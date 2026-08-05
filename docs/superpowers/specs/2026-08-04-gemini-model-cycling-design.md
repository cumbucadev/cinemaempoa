# Gemini Model Cycling — Design

## Problem

Three places in the codebase hardcode a single Gemini model, `gemini-2.5-flash`:

- `flask_backend/service/gemini_api.py` (`Gemini.MODEL`) — used synchronously by
  the `describe_image` route (`flask_backend/routes/screening.py`) for
  user-facing accessibility image descriptions.
- `flask_backend/service/movie_inspector.py` (`_build_agent`, via
  `instructor.from_provider(f"google/{Gemini.MODEL}", ...)`) — the batch
  `inspect-movies` CLI agent, which runs a bounded multi-turn tool-calling
  loop per movie.
- `scrapers/llms.py` (`_build_llm`, called with the literal string
  `"gemini-2.5-flash"` from `scrapers/cine_cinco.py` and
  `scrapers/cinebancarios.py`) — one-shot structured extraction of screening
  data from scraped text.

`gemini-2.5-flash` has a 20 requests/day free-tier quota. Google AI Studio's
rate-limit page (https://aistudio.google.com/rate-limit) lists several other
Gemini Flash models, some with much higher daily quotas:

| Model (display name)   | Free-tier RPD |
|-------------------------|---------------|
| Gemini 2.5 Flash         | 20            |
| Gemini 2.5 Flash Lite    | 20            |
| Gemini 3 Flash           | 20            |
| Gemini 3.1 Flash Lite    | 500           |
| Gemini 3.5 Flash         | 20            |
| Gemini 3.5 Flash Lite    | 500           |
| Gemini 3.6 Flash         | 20            |

Combined, these total 1080 requests/day — comfortably more than current usage
— but only if the code can fall back to a different model once one is
rate-limited, instead of hardcoding one.

## Scope

Covers all three call sites above. All three currently hit `gemini-2.5-flash`
only; after this change, all three draw from the same shared,
priority-ordered model list and fall back through it on rate limits.

## Non-goals

- No cross-process/persisted tracking of which models are exhausted "today."
  Each logical unit of work (one image description, one scrape extraction,
  one movie inspection) independently walks the priority list from the top
  and discovers rate limits fresh. This matches the existing pattern in
  `scrapers/llms.py` (which already catches and swallows 429s) and avoids
  adding a persistence layer for a low-volume workload.
- No fallback on non-rate-limit errors (bad request, network issue, malformed
  prompt, etc.) — those propagate immediately, as they do today.
- No unification of the three call sites onto a single Gemini SDK.
  `scrapers/llms.py` depends on `llama_index`'s structured-output extraction;
  `movie_inspector.py` depends on `instructor`'s `atomic-agents` integration;
  `gemini_api.py` uses the `google-genai` SDK directly. These are unrelated
  to this problem and load-bearing for their respective features.

## Model priority order

Newest generation first; within a generation, the full "Flash" model (higher
quality, lower quota) before its "Flash Lite" sibling (lower quality, higher
quota):

```python
GEMINI_MODEL_PRIORITY = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
]
```

**Open item:** these are best-guess conventional model ids derived from the
display names on the rate-limit page — the literal API model-id strings
have not been confirmed against the live API. This must be verified (and the
list corrected if needed) during implementation, before relying on the
non-`gemini-2.5-flash` entries.

## Architecture

New module `flask_backend/service/gemini_models.py` owns the priority list
and a small SDK-agnostic retry helper:

```python
GEMINI_MODEL_PRIORITY = [...]  # as above


class AllGeminiModelsExhausted(Exception):
    """Every model in GEMINI_MODEL_PRIORITY was rate-limited."""


def call_with_fallback(build_and_call, is_rate_limited, models=GEMINI_MODEL_PRIORITY):
    """Calls build_and_call(model_id) for each model in priority order,
    returning the first successful result. Only exceptions accepted by
    is_rate_limited(exc) trigger moving to the next model; anything else
    propagates immediately. Raises AllGeminiModelsExhausted (chained from
    the last error) if every model is rate-limited."""
    last_error = None
    for model_id in models:
        try:
            return build_and_call(model_id)
        except Exception as exc:
            if not is_rate_limited(exc):
                raise
            last_error = exc
            continue
    raise AllGeminiModelsExhausted from last_error
```

This module has no dependency on any particular Gemini SDK. Each call site
supplies its own `build_and_call` closure (how to build a client/agent for a
given model id and make the call) and its own `is_rate_limited` predicate
(since the exception shape differs slightly per SDK).

## Per-call-site integration

### `gemini_api.py`

The model is already a per-call parameter to `generate_content()`, not baked
into the client, so no client rebuild is needed — only the call itself is
wrapped:

```python
class Gemini:
    def __init__(self):
        if GEMINI_API_KEY is None:
            raise ValueError("Invalid Gemini API key")
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def prompt_image(self, image, text):
        image_part = types.Part.from_bytes(
            data=image.read(), mime_type=image.mimetype or "image/jpeg"
        )

        def call(model_id):
            return self.client.models.generate_content(
                model=model_id, contents=[text, image_part]
            )

        return call_with_fallback(call, _is_rate_limited).text
```

`image.read()` happens once, before the retry loop — a Flask `FileStorage`
stream can't be re-read on a second attempt.

`_is_rate_limited` checks `isinstance(exc, ClientError) and exc.code == 429`
(the same check already used in `scrapers/llms.py`).

**Knock-on change:** `routes/screening.py`'s `describe_image` currently
catches only `APIError` around `gemini.prompt_image(...)`. It must also
catch `AllGeminiModelsExhausted` and map it to the same "Erro ao gerar
descrição da imagem" 502 response, so a fully-exhausted day degrades the
same way a single API error does today.

### `scrapers/llms.py`

`_build_llm(model_id)` is unchanged in shape, but `CineBancariosExtractorLLM`
and `CineCincoExtractorLLM` drop their `model_name` constructor parameter —
the priority list is now the only source of truth for which model to use.
Callers change from `CineCincoExtractorLLM("gemini-2.5-flash")` to
`CineCincoExtractorLLM()` (same for `CineBancariosExtractorLLM` in
`scrapers/cinebancarios.py`).

`extract_screenings_from_text` builds the prompt once, then wraps
client-build-and-call in `call_with_fallback`:

```python
def call(model_id):
    llm = _build_llm(model_id)
    Settings.llm = llm
    return llm.as_structured_llm(Movies).chat(messages)

try:
    response = call_with_fallback(call, _is_rate_limited)
except AllGeminiModelsExhausted:
    print("All Gemini models rate-limited. Exiting...")
    return
```

This replaces the two near-identical `except ... e.code == 429` blocks (one
per extractor class) with one shared predicate function.

### `movie_inspector.py`

The retryable unit is the *whole* per-movie tool-calling loop, not a single
turn: if a 429 hits mid-conversation, the entire inspection for that movie
restarts with the next model rather than swapping models mid-conversation.
`_build_agent(model_id)` now takes the model id. `inspect_movie` builds a
fresh `OrchestratorInput` inside the retry closure so a retry starts with a
clean observation history rather than carrying over partial tool-call
context from a truncated attempt:

```python
def inspect_movie(movie):
    def call(model_id):
        agent_input = OrchestratorInput(...)  # built fresh per attempt
        agent = _build_agent(model_id)
        _attach_debug_hooks(agent, movie)
        return _run_inspection_loop(agent, agent_input, allowed_screening_ids)

    return call_with_fallback(call, _is_rate_limited)
```

`AllGeminiModelsExhausted` needs no special handling in `run_pipeline` — its
existing blanket `except Exception as exc:` already records
`status="error"` and moves to the next movie. This is exactly the kind of
transient failure `flask_backend/repository/movie_inspections.py`'s
`_get_latest_checked_tmdb_id` docstring already anticipates ("Gemini rate
limit, network blip").

**Open item:** what exception `instructor.from_provider("google/...")`
raises on a 429 (the raw `google.genai.errors.ClientError`, or something
instructor wraps) is not confirmed from documentation. Must be verified
during implementation — by triggering a real 429 or reading the relevant
instructor/google-genai source — before finalizing `_is_rate_limited` for
this call site.

## Error handling & exhaustion semantics

Two failure shapes flow through `call_with_fallback`:

- **Non-rate-limit errors** (bad request, network issue, malformed prompt,
  etc.) propagate immediately from whichever model was being tried — no
  fallback.
- **All 7 models rate-limited** → `AllGeminiModelsExhausted` propagates once,
  chained from the last model's error. Each site degrades the same way it
  degrades for a single API error today (see per-site sections above):
  `gemini_api.py`/`screening.py` → same 502 response; `scrapers/llms.py` →
  same "exiting" print + `None` return; `movie_inspector.py` → same
  `status="error"` row via `run_pipeline`'s existing blanket exception
  handler.

No new persistence, no cross-process state, no daily reset logic.

## Testing

- **`gemini_models.py`** (new): unit tests for `call_with_fallback` —
  succeeds on the first model; skips N rate-limited models before
  succeeding; raises `AllGeminiModelsExhausted` (chained from the last
  error) when every model fails; propagates immediately on a
  non-rate-limited exception without trying further models.
- **`gemini_api.py`**: extend `Gemini.prompt_image` tests to cover the
  fallback path (mock `generate_content` to 429 on the first model id,
  succeed on the second) and the fully-exhausted path.
- **`scrapers/llms.py`**: `tests/scrapers/test_llms.py` currently asserts
  construction with a hardcoded `model="gemini-2.5-flash"` — these need
  rewriting since the constructors no longer take a model name. Add cases
  for mid-list fallback and full exhaustion (the `AllGeminiModelsExhausted`
  → print+`None` path).
- **`movie_inspector.py`**: extend existing `_build_agent`/`inspect_movie`
  test coverage with a case where the first model 429s mid-loop and the
  whole per-movie inspection retries cleanly on the next model with a fresh
  `OrchestratorInput`.
- No integration/live-API test is planned — the real model ids are
  best-guess pending verification, and hitting the live free-tier quota
  from CI would defeat the purpose.
