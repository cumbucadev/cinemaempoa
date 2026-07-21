import hashlib
import json
from datetime import datetime
from typing import Callable, Optional


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_cache(cache_file: str) -> Optional[dict]:
    try:
        with open(cache_file) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def save_cache(cache_file: str, content_hash: str, features: list) -> None:
    with open(cache_file, "w") as f:
        json.dump(
            {
                "content_hash": content_hash,
                "features": features,
                "updated_at": datetime.now().isoformat(),
            },
            f,
            ensure_ascii=False,
        )


def get_features_with_cache(
    cache_file: str, text: str, extract: Callable[[], Optional[list]]
) -> list:
    """Returns cached features if `text`'s hash matches the last successful
    extraction; otherwise calls extract() (which should return parsed features,
    or None on failure) and updates the cache on success. Falls back to the
    last known-good features if extract() fails, or an empty list if there is
    no prior cache."""
    content_hash = hash_text(text)
    cache = load_cache(cache_file)
    if cache is not None and cache.get("content_hash") == content_hash:
        return cache["features"]

    features = extract()
    if features is None:
        return cache["features"] if cache else []

    save_cache(cache_file, content_hash, features)
    return features
