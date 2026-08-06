import os
import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from scrapers.http_cache import fetch_page


class Capitolio:
    def __init__(self):
        self.url = "https://www.capitolio.org.br"
        self.dir = os.path.join("capitolio")

        if not os.path.exists(self.dir):
            os.mkdir(self.dir)

    def _day_url(self, day):
        return (
            f"{self.url}/programacao/?starting_date={day}"
            f"&date={day}&room=Sala+de+Cinema"
        )

    def _day_file(self, day) -> str:
        return os.path.join(self.dir, f"{day}.html")

    def _day_schedule_html(self, day) -> str:
        return fetch_page(self._day_file(day), lambda: requests.get(self._day_url(day)))

    def get_daily_features_json(self):
        """Deprecated: Use get_weekly_features_json() instead"""
        return self.get_weekly_features_json()

    def get_weekly_features_json(self):
        cur_day = datetime.now()
        features = []
        while True:
            soup = BeautifulSoup(
                self._day_schedule_html(cur_day.strftime("%Y-%m-%d")), "html.parser"
            )
            movies_div = soup.find_all("div", class_="movie")
            if cur_day.weekday() != 0 and len(movies_div) == 0:
                break
            for movie in movies_div:
                # get film pt-br title
                movie_title_tag = movie.css.select_one(".movie-info .movie-title")
                movie_title = movie_title_tag.get_text()

                already_scrapped = False
                feature_film = {"time": []}
                for f in features:
                    if f["title"] == movie_title:
                        feature_film = f
                        already_scrapped = True
                        break

                if not already_scrapped:
                    feature_film["title"] = movie_title

                    # get the film poster
                    poster = movie.find("img", class_="movie-poster")
                    feature_film["poster"] = poster["src"]

                    # Capitólio splits movie metadata across two elements:
                    # .movie-subtitle (title/price line) and .movie-director
                    # (origin/year/duration, Direção:, Classificação:, etc).
                    # We keep this text as-is rather than parsing it into
                    # separate fields - it all ends up concatenated into one
                    # Screening.description string downstream anyway.
                    movie_subtitle = movie.css.select_one(".movie-info .movie-subtitle")
                    movie_director_block = movie.css.select_one(
                        ".movie-info .movie-director"
                    )

                    general_info_lines = []
                    if movie_subtitle:
                        subtitle_text = movie_subtitle.get_text().strip()
                        if subtitle_text:
                            general_info_lines.append(subtitle_text)
                    if movie_director_block:
                        for line in movie_director_block.get_text("\n").splitlines():
                            line = line.strip()
                            if line:
                                general_info_lines.append(line)
                    feature_film["general_info"] = "\n".join(general_info_lines)

                    movie_text = movie.css.select_one(".movie-info .movie-text")
                    feature_film["excerpt"] = (
                        movie_text.get_text().strip() if movie_text else ""
                    )

                    read_more = movie.css.select_one(".movie-info .read-more")
                    feature_film["read_more"] = f"{self.url}{read_more['href']}"

                # get film start time, regardless of whether we already
                # scrapped it on a previous day or not
                movie_details = movie.css.select(".movie-info .movie-detail-blocks")
                for detail in movie_details:
                    if "Horários: " in detail.get_text():
                        match = re.search(
                            r"Horários:\s*([0-9]{2}:[0-9]{2}h)", detail.get_text()
                        )
                        if match:
                            feature_film["time"] = feature_film["time"] + [
                                f"{cur_day.strftime('%Y-%m-%d')}T{match.group(1)}"
                            ]
                        else:
                            feature_film["time"] = feature_film["time"] + [
                                "Não informado"
                            ]
                features.append(feature_film)
            cur_day = cur_day + timedelta(days=1)

        return features
