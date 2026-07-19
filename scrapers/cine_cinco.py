import hashlib
import json
import os
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from scrapers.llms import CineCincoExtractorLLM


class CineCinco:
    def __init__(self):
        self.url = "https://www.pucrs.br/cultura/projetos/cine-cinco/"
        self.dir = os.path.join("cine-cinco")

        if not os.path.exists(self.dir):
            os.mkdir(self.dir)

        self.todays_dir = os.path.join(self.dir, self._get_today_ymd())
        if not os.path.exists(self.todays_dir):
            os.mkdir(self.todays_dir)

        self.cache_file = os.path.join(self.dir, "cache.json")

    def _get_today_ymd(self):
        cur_datetime = datetime.now()
        return cur_datetime.strftime("%Y-%m-%d")

    def _get_url_content(self, file, url):
        """Returns contents from file, or GET from url and save to file"""
        if os.path.exists(file):
            with open(file) as f:
                return f.read()
        r = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) "
                    "Gecko/20100101 Firefox/116.0"
                ),
            },
        )
        r.raise_for_status()
        with open(file, "w") as f:
            f.write(r.text)
        return r.text

    def _get_content_soup(self):
        """Returns the BeautifulSoup node for the page's `div.content` block,
        which holds the entire "Programação" section."""
        html_filepath = os.path.join(self.todays_dir, "page.html")
        html = self._get_url_content(html_filepath, self.url)
        soup = BeautifulSoup(html, "html.parser")
        content = soup.select_one("div.content.clearfix") or soup.select_one(
            "div.content"
        )
        if content is None:
            raise ValueError(
                "Could not find div.content on the Cine Cinco page. "
                "The page structure may have changed."
            )
        return content

    def _get_text_from_soup(self, soup):
        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()
        return soup.get_text()

    def _hash_text(self, text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _load_cache(self):
        if not os.path.exists(self.cache_file):
            return None
        try:
            with open(self.cache_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _save_cache(self, content_hash, features):
        with open(self.cache_file, "w") as f:
            json.dump(
                {
                    "content_hash": content_hash,
                    "features": features,
                    "updated_at": datetime.now().isoformat(),
                },
                f,
                ensure_ascii=False,
            )

    def get_daily_features_json(self):
        content_soup = self._get_content_soup()
        text = self._get_text_from_soup(content_soup)
        content_hash = self._hash_text(text)

        cache = self._load_cache()
        if cache is not None and cache.get("content_hash") == content_hash:
            # Page content hasn't changed since the last successful extraction -
            # skip the LLM call entirely and reuse the cached features.
            return cache["features"]

        year = datetime.now().year
        gemini = CineCincoExtractorLLM("gemini-2.5-flash")
        gemini_output_str = gemini.extract_screenings_from_text(year, text)
        if gemini_output_str is None:
            # LLM call failed (rate limit / error) - fall back to the last
            # known-good features rather than importing nothing.
            return cache["features"] if cache else []
        gemini_output = json.loads(gemini_output_str)

        features = []
        for movie in gemini_output["movies"]:
            feature = {
                "poster": movie.get("image_url"),
                "time": movie.get("screening_dates"),
                "title": movie.get("title"),
                "director": movie.get("director"),
                "classification": movie.get("classification"),
                "general_info": movie.get("general_info"),
                "excerpt": movie.get("excerpt"),
                "read_more": self.url,
            }
            features.append(feature)

        self._save_cache(content_hash, features)
        return features
