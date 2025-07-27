import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString, ResultSet

from utils import is_monday
from .llm import CineBancariosLLM


class CineBancarios:
    def __init__(self, api_key: str):
        self.url = "http://cinebancarios.blogspot.com/feeds/posts/default?alt=rss"
        self.dir = os.path.join("cinebancarios")
        self.llm = CineBancariosLLM(api_key)

        if not os.path.exists(self.dir):
            os.mkdir(self.dir)

        self.todays_dir = os.path.join(self.dir, self._get_today_ymd())
        if not os.path.exists(self.todays_dir):
            os.mkdir(self.todays_dir)

    def _get_url_content(self, file, url):
        """Returns contents from file, or GET from url and save to file"""
        if os.path.exists(file):
            with open(file, "r") as f:
                return f.read()
        r = requests.get(url)
        r.raise_for_status()
        with open(file, "w") as f:
            f.write(r.text)
        return r.text

    def _get_today_ymd(self):
        cur_datetime = datetime.now()
        cur_date = cur_datetime.strftime("%Y-%m-%d")

        return cur_date


    def _get_current_blog_post_soup(self):
        rss_filepath = os.path.join(self.todays_dir, "feed.xml")
        blog_rss = self._get_url_content(rss_filepath, self.url)
        root = ET.fromstring(blog_rss)
        for child in root[0]:
            if child.tag != "item":
                continue
            for item_prop in child:
                if item_prop.tag != "description":
                    continue

                return BeautifulSoup(item_prop.text, "html.parser")


    def _convert_llm_output_to_features(self, program) -> list:
        """Convert LLM output to the expected features format."""
        features = []
        for movie in program.movies:
            feature = {
                "poster": movie.image_url or "",
                "title": movie.title,
                "general_info": movie.general_info or "",
                "director": movie.director or "",
                "classification": movie.classification or "",
                "excerpt": movie.excerpt or "",
                "time": " / ".join(f"{d.time}" for d in movie.screening_dates),
                "read_more": None
            }
            features.append(feature)
        return features

    def get_daily_features_json(self):
        current_post_soup = self._get_current_blog_post_soup()
        if not current_post_soup:
            return {
                "url": "http://cinebancarios.blogspot.com",
                "cinema": "CineBancários",
                "slug": "cinebancarios",
                "warning": "Não há sessões nas segundas-feiras" if is_monday() else False,
                "features": []
            }

        # Process the HTML content with LLM
        program = self.llm.process_html(str(current_post_soup))
        
        # Convert LLM output to expected format
        features = self._convert_llm_output_to_features(program)
        
        return {
            "url": "http://cinebancarios.blogspot.com",
            "cinema": "CineBancários",
            "slug": "cinebancarios",
            "warning": "Não há sessões nas segundas-feiras" if is_monday() else False,
            "features": features
        }
