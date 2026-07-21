import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from scrapers.http_cache import fetch_page
from scrapers.llm_cache import get_features_with_cache
from scrapers.llms import CineBancariosExtractorLLM


class CineBancarios:
    def __init__(self):
        self.url = "http://cinebancarios.blogspot.com/feeds/posts/default?alt=rss"
        self.dir = os.path.join("cinebancarios")
        self.pubDate = None

        if not os.path.exists(self.dir):
            os.mkdir(self.dir)

        self.todays_dir = os.path.join(self.dir, self._get_today_ymd())
        if not os.path.exists(self.todays_dir):
            os.mkdir(self.todays_dir)

        self.cache_file = os.path.join(self.dir, "cache.json")

    def _get_url_content(self, file, url):
        """Returns contents from file, or GET from url and save to file"""
        return fetch_page(file, lambda: requests.get(url))

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
                self.pubDate = child.find("pubDate").text
                self.postLink = child.find("link").text
                return BeautifulSoup(item_prop.text, "html.parser")

    def _get_text_from_soup(self, soup):
        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()
        return soup.get_text()

    def _extract_features(self, text):
        gemini = CineBancariosExtractorLLM("gemini-2.5-flash")
        gemini_output_str = gemini.extract_screenings_from_text(self.pubDate, text)
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
                "read_more": self.postLink,
            }
            for movie in gemini_output["movies"]
        ]

    def get_daily_features_json(self):
        soup = self._get_current_blog_post_soup()
        text = self._get_text_from_soup(soup)
        return get_features_with_cache(
            self.cache_file, text, lambda: self._extract_features(text)
        )
