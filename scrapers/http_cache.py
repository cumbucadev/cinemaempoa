import os
from typing import Callable

import requests

from flask_backend.env_config import APP_ENVIRONMENT
from flask_backend.utils.enums.environment import EnvironmentEnum


def _dev_cache_enabled() -> bool:
    return APP_ENVIRONMENT != EnvironmentEnum.PRODUCTION


def fetch_page(cache_path: str, fetch: Callable[[], requests.Response]) -> str:
    """Returns contents from cache_path if present (outside production), otherwise
    calls fetch() and, outside production, saves the response to cache_path."""
    if _dev_cache_enabled() and os.path.exists(cache_path):
        with open(cache_path) as f:
            return f.read()

    response = fetch()
    response.raise_for_status()

    if _dev_cache_enabled():
        cache_dir = os.path.dirname(cache_path)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, "w") as f:
            f.write(response.text)

    return response.text
