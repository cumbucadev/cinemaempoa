import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from flask_backend.env_config import DEEPSEEK_API_KEY
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
                self.pubDate = child.find("pubDate").text
                self.postLink = child.find("link").text
                return BeautifulSoup(item_prop.text, "html.parser")

    def _get_text_from_soup(self, soup):
        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()
        return soup.get_text()

    def get_daily_features_json(self):
        soup = self._get_current_blog_post_soup()
        text = self._get_text_from_soup(soup)
        gemini = CineBancariosExtractorLLM("gemini-2.5-flash")
        gemini_output_str = gemini.extract_screenings_from_text(self.pubDate, text)
        gemini_output = json.loads(gemini_output_str)
        if DEEPSEEK_API_KEY is not None:
            deepseek = CineBancariosExtractorLLM("deepseek-chat")
            deepseek_output = deepseek.extract_screenings_from_text(self.pubDate, text)

            if gemini_output != deepseek_output:
                # TODO: notify the website admin, we need to verify which one is correct
                pass
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
                "read_more": self.postLink,
            }
            features.append(feature)
        return features
