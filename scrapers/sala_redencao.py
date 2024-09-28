import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from utils import get_formatted_day_str, string_is_day


class SalaRedencao:
    def __init__(self, date: str | None = None):
        if date:
            self.date = date
        else:
            self.date = self._get_today_ymd()

        self.url = "https://www.ufrgs.br/difusaocultural/salaredencao/"
        self.events = []

        self.dir = os.path.join("sala-redencao")
        os.makedirs(self.dir, exist_ok=True)

        self.scrape_dir = os.path.join(self.dir, self.date)
        os.makedirs(self.scrape_dir, exist_ok=True)

    def _get_today_ymd(self):
        cur_datetime = datetime.now()
        cur_date = cur_datetime.strftime("%Y-%m-%d")
        return cur_date

    def _get_todays_lp_url(self):
        return self.url

    def _get_lp_file(self):
        return os.path.join(self.scrape_dir, "landing.html")

    def _get_landing_page_html(self) -> str:
        return self._get_page_html(self._get_lp_file(), self.url)

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
        landing_page_soup = BeautifulSoup(self._get_landing_page_html(), "html.parser")
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
                if not string_is_day(date, self.date):
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
        """Looks for <p> tags with content in format

        <strong>MOVIE TILE</strong><br>
        (dir. director person | Country | 1950 | 123 min)<br>
        Short movie sinopsis.<br>
        <em>04 de setembro | segunda-feira | 16h</em><br>
        <em>06 de setembro | quarta-feira | 19h</em><br>
        <em>21 de setembro | quinta-feira | 16h</em><br><br>

        there might be multiple movies inside each <p> tag"""
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
                    if not string_is_day(date, self.date):
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

    def _get_next_sibling_with_content(self, tag):
        next_sibling = tag.next_sibling
        if next_sibling is None:
            # bail early if there are no more tags to parse
            return
        if next_sibling.text.strip() != "":
            return next_sibling
        return self._get_next_sibling_with_content(next_sibling)

    def _get_prev_sibling_with_content(self, tag):
        prev_sibling = tag.previous_sibling
        if prev_sibling.text.strip() != "":
            return prev_sibling
        return self._get_prev_sibling_with_content(prev_sibling)

    def _parse_blog_post_alternate_format(self, blog_post_soup, blog_post_url):
        """Looks for movies in the following format

        <p><strong>13 de setembro</strong></p>
        <p><strong>MOVIE TITLE</strong></p>
        <p>(Country, 2022, 1h15min. Direção: director person. Distribuição: Something Something.)</p>
        <p><strong>Temas: </strong>Various. Dot. Separated. Words.</p>
        <p><strong>Sinopse: </strong> Short movie description.</p>

        Returns the first parsed match."""
        p_tags = blog_post_soup.find("div", class_="content-inner").find_all("p")
        current_day_str = get_formatted_day_str(self.date)
        for p_tag in p_tags:
            if not p_tag.text.startswith(current_day_str):
                continue
            # found a movie that screens today

            # next tag with content is the title
            title_tag = self._get_next_sibling_with_content(p_tag)
            if title_tag is None:
                continue
            title = title_tag.text

            # next tag should be movie release info in format
            # (Country, 2022, 1h15min. Direção: Director Person. Distribuição: Something Something.)
            release_info_tag = self._get_next_sibling_with_content(title_tag)
            release_info = release_info_tag.text.split(".")
            for idx, info_n in enumerate(release_info):
                info = info_n.strip()
                if idx == 0:
                    general_info = info.lstrip("(")
                    continue
                if not info.startswith("Direção: "):
                    continue
                director = info.replace("Direção: ", "")

            excerpt = None
            curr_tag = self._get_next_sibling_with_content(release_info_tag)
            while excerpt is None:
                curr_tag = self._get_next_sibling_with_content(curr_tag)
                if curr_tag.text.startswith("Sinopse"):
                    excerpt = curr_tag.text

            # backtrack over <p> tags in search for screening time
            time = ""
            prev_tag = self._get_prev_sibling_with_content(p_tag)
            while time == "" and prev_tag is not None:
                prev_tag = self._get_prev_sibling_with_content(prev_tag)
                screening_time_match = re.match(
                    rf"^Dia {current_day_str},[\w\s-]+, às (\d{{2}}h(\d{{2}})?)",
                    prev_tag.text,
                )
                if screening_time_match:
                    time = screening_time_match[1]

            return {
                "poster": "",
                "time": time,
                "title": title,
                "original_title": "",
                "price": "",
                "director": director,
                "classification": "",
                "general_info": general_info,
                "excerpt": excerpt,
                "read_more": blog_post_url,
            }
        return None

    def _get_events_blog_post_html(self):
        events_html_dir = os.path.join(self.scrape_dir, "events")
        os.makedirs(events_html_dir, exist_ok=True)
        features = []
        for event_url in self.events:
            event_url_stripped = event_url.rstrip("/")
            event_slug = f"{event_url_stripped.split('/')[-1]}.html"
            event_file = os.path.join(events_html_dir, event_slug)
            event_html = self._get_page_html(event_file, event_url)

            event_soup = BeautifulSoup(event_html, "html.parser")
            blog_features = self._parse_blog_post_by_html(event_soup, event_url)

            if len(blog_features) == 0:
                # try another format
                feature = self._parse_blog_post_alternate_format(event_soup, event_url)
                if feature is not None:
                    blog_features.append(feature)

            if len(blog_features) == 0:
                # try to parse raw text content from the html
                blog_features = self._parse_blog_post_with_regex(event_soup, event_url)

            features = features + blog_features
        return features

    def get_daily_features_json(self) -> str:
        self._get_events_blog_post_url()
        return self._get_events_blog_post_html()
