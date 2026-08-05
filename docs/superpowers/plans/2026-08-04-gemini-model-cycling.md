# Gemini Model Cycling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `gemini-2.5-flash` model used across three call sites with a shared, priority-ordered list of Gemini models that falls back to the next model on a 429 (rate limit) response, so the app can use its full combined free-tier daily quota instead of being capped at one model's 20 RPD.

**Architecture:** A new SDK-agnostic module, `flask_backend/service/gemini_models.py`, owns the ordered model-id list and a `call_with_fallback(build_and_call, is_rate_limited, models=...)` helper that tries each model in order, moving on only when `is_rate_limited` accepts the raised exception, and raising `AllGeminiModelsExhausted` (chained from the last error) if every model fails. Each of the three call sites (`gemini_api.py`, `scrapers/llms.py`, `movie_inspector.py`) keeps its own SDK and supplies its own client-building closure and rate-limit predicate.

**Tech Stack:** Python 3.14, Flask, `google-genai` SDK, `llama_index` (`llama_index.llms.google_genai`), `instructor` + `atomic-agents`, `pytest`, `uv`.

## Global Constraints

- Use `uv run` / `uv sync` for all Python commands — do not invoke a bare `python`/`pytest` outside `uv run` if a project virtualenv is in play (see `AGENTS.md`).
- Run `uv run ruff check --fix` and `uv run ruff format` before any commit that touches `.py` files (per `AGENTS.md`; CI fails on unformatted code). This plan does not touch templates, so `djlint` is not required.
- Only rate-limit (HTTP 429 / `google.genai.errors.ClientError` with `.code == 429`) exceptions trigger falling back to the next model. All other exceptions propagate immediately from whichever model raised them — no fallback.
- No cross-process or persisted "exhausted today" state. Each logical unit of work (one image description, one scrape extraction, one movie inspection) independently walks the priority list from the top.
- The model-id strings in `GEMINI_MODEL_PRIORITY` beyond `gemini-2.5-flash`/`gemini-2.5-flash-lite` are best-guess conventional ids, not confirmed against the live Gemini API. This plan implements and tests them with mocks; verifying the literal strings against a real API key is a follow-up the user does manually (see Task 1, Step 6).
- Never add an AI/agent co-author trailer to any commit (per `AGENTS.md`).

---

### Task 1: `gemini_models.py` — shared priority list and fallback helper

**Files:**
- Create: `flask_backend/service/gemini_models.py`
- Test: `flask_backend/tests/test_service/test_gemini_models.py`

**Interfaces:**
- Produces: `GEMINI_MODEL_PRIORITY: list[str]` (module-level constant, 7 model ids, newest-first, Flash before Flash Lite per generation).
- Produces: `class AllGeminiModelsExhausted(Exception)`.
- Produces: `def call_with_fallback(build_and_call: Callable[[str], T], is_rate_limited: Callable[[Exception], bool], models: list[str] = GEMINI_MODEL_PRIORITY) -> T`.

- [ ] **Step 1: Write the failing tests**

Create `flask_backend/tests/test_service/test_gemini_models.py`:

```python
import pytest

from flask_backend.service.gemini_models import (
    AllGeminiModelsExhausted,
    call_with_fallback,
)


class TestCallWithFallback:
    def test_succeeds_on_first_model(self):
        calls = []

        def build_and_call(model_id):
            calls.append(model_id)
            return "ok"

        result = call_with_fallback(
            build_and_call, lambda exc: False, models=["model-a", "model-b"]
        )

        assert result == "ok"
        assert calls == ["model-a"]

    def test_falls_back_after_rate_limited_models(self):
        calls = []

        def build_and_call(model_id):
            calls.append(model_id)
            if model_id != "model-c":
                raise ValueError("rate limited")
            return "ok"

        result = call_with_fallback(
            build_and_call,
            lambda exc: True,
            models=["model-a", "model-b", "model-c"],
        )

        assert result == "ok"
        assert calls == ["model-a", "model-b", "model-c"]

    def test_raises_all_exhausted_when_every_model_is_rate_limited(self):
        def build_and_call(model_id):
            raise ValueError(f"rate limited: {model_id}")

        with pytest.raises(AllGeminiModelsExhausted) as exc_info:
            call_with_fallback(
                build_and_call, lambda exc: True, models=["model-a", "model-b"]
            )

        assert isinstance(exc_info.value.__cause__, ValueError)
        assert "model-b" in str(exc_info.value.__cause__)

    def test_non_rate_limited_exception_propagates_immediately(self):
        calls = []

        def build_and_call(model_id):
            calls.append(model_id)
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            call_with_fallback(
                build_and_call, lambda exc: False, models=["model-a", "model-b"]
            )

        assert calls == ["model-a"]

    def test_default_models_is_gemini_model_priority(self):
        from flask_backend.service.gemini_models import GEMINI_MODEL_PRIORITY

        calls = []

        def build_and_call(model_id):
            calls.append(model_id)
            return "ok"

        call_with_fallback(build_and_call, lambda exc: False)

        assert calls == [GEMINI_MODEL_PRIORITY[0]]


class TestGeminiModelPriority:
    def test_has_seven_models_newest_flash_before_lite_per_generation(self):
        from flask_backend.service.gemini_models import GEMINI_MODEL_PRIORITY

        assert GEMINI_MODEL_PRIORITY == [
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3-flash",
            "gemini-2.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash-lite",
        ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest flask_backend/tests/test_service/test_gemini_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'flask_backend.service.gemini_models'`

