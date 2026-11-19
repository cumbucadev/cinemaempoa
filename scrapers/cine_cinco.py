import json
import os
import re
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from scrapers.http_cache import fetch_page
from scrapers.llm_cache import get_features_with_cache, hash_text
from scrapers.llms import CineCincoExtractorLLM

AGENDA_URL = "https://www.pucrs.br/cultura/agenda/"
VENUE = "cine cinco"


def drop_repeated_sessions(features):
    """Cine Cinco has a single room, so a session time names one screening.
    The monthly programme repeats the films that also get their own event
    page; keep each session where it was first announced."""
    seen = set()
    kept = []
    for feature in features:
        times = [time for time in feature["time"] if time not in seen]
        seen.update(times)
        if times:
            kept.append({**feature, "time": times})
    return kept


class CineCinco:
    def __init__(self):
        self.url = "https://www.pucrs.br/cultura/projetos/cine-cinco/"
        self.dir = os.path.join("cine-cinco")
        self.todays_dir = os.path.join(self.dir, self._get_today_ymd())
        os.makedirs(self.todays_dir, exist_ok=True)
        # One LLM cache per event page, so only the page that changed goes
        # back to Gemini.
        self.cache_dir = os.path.join(self.dir, "cache")

    def _get_today_ymd(self):
        cur_datetime = datetime.now()
        return cur_datetime.strftime("%Y-%m-%d")

    def _get_url_content(self, file, url):
        """Returns contents from file, or GET from url and save to file"""
        return fetch_page(
            file,
            lambda: requests.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) "
                        "Gecko/20100101 Firefox/116.0"
                    ),
                },
                timeout=(10, 30),
            ),
        )

    def _get_event_urls(self):
        """The Cine Cinco events on the PUCRS cultural agenda, which lists the
        ongoing and upcoming events. The project page stopped carrying the
        programme, and the event slugs follow no fixed pattern, so an event
        counts when its title or venue names Cine Cinco."""
        html = self._get_url_content(
            os.path.join(self.todays_dir, "agenda.html"), AGENDA_URL
        )
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for item in soup.select("div.item"):
            link = item.select_one('a[href*="/evento/"]')
            if link is None or VENUE not in _normalize(item.get_text(" ")):
                continue
            if link["href"] not in urls:
                urls.append(link["href"])
        return urls

    def _get_event_text(self, url):
        """The event post's text, preceded by the event's date range: the
        sessions are written without a year, the date range has one."""
        slug = url.rstrip("/").split("/")[-1]
        html = self._get_url_content(
            os.path.join(self.todays_dir, "events", f"{slug}.html"), url
        )
        soup = BeautifulSoup(html, "html.parser")
        post = soup.select_one("div.content div.col-xs-9")
        if post is None:
            raise ValueError(
                f"Could not find the post body on {url}. "
                "The page structure may have changed."
            )
        share = post.select_one("div.compartilhe-noticia")
        if share is not None:
            # Below the share buttons the page lists other events.
            for tag in share.find_next_siblings():
                tag.decompose()
            share.decompose()
        for tag in post(["script", "style"]):
            tag.decompose()

        text = _collapse_blank_lines(post.get_text())
        event_info = soup.select_one("div.infos-evento")
        if event_info is not None:
            info = _collapse_blank_lines(event_info.get_text())
            text = f"Informações do evento:\n{info}\n\n{text}"
        return text

    def _extract_features(self, text, url):
        year = datetime.now().year
        gemini = CineCincoExtractorLLM()
        gemini_output_str = gemini.extract_screenings_from_text(year, text)
        if gemini_output_str is None:
            # LLM call failed (rate limit / error) - the llm_cache helper falls
            # back to the last known-good features rather than importing nothing.
            return None
        gemini_output = json.loads(gemini_output_str)

        return [
            {
                "poster": movie.get("image_url"),
                "time": movie.get("screening_dates"),
                "title": movie.get("title"),
                "director": movie.get("director"),
                "classification": movie.get("classification"),
                "general_info": movie.get("general_info"),
                "excerpt": movie.get("excerpt"),
                "read_more": url,
            }
            for movie in gemini_output["movies"]
        ]

    def _get_event_features(self, url):
        text = self._get_event_text(url)
        cache_file = os.path.join(self.cache_dir, f"{hash_text(url)[:16]}.json")
        return get_features_with_cache(
            cache_file, text, lambda: self._extract_features(text, url)
        )

    def get_daily_features_json(self):
        features = []
        for url in self._get_event_urls():
            try:
                features += self._get_event_features(url)
            except requests.exceptions.RequestException as e:
                print(f"Cine Cinco: evento inacessível {url} ({e})", file=sys.stderr)
        return drop_repeated_sessions(features)


def _normalize(text):
    return " ".join(text.split()).casefold()


def _collapse_blank_lines(text):
    lines = (line.strip() for line in text.splitlines())
    return re.sub(r"\n{2,}", "\n", "\n".join(line for line in lines if line))
