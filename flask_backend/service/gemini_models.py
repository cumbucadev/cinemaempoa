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
