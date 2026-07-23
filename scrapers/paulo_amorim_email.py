import json
import os

from bs4 import BeautifulSoup
from imap_tools import AND, MailBox, MailMessageFlags

from flask_backend.env_config import (
    PAULO_AMORIM_EMAIL_ADDRESS,
    PAULO_AMORIM_EMAIL_APP_PASSWORD,
    PAULO_AMORIM_NEWSLETTER_SENDER_EMAIL,
)
from scrapers.llm_cache import hash_text, load_cache, save_cache
from scrapers.llms import PauloAmorimEmailExtractorLLM

IMAP_HOST = "imap.gmail.com"


class PauloAmorimEmail:
    def __init__(self):
        self.dir = os.path.join("paulo-amorim-email")
        if not os.path.exists(self.dir):
            os.mkdir(self.dir)

    def _get_text_from_html(self, html):
        soup = BeautifulSoup(html, "html.parser")
        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()
        return soup.get_text()

    def _extract_features(self, str_received_date, text):
        gemini = PauloAmorimEmailExtractorLLM("gemini-2.5-flash")
        gemini_output_str = gemini.extract_screenings_from_text(str_received_date, text)
        if gemini_output_str is None:
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
                "read_more": "https://www.cinematecapauloamorim.com.br",
            }
            for movie in gemini_output["movies"]
        ]

    def _connect(self):
        return MailBox(IMAP_HOST).login(
            PAULO_AMORIM_EMAIL_ADDRESS, PAULO_AMORIM_EMAIL_APP_PASSWORD
        )

    def _process_message(self, mailbox, msg):
        html = msg.html or msg.text
        text = self._get_text_from_html(html)
        content_hash = hash_text(text)
        cache_file = os.path.join(self.dir, f"{msg.uid}.json")
        cache = load_cache(cache_file)

        if cache is not None and cache.get("content_hash") == content_hash:
            movies = cache["features"]
        else:
            str_received_date = msg.date.strftime("%a, %d %b %Y %H:%M:%S %z")
            movies = self._extract_features(str_received_date, text)
            if movies is None:
                return None
            save_cache(cache_file, content_hash, movies)

        mailbox.flag(msg.uid, MailMessageFlags.SEEN, True)
        return movies

    def get_weekly_features_json(self):
        features = []
        with self._connect() as mailbox:
            messages = list(
                mailbox.fetch(
                    AND(seen=False, from_=PAULO_AMORIM_NEWSLETTER_SENDER_EMAIL),
                    mark_seen=False,
                )
            )
            for msg in messages:
                try:
                    movies = self._process_message(mailbox, msg)
                except Exception as e:
                    print(f"Error: {e}")
                    continue
                if movies is not None:
                    features.extend(movies)
        return features
