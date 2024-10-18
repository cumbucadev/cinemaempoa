import csv
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

data_dir = Path(__file__).parent / "country_data" / "data"


@lru_cache(1)
def available_languages() -> List[str]:
    return sorted(x.name for x in data_dir.iterdir() if (x / "country.csv").exists())


@lru_cache()
def countries_for_language(
    lang: str, encoding: Optional[str] = "utf8"
) -> List[Tuple[str, str]]:
    path = data_dir / _clean_lang(lang) / "country.csv"
    with path.open(encoding=encoding) as file_:
        return [(row["id"], row["value"]) for row in csv.DictReader(file_)]


def _clean_lang(lang: str) -> str:
    cleaned_lang = lang.replace("-", "_").lower()
    try:
        return _languages()[cleaned_lang]
    except KeyError:
        raise ValueError("Language {} not found".format(lang)) from None


@lru_cache(1)
def _languages() -> Dict[str, str]:
    return {language.lower(): language for language in available_languages()}
