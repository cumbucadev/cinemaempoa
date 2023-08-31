import os
import re
import requests

from bs4 import BeautifulSoup
from datetime import datetime

from utils import string_is_current_day


class SalaRedencao:
    def __init__(self):
        self.url = "https://www.ufrgs.br/difusaocultural/salaredencao/"
        self.dir = os.path.join("sala-redencao")
        self.events = []

        if not os.path.exists(self.dir):
            os.mkdir(self.dir)

        self.todays_dir = os.path.join(self.dir, self._get_today_ymd())
        if not os.path.exists(self.todays_dir):
            os.mkdir(self.todays_dir)

    def _get_today_ymd(self):
        cur_datetime = datetime.now()
        cur_date = cur_datetime.strftime("%Y-%m-%d")
        return cur_date

    def _get_todays_lp_url(self):
        return self.url

    def _get_todays_lp_file(self):
        return os.path.join(self.todays_dir, "landing.html")

    def _get_todays_landing_page_html(self) -> str:
        return self._get_page_html(self._get_todays_lp_file(), self.url)

    def _get_page_html(self, file, url):
        """Returns contents from file, or GET from url and save to file"""
        if os.path.exists(file):
            with open(file, "r") as f:
                return f.read()
        r = requests.get(url)
        r.raise_for_status()
        with open(file, "w") as f:
            f.write(r.text)
        return r.text

    def _get_events_blog_post_url(self):
        landing_page_soup = BeautifulSoup(
            self._get_todays_landing_page_html(), "html.parser"
        )
        events_post_anchor_tag = landing_page_soup.css.select(
            "a.evcal_evdata_row.evo_clik_row"
        )
        for event_post_anchor_tag in events_post_anchor_tag:
            event_inner_url = event_post_anchor_tag["href"]

            if event_inner_url and event_inner_url not in self.events:
                self.events.append(event_inner_url)

    def _parse_blog_post_with_regex(self, event_soup, event_url):
        event_content_inner = event_soup.css.select_one("div.content-inner")
        # pattern = r"([\w\s]+)\(dir\. ([\w\s]+) \| ([\w\s]+) \| (\d{4}) \| (\d+ min)\)(.*?)\d{1,2} de [a-z]+ \| [\w\-]+ \| \d{1,2}[hH]"
        pattern = r"([\w\s]+)\(dir\. ([\w\s]+) \| ([\w\s]+) \| (\d{4}) \| (\d+ min)\)(.*?)((?:\d{1,2} de [a-z]+ \| [\w\-]+ \| \d{1,2}[hH]\s*)+)"
        matches = re.findall(pattern, event_content_inner.text, re.DOTALL)
        feats = []
        for movie in matches:
            screening_dates = re.findall(
                r"(\d{1,2} de [a-z]+ \| [\w\-]+ \| \d{1,2}[hH])", movie[6]
            )
            time = []
            for date in screening_dates:
                if not string_is_current_day(date):
                    continue
                time.append(date)

            if len(time) == 0:
                # no screenings today!
                continue

            title = movie[0].strip()
            director = movie[1].strip()
            countries = movie[2].strip()
            year = movie[3]
            duration = movie[4].strip()
            excerpt = movie[5].strip()

            feature = {
                "poster": "",
                "time": "\n".join(time),
                "title": title,
                "original_title": "",
                "price": "",
                "director": director,
                "classification": "",
                "general_info": countries + " / " + year + " / " + duration,
                "excerpt": excerpt,
                "read_more": event_url,
            }

            feats.append(feature)
        return feats

    def _parse_blog_post_by_html(self, blog_post_soup, blog_post_url):
        content_inner = blog_post_soup.find("div", class_="content-inner")
        p_tags = content_inner.find_all("p")
        feats = []
        pattern = r"([\w\s]+)\(dir\. ([\w\s]+) \| ([\w\s]+) \| (\d{4}) \| (\d+ min)\)(.*?)((?:\d{1,2} de [a-z]+ \| [\w\-]+ \| \d{1,2}[hH]\s*)+)"
        for p_tag in p_tags:
            matches = re.findall(pattern, p_tag.text, re.DOTALL)
            for movie in matches:
                screening_dates = re.findall(
                    r"(\d{1,2} de [a-z]+ \| [\w\-]+ \| \d{1,2}[hH])", movie[6]
                )
                time = []
                for date in screening_dates:
                    if not string_is_current_day(date):
                        continue
                    time.append(date)

                if len(time) == 0:
                    # no screenings today!
                    continue

                title = movie[0].strip()
                director = movie[1].strip()
                countries = movie[2].strip()
                year = movie[3]
                duration = movie[4].strip()
                excerpt = movie[5].strip()

                feature = {
                    "poster": "",
                    "time": "\n".join(time),
                    "title": title,
                    "original_title": "",
                    "price": "",
                    "director": director,
                    "classification": "",
                    "general_info": countries + " / " + year + " / " + duration,
                    "excerpt": excerpt,
                    "read_more": blog_post_url,
                }
                feats.append(feature)
        return feats

    def _get_events_blog_post_html(self):
        events_html_dir = os.path.join(self.todays_dir, "events")
        if not os.path.isdir(events_html_dir):
            os.mkdir(events_html_dir)
        features = []
        for event_url in self.events:
            event_url_stripped = event_url.rstrip("/")
            event_slug = f"{event_url_stripped.split('/')[-1]}.html"
            event_file = os.path.join(events_html_dir, event_slug)
            event_html = self._get_page_html(event_file, event_url)

            event_soup = BeautifulSoup(event_html, "html.parser")
            blog_features = self._parse_blog_post_by_html(event_soup, event_url)
            features = features + blog_features
        return features

    def get_daily_features_json(self) -> str:
        self._get_events_blog_post_url()
        return self._get_events_blog_post_html()