- [ ] **Step 3: Write the implementation**

Create `flask_backend/service/gemini_models.py`:

```python
from typing import Callable, TypeVar

T = TypeVar("T")

GEMINI_MODEL_PRIORITY = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
]


class AllGeminiModelsExhausted(Exception):
    """Every model in GEMINI_MODEL_PRIORITY was rate-limited."""


def call_with_fallback(
    build_and_call: Callable[[str], T],
    is_rate_limited: Callable[[Exception], bool],
    models: list[str] = GEMINI_MODEL_PRIORITY,
) -> T:
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest flask_backend/tests/test_service/test_gemini_models.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Lint and format**

Run: `uv run ruff check --fix flask_backend/service/gemini_models.py flask_backend/tests/test_service/test_gemini_models.py && uv run ruff format flask_backend/service/gemini_models.py flask_backend/tests/test_service/test_gemini_models.py`

- [ ] **Step 6: Commit**

```bash
git add flask_backend/service/gemini_models.py flask_backend/tests/test_service/test_gemini_models.py
git commit -m "feat: add shared Gemini model priority list and fallback helper"
```

**Note for the user (not an automated step):** the model ids `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3-flash`, `gemini-3.5-flash-lite`, and `gemini-3.1-flash-lite` are best-guess conventional ids and have not been confirmed against the live Gemini API. Verify them (e.g. by listing available models with a real `GEMINI_API_KEY`) before relying on this in production, and update `GEMINI_MODEL_PRIORITY` if any string is wrong.

---

### Task 2: `gemini_api.py` — fall back across models in `prompt_image`

**Files:**
- Modify: `flask_backend/service/gemini_api.py`
- Test: `flask_backend/tests/test_service/test_gemini_api.py`

**Interfaces:**
- Consumes: `call_with_fallback`, `GEMINI_MODEL_PRIORITY` from `flask_backend.service.gemini_models` (Task 1).
- Produces: `Gemini.prompt_image(image, text) -> str` (unchanged signature/return type). `Gemini.MODEL` class attribute is removed — nothing else in the codebase but `movie_inspector.py` (Task 5) reads it.

- [ ] **Step 1: Write the failing tests**

Replace the contents of `flask_backend/tests/test_service/test_gemini_api.py`:

```python
import io
from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ClientError

from flask_backend.service.gemini_api import Gemini
from flask_backend.service.gemini_models import GEMINI_MODEL_PRIORITY


class TestGeminiInit:
    def test_missing_api_key_raises_value_error(self):
        with (
            patch("flask_backend.service.gemini_api.GEMINI_API_KEY", None),
            pytest.raises(ValueError, match="Invalid Gemini API key"),
        ):
            Gemini()

    def test_with_api_key_builds_client(self):
        with (
            patch("flask_backend.service.gemini_api.GEMINI_API_KEY", "fake-key"),
            patch("flask_backend.service.gemini_api.genai.Client") as mock_client_cls,
        ):
            Gemini()
        mock_client_cls.assert_called_once_with(api_key="fake-key")


def _make_gemini():
    with (
        patch("flask_backend.service.gemini_api.GEMINI_API_KEY", "fake-key"),
        patch(
            "flask_backend.service.gemini_api.genai.Client", return_value=MagicMock()
        ),
    ):
        return Gemini()


class TestPromptImage:
    def test_success_returns_response_text(self):
        gemini = _make_gemini()
        mock_response = MagicMock()
        mock_response.text = "Uma bela descrição."
        gemini.client.models.generate_content.return_value = mock_response

        image = io.BytesIO(b"fake-image-bytes")
        image.mimetype = "image/jpeg"

        result = gemini.prompt_image(image, "describe this")

        assert result == "Uma bela descrição."
        args, kwargs = gemini.client.models.generate_content.call_args
        assert kwargs["model"] == GEMINI_MODEL_PRIORITY[0]
        assert kwargs["contents"][0] == "describe this"

    def test_rate_limit_on_first_model_falls_back_to_second(self):
        gemini = _make_gemini()
        mock_response = MagicMock()
        mock_response.text = "Uma bela descrição."
        gemini.client.models.generate_content.side_effect = [
            ClientError(code=429, response_json={}),
            mock_response,
        ]

        image = io.BytesIO(b"fake-image-bytes")
        image.mimetype = "image/jpeg"

        result = gemini.prompt_image(image, "describe this")

        assert result == "Uma bela descrição."
        calls = gemini.client.models.generate_content.call_args_list
        assert calls[0].kwargs["model"] == GEMINI_MODEL_PRIORITY[0]
        assert calls[1].kwargs["model"] == GEMINI_MODEL_PRIORITY[1]

    def test_rate_limit_on_every_model_raises_all_exhausted(self):
        from flask_backend.service.gemini_models import AllGeminiModelsExhausted

        gemini = _make_gemini()
        gemini.client.models.generate_content.side_effect = ClientError(
            code=429, response_json={}
        )

        image = io.BytesIO(b"fake-image-bytes")
        image.mimetype = "image/jpeg"

        with pytest.raises(AllGeminiModelsExhausted):
            gemini.prompt_image(image, "describe this")

        assert gemini.client.models.generate_content.call_count == len(
            GEMINI_MODEL_PRIORITY
        )

    def test_non_rate_limit_error_propagates_without_fallback(self):
        gemini = _make_gemini()
        gemini.client.models.generate_content.side_effect = ValueError("boom")

        image = io.BytesIO(b"fake-image-bytes")
        image.mimetype = "image/jpeg"

        with pytest.raises(ValueError, match="boom"):
            gemini.prompt_image(image, "describe this")

        assert gemini.client.models.generate_content.call_count == 1
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `uv run pytest flask_backend/tests/test_service/test_gemini_api.py -v`
Expected: `test_success_returns_response_text` FAILs (asserts `GEMINI_MODEL_PRIORITY[0]` but code still sends `Gemini.MODEL`), `test_rate_limit_on_first_model_falls_back_to_second` and `test_rate_limit_on_every_model_raises_all_exhausted` FAIL (no fallback exists yet — old code raises `ClientError` directly on first call).

