import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup


class Capitolio:
    def __init__(self):
        self.url = "http://www.capitolio.org.br/programacao"
        self.dir = os.path.join("capitolio")

        if not os.path.exists(self.dir):
            os.mkdir(self.dir)

        self.soup = BeautifulSoup(self._todays_schedule_html(), "html.parser")

    def _get_todays_url(self):
        return f"{self.url}?date={self._get_today_ymd()}&room=Sala+de+Cinema"

    def _get_todays_file(self):
        return os.path.join(self.dir, f"{self._get_today_ymd()}.html")

    def _get_today_ymd(self):
        cur_datetime = datetime.now()
        cur_date = cur_datetime.strftime("%Y-%m-%d")
        return cur_date

    def _todays_schedule_html(self) -> str:
        if os.path.exists(self._get_todays_file()):
            with open(self._get_todays_file(), "r") as f:
                return f.read()

        r = requests.get(self._get_todays_url())
        r.raise_for_status()
        with open(self._get_todays_file(), "w") as f:
            f.write(r.text)
        return r.text

    def get_daily_features_json(self) -> str:
        features = []
        for movie in self.soup.find_all("div", class_="movie"):
            feature_film = {}

            # get the film poster
            poster = movie.find("img", class_="movie-poster")
            feature_film["poster"] = poster["src"]

            # get film start time
            movie_details = movie.css.select(".movie-info .movie-detail-blocks")
            for detail in movie_details:
                if "Horários: " in detail.get_text():
                    feature_film["time"] = detail.get_text()

            # get film pt-bt title
            movie_title = movie.css.select_one(".movie-info .movie-title")
            feature_film["title"] = movie_title.get_text()

            movie_subtitle = movie.css.select_one(".movie-info .movie-subtitle")

            # get film original title
            movie_original_title = movie_subtitle.get_text().split("(")[0].strip()
            feature_film["original_title"] = movie_original_title

            # get ticket price
            price_pattern = r".*?\((.*)\).*"
            price_match = re.search(price_pattern, movie_subtitle.get_text())
            # handle match not found (price is not in expected pattern)
            try:
                ticket_price = price_match.group(1)
            except (IndexError, AttributeError):
                ticket_price = "não informado"
            # handle finding unexpect value
            if not ticket_price.startswith("R$"):
                ticket_price = "não informado"
            feature_film["price"] = ticket_price

            # origin/year/length info
            movie_director = movie.css.select_one(
                ".movie-info .movie-director"
            ).get_text()
            general_info = ""
            for line in iter(movie_director.splitlines()):
                line = line.strip()
                if len(line) == 0:
                    continue
                if line.startswith("Direção"):
                    feature_film["director"] = (
                        line.replace(
                            "Direção:",
                            "",
                        )
                        .replace("Direção", "")
                        .strip()
                    )
                elif line.startswith("Classificação"):
                    feature_film["classification"] = line
                else:
                    general_info += f"\n{line}"
            feature_film["general_info"] = general_info

            movie_text = movie.css.select_one(".movie-info .movie-text")
            feature_film["excerpt"] = movie_text.get_text()

            read_more = movie.css.select_one(".movie-info .read-more")
            feature_film["read_more"] = "http://www.capitolio.org.br" + read_more["href"]
            features.append(feature_film)

        return features