- [ ] **Step 3: Write the implementation**

Replace the contents of `flask_backend/service/gemini_api.py`:

```python
from google import genai
from google.genai import types
from google.genai.errors import ClientError

from flask_backend.env_config import GEMINI_API_KEY
from flask_backend.service.gemini_models import call_with_fallback


def _is_rate_limited(exc: Exception) -> bool:
    return isinstance(exc, ClientError) and exc.code == 429


class Gemini:
    """Interacts with Google's Gemini API via the google-genai SDK
    https://ai.google.dev/gemini-api/docs"""

    def __init__(self):
        if GEMINI_API_KEY is None:
            raise ValueError("Invalid Gemini API key")
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def prompt_image(self, image, text):
        image_part = types.Part.from_bytes(
            data=image.read(),
            mime_type=image.mimetype or "image/jpeg",
        )

        def call(model_id):
            return self.client.models.generate_content(
                model=model_id,
                contents=[text, image_part],
            )

        response = call_with_fallback(call, _is_rate_limited)
        return response.text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest flask_backend/tests/test_service/test_gemini_api.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Lint and format**

Run: `uv run ruff check --fix flask_backend/service/gemini_api.py flask_backend/tests/test_service/test_gemini_api.py && uv run ruff format flask_backend/service/gemini_api.py flask_backend/tests/test_service/test_gemini_api.py`

- [ ] **Step 6: Commit**

```bash
git add flask_backend/service/gemini_api.py flask_backend/tests/test_service/test_gemini_api.py
git commit -m "feat: fall back across Gemini models in Gemini.prompt_image"
```

---

### Task 3: `routes/screening.py` — handle full model exhaustion in `describe_image`

**Files:**
- Modify: `flask_backend/routes/screening.py`
- Test: `flask_backend/tests/test_routes/test_screening.py`

**Interfaces:**
- Consumes: `AllGeminiModelsExhausted` from `flask_backend.service.gemini_models` (Task 1).

- [ ] **Step 1: Write the failing test**

In `flask_backend/tests/test_routes/test_screening.py`, add this test to `TestScreeningDescribeImage` (after `test_describe_image_rate_limit_returns_502`, defined around line 694):

```python
    def test_describe_image_all_models_exhausted_returns_502(self, auth_headers):
        from flask_backend.service.gemini_models import AllGeminiModelsExhausted

        mock_gemini = MagicMock()
        mock_gemini.prompt_image.side_effect = AllGeminiModelsExhausted()
        with patch("flask_backend.routes.screening.Gemini", return_value=mock_gemini):
            response = auth_headers.post(
                "/screening/image/describe",
                data={"image": (io.BytesIO(b"fake"), "photo.jpg")},
                content_type="multipart/form-data",
            )
        assert response.status_code == 502
        assert (
            response.get_json()["details"]
            == "Erro ao gerar descrição da imagem. Tente novamente."
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest flask_backend/tests/test_routes/test_screening.py -k test_describe_image_all_models_exhausted_returns_502 -v`
Expected: FAIL — `AllGeminiModelsExhausted` propagates uncaught out of the view (500 from Flask's default error handling, not the 502 the test expects), since `describe_image` only catches `APIError`.

- [ ] **Step 3: Update the implementation**

In `flask_backend/routes/screening.py`, add the import near the existing `Gemini` import (around line 48):

```python
from flask_backend.service.gemini_api import Gemini
from flask_backend.service.gemini_models import AllGeminiModelsExhausted
```

Then change the `except` clause in `describe_image` (around line 512):

```python
    try:
        image_description = gemini.prompt_image(image, prompt_text)
    except (APIError, AllGeminiModelsExhausted) as e:
        return jsonify(
            {
                "details": "Erro ao gerar descrição da imagem. Tente novamente.",
                "info": str(e),
            }
        ), 502
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest flask_backend/tests/test_routes/test_screening.py -k TestScreeningDescribeImage -v`
Expected: PASS (all `TestScreeningDescribeImage` tests, including the new one)

- [ ] **Step 5: Lint and format**

Run: `uv run ruff check --fix flask_backend/routes/screening.py flask_backend/tests/test_routes/test_screening.py && uv run ruff format flask_backend/routes/screening.py flask_backend/tests/test_routes/test_screening.py`

- [ ] **Step 6: Commit**

```bash
git add flask_backend/routes/screening.py flask_backend/tests/test_routes/test_screening.py
git commit -m "fix: return 502 when all Gemini models are rate-limited in describe_image"
```

---

### Task 4: `scrapers/llms.py` — fall back across models in both extractor classes

**Files:**
- Modify: `scrapers/llms.py`
- Modify: `scrapers/cine_cinco.py` (drop the `model_name` argument at the `CineCincoExtractorLLM()` call site)
- Modify: `scrapers/cinebancarios.py` (drop the `model_name` argument at the `CineBancariosExtractorLLM()` call site)
- Test: `tests/scrapers/test_llms.py`

**Interfaces:**
- Consumes: `call_with_fallback`, `AllGeminiModelsExhausted` from `flask_backend.service.gemini_models` (Task 1).
- Produces: `CineBancariosExtractorLLM()` and `CineCincoExtractorLLM()` — both constructors now take **no** `model_name` argument (dropped; the priority list is the only source of truth). `extract_screenings_from_text(...)` keeps its existing signature and return type (`str | None`) on both classes.

- [ ] **Step 1: Write the failing tests**

Replace the contents of `tests/scrapers/test_llms.py`:

```python
from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ClientError as GoogleGenAIClientError

from flask_backend.service.gemini_models import GEMINI_MODEL_PRIORITY
from scrapers.llms import CineBancariosExtractorLLM, CineCincoExtractorLLM


class TestCineBancariosExtractorLLMInit:
    def test_gemini_without_api_key_raises_value_error(self):
        with (
            patch("scrapers.llms.GEMINI_API_KEY", None),
            pytest.raises(ValueError, match="GEMINI_API_KEY is not set"),
        ):
            CineBancariosExtractorLLM()

    def test_gemini_with_api_key_constructs(self):
        with patch("scrapers.llms.GEMINI_API_KEY", "fake-key"):
            CineBancariosExtractorLLM()


def _make_extractor():
    with patch("scrapers.llms.GEMINI_API_KEY", "fake-key"):
        return CineBancariosExtractorLLM()


class TestExtractScreeningsFromText:
    def test_success_returns_raw_json(self):
        extractor = _make_extractor()
        mock_response = MagicMock()
        mock_response.raw.model_dump_json.return_value = '{"movies": []}'
        mock_llm = MagicMock()
        mock_llm.as_structured_llm.return_value.chat.return_value = mock_response

        with (
            patch("scrapers.llms._build_llm", return_value=mock_llm) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(
                "Mon, 09 Mar 2026 18:48:00 +0000", "some blog text"
            )

        assert result == '{"movies": []}'
        mock_build.assert_called_once_with(GEMINI_MODEL_PRIORITY[0])

    def test_rate_limit_on_first_model_falls_back_to_second(self):
        extractor = _make_extractor()
        mock_response = MagicMock()
        mock_response.raw.model_dump_json.return_value = '{"movies": []}'
        first_llm = MagicMock()
        first_llm.as_structured_llm.return_value.chat.side_effect = (
            GoogleGenAIClientError(code=429, response_json={})
        )
        second_llm = MagicMock()
        second_llm.as_structured_llm.return_value.chat.return_value = mock_response

        with (
            patch(
                "scrapers.llms._build_llm", side_effect=[first_llm, second_llm]
            ) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(
                "Mon, 09 Mar 2026 18:48:00 +0000", "some blog text"
            )

        assert result == '{"movies": []}'
        assert mock_build.call_args_list[0].args == (GEMINI_MODEL_PRIORITY[0],)
        assert mock_build.call_args_list[1].args == (GEMINI_MODEL_PRIORITY[1],)

    def test_rate_limit_on_every_model_returns_none(self):
        extractor = _make_extractor()
        mock_llm = MagicMock()
        mock_llm.as_structured_llm.return_value.chat.side_effect = (
            GoogleGenAIClientError(code=429, response_json={})
        )

        with (
            patch("scrapers.llms._build_llm", return_value=mock_llm) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(
                "Mon, 09 Mar 2026 18:48:00 +0000", "some blog text"
            )

        assert result is None
        assert mock_build.call_count == len(GEMINI_MODEL_PRIORITY)

    def test_generic_exception_returns_none(self):
        extractor = _make_extractor()
        mock_llm = MagicMock()
        mock_llm.as_structured_llm.return_value.chat.side_effect = Exception("boom")

        with (
            patch("scrapers.llms._build_llm", return_value=mock_llm) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(
                "Mon, 09 Mar 2026 18:48:00 +0000", "some blog text"
            )

        assert result is None
        assert mock_build.call_count == 1


class TestGetCurrYear:
    def test_returns_current_year(self):
        extractor = _make_extractor()
        with patch("scrapers.llms.datetime") as mock_dt:
            mock_dt.now.return_value.year = 2026
            assert extractor._get_curr_year() == 2026


class TestPromptBuilders:
    def test_get_system_prompt_includes_year(self):
        extractor = _make_extractor()
        prompt = extractor._get_system_prompt(2026)
        assert "2026" in prompt
        assert "cinema programming auditor" in prompt

    def test_get_prompt_builds_system_and_user_messages(self):
        extractor = _make_extractor()
        messages = extractor._get_prompt(2026, "some blog text")
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "some blog text"


def _make_cine_cinco_extractor():
    with patch("scrapers.llms.GEMINI_API_KEY", "fake-key"):
        return CineCincoExtractorLLM()


class TestCineCincoExtractorLLMInit:
    def test_gemini_without_api_key_raises_value_error(self):
        with (
            patch("scrapers.llms.GEMINI_API_KEY", None),
            pytest.raises(ValueError, match="GEMINI_API_KEY is not set"),
        ):
            CineCincoExtractorLLM()


class TestCineCincoExtractScreeningsFromText:
    def test_success_returns_raw_json(self):
        extractor = _make_cine_cinco_extractor()
        mock_response = MagicMock()
        mock_response.raw.model_dump_json.return_value = '{"movies": []}'
        mock_llm = MagicMock()
        mock_llm.as_structured_llm.return_value.chat.return_value = mock_response

        with (
            patch("scrapers.llms._build_llm", return_value=mock_llm) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(2026, "some page text")

        assert result == '{"movies": []}'
        mock_build.assert_called_once_with(GEMINI_MODEL_PRIORITY[0])

    def test_rate_limit_on_every_model_returns_none(self):
        extractor = _make_cine_cinco_extractor()
        mock_llm = MagicMock()
        mock_llm.as_structured_llm.return_value.chat.side_effect = (
            GoogleGenAIClientError(code=429, response_json={})
        )

        with (
            patch("scrapers.llms._build_llm", return_value=mock_llm) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(2026, "some page text")

        assert result is None
        assert mock_build.call_count == len(GEMINI_MODEL_PRIORITY)

    def test_generic_exception_returns_none(self):
        extractor = _make_cine_cinco_extractor()
        mock_llm = MagicMock()
        mock_llm.as_structured_llm.return_value.chat.side_effect = Exception("boom")

        with (
            patch("scrapers.llms._build_llm", return_value=mock_llm) as mock_build,
            patch("scrapers.llms.Settings"),
        ):
            result = extractor.extract_screenings_from_text(2026, "some page text")

        assert result is None
        assert mock_build.call_count == 1


class TestCineCincoPromptBuilders:
    def test_get_system_prompt_includes_year_and_cine_cinco(self):
        extractor = _make_cine_cinco_extractor()
        prompt = extractor._get_system_prompt(2026)
        assert "2026" in prompt
        assert "Cine Cinco" in prompt
        assert "Direção de" in prompt

    def test_get_prompt_builds_system_and_user_messages(self):
        extractor = _make_cine_cinco_extractor()
        messages = extractor._get_prompt(2026, "some page text")
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "some page text"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scrapers/test_llms.py -v`
Expected: FAIL — `CineBancariosExtractorLLM()`/`CineCincoExtractorLLM()` still require a `model_name` positional argument (`TypeError: __init__() missing 1 required positional argument`), and `scrapers.llms._build_llm` doesn't accept being called as a standalone patched target the way these tests expect yet (module still validates `model_name == "gemini-2.5-flash"`).

- [ ] **Step 3: Write the implementation**

Replace the contents of `scrapers/llms.py`:

```python
from datetime import datetime

from google.genai.errors import ClientError as GoogleGenAIClientError
from llama_index.core import Settings
from llama_index.core.bridge.pydantic import BaseModel
from llama_index.core.llms import ChatMessage

from flask_backend.env_config import GEMINI_API_KEY
from flask_backend.service.gemini_models import AllGeminiModelsExhausted, call_with_fallback


class Movie(BaseModel):
    title: str
    image_url: str
    general_info: str
    director: str
    classification: str
    excerpt: str
    screening_dates: list[str]


class Movies(BaseModel):
    movies: list[Movie]


def _is_rate_limited(exc: Exception) -> bool:
    return isinstance(exc, GoogleGenAIClientError) and exc.code == 429


def _build_llm(model_id):
    from llama_index.llms.google_genai import GoogleGenAI

    return GoogleGenAI(model=model_id, api_key=GEMINI_API_KEY)


class CineBancariosExtractorLLM:
    def __init__(self):
        if GEMINI_API_KEY is None:
            raise ValueError("GEMINI_API_KEY is not set")

    def _get_curr_year(self):
        current_datetime = datetime.now()
        return current_datetime.year

    def extract_screenings_from_text(self, strPubDate, text):
        # pubDate is in the format 2010-03-09T18:48:00+00:00
        pubDate = datetime.strptime(strPubDate, "%a, %d %b %Y %H:%M:%S %z")
        year = pubDate.year
        messages = self._get_prompt(year, text)

        def call(model_id):
            llm = _build_llm(model_id)
            Settings.llm = llm
            return llm.as_structured_llm(Movies).chat(messages)

        try:
            response = call_with_fallback(call, _is_rate_limited)
        except AllGeminiModelsExhausted:
            print("All Gemini models rate-limited. Exiting...")
            return
        except Exception as e:
            print(f"Error: {e}")
            return
        return response.raw.model_dump_json()

    def _get_system_prompt(self, year):
        return f"""You are a cinema programming auditor. You need to collect screening information from the following text.
For each movie, extract the following information:
1. Title: The name of the movie
2. Image URL: If available, the URL of the movie's poster image
3. General Info: Information in the format "Country/Genre/Year/Duration" (e.g. "Brasil/Drama/2023/97min")
4. Director: The director's name, usually found after "Direção:"
5. Classification: The age rating, usually found after "Classificação indicativa:"
6. Excerpt: The movie's synopsis, usually found after "Sinopse:"
7. Screening Dates: All dates and times when the movie is shown
The text may contain multiple movies. Each movie's information is usually separated by blank lines or section headers like "ESTREIA" or "EM CARTAZ".
Make sure to:
- Extract all available information for each movie
- Handle cases where some information might be missing
- Keep the original formatting of the text where appropriate
- Include all screening times for each movie. The year is {year}. The format of the dates is YYYY-MM-DD HH:MM.
- Return the data in JSON format that matches the following structure:

If no movies are found, return an empty list."""

    def _get_prompt(self, year, text_content):
        messages = [
            ChatMessage(role="system", content=self._get_system_prompt(year)),
            ChatMessage(role="user", content=text_content),
        ]
        return messages


class CineCincoExtractorLLM:
    def __init__(self):
        if GEMINI_API_KEY is None:
            raise ValueError("GEMINI_API_KEY is not set")

    def extract_screenings_from_text(self, year, text):
        messages = self._get_prompt(year, text)

        def call(model_id):
            llm = _build_llm(model_id)
            Settings.llm = llm
            return llm.as_structured_llm(Movies).chat(messages)

        try:
            response = call_with_fallback(call, _is_rate_limited)
        except AllGeminiModelsExhausted:
            print("All Gemini models rate-limited. Exiting...")
            return
        except Exception as e:
            print(f"Error: {e}")
            return
        return response.raw.model_dump_json()

    def _get_system_prompt(self, year):
        return f"""You are a cinema programming auditor for "Cine Cinco", a free university cinema run by PUCRS in Porto Alegre, Brazil. You need to collect screening information from the following text, which was extracted from the cinema's programming page.
The text begins with a page title, a "Programação" heading, and sometimes a themed batch heading (e.g. "COPA DO CINEMA") followed by an intro paragraph - these are NOT movies, ignore them. After that, one block of text follows per movie. The text also ends with a few paragraphs of general information about the Cine Cinco venue (its location, capacity, regular schedule) - these are NOT movies either, ignore them too.
For each movie, extract the following information:
1. Title: The name of the movie, usually the first line of its block
2. Image URL: If available, the URL of the movie's poster image
3. General Info: Information in the format "Country/Genre/Year/Duration" (e.g. "Brasil/Drama/2023/97min")
4. Director: The director's name, usually found after "Direção de". This is sometimes ABSENT entirely (e.g. "Sessão Surpresa" entries usually have no director mentioned) - if there is no director for a movie, return an empty string, never guess or invent one.
5. Classification: The age rating, usually found after "Classificação" (e.g. "Classificação 18 anos", or "Classificação Livre" for a free/unrestricted rating).
6. Excerpt: The movie's synopsis. Unlike other cinema listings, there is no "Sinopse:" label here - it is simply the unlabeled paragraph of prose that follows the general info/director/classification lines.
7. Screening Dates: One or more sessions, usually introduced by "Sessão:", in the format "D/M • weekday — HHhMM" (e.g. "1/7 • quarta — 17h"). The day and month are given but the YEAR IS NOT PRESENT IN THE TEXT - always use {year} as the year. Convert each session into the format YYYY-MM-DD HH:MM. A movie may have more than one session listed - return one string per session.
Each movie's block is usually followed by a blank line, and sometimes a trailing "Apoio: ..." sponsor line - ignore the sponsor line, it is not part of the film's info.
Make sure to:
- Extract all available information for each movie
- Handle cases where some information (especially Director) might be missing - use an empty string, never fabricate data
- Include all screening times for each movie
- Return the data in JSON format that matches the following structure:

If no movies are found, return an empty list."""

    def _get_prompt(self, year, text_content):
        messages = [
            ChatMessage(role="system", content=self._get_system_prompt(year)),
            ChatMessage(role="user", content=text_content),
        ]
        return messages
```

Then in `scrapers/cine_cinco.py`, change line 69 from:

```python
        gemini = CineCincoExtractorLLM("gemini-2.5-flash")
```

to:

```python
        gemini = CineCincoExtractorLLM()
```

And in `scrapers/cinebancarios.py`, change line 59 from:

```python
        gemini = CineBancariosExtractorLLM("gemini-2.5-flash")
```

to:

```python
        gemini = CineBancariosExtractorLLM()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scrapers/test_llms.py tests/scrapers/test_cine_cinco.py tests/scrapers/test_cinebancarios.py -v`
Expected: PASS (the two scraper-level test files already patch `CineCincoExtractorLLM`/`CineBancariosExtractorLLM` wholesale via `unittest.mock.patch`, so they're unaffected by the dropped constructor argument)

- [ ] **Step 5: Lint and format**

Run: `uv run ruff check --fix scrapers/llms.py scrapers/cine_cinco.py scrapers/cinebancarios.py tests/scrapers/test_llms.py && uv run ruff format scrapers/llms.py scrapers/cine_cinco.py scrapers/cinebancarios.py tests/scrapers/test_llms.py`

- [ ] **Step 6: Commit**

```bash
git add scrapers/llms.py scrapers/cine_cinco.py scrapers/cinebancarios.py tests/scrapers/test_llms.py
git commit -m "feat: fall back across Gemini models in scraper LLM extractors"
```

---

### Task 5: `movie_inspector.py` — retry the whole per-movie inspection with the next model

**Files:**
- Modify: `flask_backend/service/movie_inspector.py`
- Test: `flask_backend/tests/test_service/test_movie_inspector.py`

**Interfaces:**
- Consumes: `call_with_fallback`, `AllGeminiModelsExhausted` from `flask_backend.service.gemini_models` (Task 1).
- Produces: `_build_agent(model_id: str) -> AtomicAgent[OrchestratorInput, OrchestratorDecision]` (now takes a `model_id` parameter instead of reading `Gemini.MODEL`). `inspect_movie(movie) -> InspectionOutcome` keeps its existing signature/return type; on the inside it now retries the whole tool-calling loop with the next model on a 429, starting each retry with a fresh `OrchestratorInput`. New private helper `_run_inspection_loop(model_id, movie, allowed_screening_ids) -> InspectionOutcome` holds the per-attempt logic previously inlined in `inspect_movie`.

- [ ] **Step 1: Write the failing test**

In `flask_backend/tests/test_service/test_movie_inspector.py`, add this test to `TestInspectMovie` (the class starting around line 393; place it after `test_attaches_debug_hooks_to_the_built_agent`, around line 428):

```python
    def test_rate_limit_on_first_model_retries_whole_inspection_on_second(self, app):
        from google.genai.errors import ClientError

        with app.app_context():
            movie = _create_movie(tmdb_id=42)

            rate_limited_agent = MagicMock()
            rate_limited_agent.run.side_effect = ClientError(
                code=429, response_json={}
            )
            second_agent = MagicMock()
            second_agent.run.return_value = self._decision(
                verdict=self._verdict(status="consistent", reasoning="ok")
            )

            with patch.object(
                movie_inspector,
                "_build_agent",
                side_effect=[rate_limited_agent, second_agent],
            ) as mock_build_agent:
                outcome = movie_inspector.inspect_movie(movie)

            from flask_backend.service.gemini_models import GEMINI_MODEL_PRIORITY

            assert outcome.status == "consistent"
            assert mock_build_agent.call_args_list[0].args == (
                GEMINI_MODEL_PRIORITY[0],
            )
            assert mock_build_agent.call_args_list[1].args == (
                GEMINI_MODEL_PRIORITY[1],
            )

    def test_rate_limit_on_every_model_raises_all_exhausted(self, app):
        from google.genai.errors import ClientError

        from flask_backend.service.gemini_models import (
            AllGeminiModelsExhausted,
            GEMINI_MODEL_PRIORITY,
        )

        with app.app_context():
            movie = _create_movie(tmdb_id=42)

            rate_limited_agent = MagicMock()
            rate_limited_agent.run.side_effect = ClientError(
                code=429, response_json={}
            )

            with patch.object(
                movie_inspector, "_build_agent", return_value=rate_limited_agent
            ) as mock_build_agent:
                with pytest.raises(AllGeminiModelsExhausted):
                    movie_inspector.inspect_movie(movie)

            assert mock_build_agent.call_count == len(GEMINI_MODEL_PRIORITY)
```

Check the top of the test file for the existing `pytest` import (used elsewhere for e.g. `pytest.raises` in other test classes); add `import pytest` alongside the existing `from unittest.mock import MagicMock, patch` at the top of the file if it is not already imported.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest flask_backend/tests/test_service/test_movie_inspector.py -k "test_rate_limit_on_first_model_retries_whole_inspection_on_second or test_rate_limit_on_every_model_raises_all_exhausted" -v`
Expected: FAIL — `ClientError` propagates straight out of `inspect_movie` on the first `agent.run()` call today; there is no fallback, so the first test's second `_build_agent` call never happens and the second test's `pytest.raises(AllGeminiModelsExhausted)` doesn't match the raw `ClientError` that's actually raised.

- [ ] **Step 3: Write the implementation**

In `flask_backend/service/movie_inspector.py`, change the imports (around lines 12–30): remove `from flask_backend.service.gemini_api import Gemini` and add:

```python
from google.genai.errors import ClientError

from flask_backend.service.gemini_models import AllGeminiModelsExhausted, call_with_fallback
```

Add `_is_rate_limited` near the top-level helpers (e.g. right before `_build_agent`, around line 217):

```python
def _is_rate_limited(exc: Exception) -> bool:
    return isinstance(exc, ClientError) and exc.code == 429
```

Change `_build_agent` (around line 217) to take `model_id`:

```python
def _build_agent(model_id: str) -> AtomicAgent[OrchestratorInput, OrchestratorDecision]:
    client = instructor.from_provider(f"google/{model_id}", api_key=GEMINI_API_KEY)
    system_prompt_generator = SystemPromptGenerator(
        background=[
            "Você é um inspetor de dados de um portal de cinema.",
            "Sua tarefa é verificar se o filme vinculado no TMDB corresponde ao "
            "filme descrito pelos cinemas que o exibem - filmes com o mesmo "
            "título em português são frequentemente vinculados errado.",
        ],
        steps=[
            "Compare diretor, ano, país e gênero do TMDB com o texto das sessões.",
            "Se algo não bate, use as ferramentas disponíveis para investigar antes de concluir.",
            "Só conclua 'fixed' depois de identificar um tmdb_id correto usando "
            "search_tmdb_candidates/get_tmdb_details - nunca invente um id.",
            "Se não tiver certeza, conclua 'needs_review' em vez de arriscar um palpite.",
        ],
        output_instructions=[
            "Responda apenas com a próxima ação: um dos tools disponíveis, ou "
            "'conclude' acompanhado do veredito final.",
        ],
    )
    return AtomicAgent[OrchestratorInput, OrchestratorDecision](
        config=AgentConfig(
            client=client,
            model=model_id,
            system_prompt_generator=system_prompt_generator,
            history=ChatHistory(),
            assistant_role="model",
        )
    )
```

Leave `_attach_debug_hooks` and `_dispatch_tool` unchanged. Replace `inspect_movie` (around line 396) with:

```python
def inspect_movie(movie: Movie) -> InspectionOutcome:
    """Runs the orchestrator's bounded tool-calling loop for one movie and
    returns the resulting outcome. If `verdict.status == "fixed"`, the
    movie's TMDB link has already been updated and committed. If the
    current model is rate-limited, retries the whole inspection with the
    next model in GEMINI_MODEL_PRIORITY, starting from a clean slate rather
    than resuming a partial tool-calling loop."""
    allowed_screening_ids = {s.id for s in movie.screenings}

    def call(model_id):
        return _run_inspection_loop(model_id, movie, allowed_screening_ids)

    return call_with_fallback(call, _is_rate_limited)


def _run_inspection_loop(
    model_id: str, movie: Movie, allowed_screening_ids: set
) -> InspectionOutcome:
    agent_input = OrchestratorInput(
        movie_title=movie.title,
        tmdb_original_title=movie.original_title,
        tmdb_release_year=movie.release_year,
        tmdb_original_language=movie.original_language,
        tmdb_directors=[d.name for d in movie.directors],
        tmdb_countries=[c.name for c in movie.countries],
        tmdb_genres=[g.name for g in movie.genres],
        screenings=[
            ScreeningContext(
                screening_id=s.id, cinema_name=s.cinema.name, description=s.description
            )
            for s in movie.screenings
        ],
    )
    observed_tmdb_ids: set = set()
    agent = _build_agent(model_id)
    _attach_debug_hooks(agent, movie)

    for turn in range(1, MAX_TOOL_CALLS + 1):
        decision = agent.run(agent_input)
        logger.debug(
            "Filme %d ('%s') – turno %d/%d: ação=%s",
            movie.id,
            movie.title,
            turn,
            MAX_TOOL_CALLS,
            decision.action,
        )

        if decision.action == "conclude":
            if decision.verdict is None:
                agent_input.observations.append(
                    "Ação 'conclude' enviada sem veredito; forneça o veredito."
                )
                continue
            return _apply_verdict(movie, decision.verdict, observed_tmdb_ids)

        observation, ids = _dispatch_tool(decision, allowed_screening_ids)
        logger.debug(
            "Filme %d ('%s') – turno %d: tool=%s observação=%s",
            movie.id,
            movie.title,
            turn,
            decision.action,
            observation[:200],
        )
        observed_tmdb_ids.update(ids)
        agent_input.observations.append(observation)

    logger.info(
        "Filme %d ('%s') – inspeção inconclusiva após %d chamadas de ferramenta",
        movie.id,
        movie.title,
        MAX_TOOL_CALLS,
    )
    return InspectionOutcome(
        status="needs_review",
        reasoning=f"Inspeção inconclusiva após {MAX_TOOL_CALLS} chamadas de ferramenta.",
    )
```

No changes are needed in `run_pipeline`: its existing `except Exception as exc:` block (around line 492) already catches `AllGeminiModelsExhausted` (a subclass of `Exception`) and records `status="error"`, exactly like it does for any other inspection failure today.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest flask_backend/tests/test_service/test_movie_inspector.py -v`
Expected: PASS (the whole file — the pre-existing tests that `patch.object(movie_inspector, "_build_agent", return_value=fake_agent)` are unaffected, since `MagicMock` accepts the new `model_id` argument regardless of the patched target's original signature, and a single successful `call_with_fallback` attempt behaves exactly like the old direct call)

- [ ] **Step 5: Lint and format**

Run: `uv run ruff check --fix flask_backend/service/movie_inspector.py flask_backend/tests/test_service/test_movie_inspector.py && uv run ruff format flask_backend/service/movie_inspector.py flask_backend/tests/test_service/test_movie_inspector.py`

- [ ] **Step 6: Commit**

```bash
git add flask_backend/service/movie_inspector.py flask_backend/tests/test_service/test_movie_inspector.py
git commit -m "feat: retry inspect_movie with the next Gemini model on rate limit"
```

---

### Task 6: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest`
Expected: PASS, no failures or errors, no tests skipped due to import errors.

- [ ] **Step 2: Run coverage to confirm nothing regressed**

Run: `uv run coverage run -m pytest && uv run coverage report -m`
Expected: report generates cleanly; `flask_backend/service/gemini_models.py`, `flask_backend/service/gemini_api.py`, `scrapers/llms.py`, and `flask_backend/service/movie_inspector.py` show coverage consistent with the rest of the codebase (no large uncovered blocks introduced by this change).

- [ ] **Step 3: Run the full lint/format/complexity suite**

Run:
```bash
uv run ruff check --fix
uv run ruff format
uv run vulture flask_backend scrapers cinemaempoa.py vulture_whitelist.py --exclude "*/tests/*" --min-confidence 80
uv run xenon --max-absolute B --max-modules A --max-average A flask_backend scrapers --exclude "*/tests/*"
```
Expected: `ruff check`/`ruff format` report no changes needed after Task 1–5 already ran them per-file; `vulture` reports no new dead code (in particular, confirm `Gemini.MODEL` and the old `_build_llm` model-name validation are fully gone, not just unreferenced); `xenon` passes (the new `_run_inspection_loop` split in Task 5 should, if anything, reduce `movie_inspector.py`'s complexity by shrinking `inspect_movie`).

- [ ] **Step 4: Grep for any remaining hardcoded `gemini-2.5-flash` reference outside tests**

Run: `grep -rn "gemini-2.5-flash" --include="*.py" . | grep -v "/tests/"`
Expected: no output — every non-test reference to the literal model string should now live only inside `GEMINI_MODEL_PRIORITY` in `flask_backend/service/gemini_models.py` (which spells it `"gemini-2.5-flash"` as one of the seven list entries, so a match there is fine; anywhere else is a leftover to fix).

No commit for this task — it's a verification pass over the four commits already made in Tasks 1–5. If any step fails, fix it within the relevant task's files and amend that task's commit only if you're still actively working that task's changes; otherwise create a new small fix commit.
