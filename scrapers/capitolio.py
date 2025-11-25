import os
import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup


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
        if os.path.exists(self._day_file(day)):
            with open(self._day_file(day), "r") as file:
                return file.read()
        response = requests.get(self._day_url(day))
        response.raise_for_status()

        with open(self._day_file(day), "w") as file:
            file.write(response.text)
        return response.text

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
                # remove the latest downloaded file so it is redownloaded again next week
                os.remove(self._day_file(cur_day.strftime("%Y-%m-%d")))
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

                    movie_subtitle = movie.css.select_one(".movie-info .movie-subtitle")

                    # get film original title
                    if movie_subtitle:
                        if re.search(r"[|]", movie_subtitle.get_text()):
                            movie_original_title = (
                                movie_subtitle.get_text().split("|")[0].strip()
                            )
                            feature_film["original_title"] = movie_original_title
                        elif re.search(r"[(]", movie_subtitle.get_text()):
                            movie_original_title = (
                                movie_subtitle.get_text().split("(")[0].strip()
                            )
                            feature_film["original_title"] = movie_original_title
                        else:
                            feature_film["original_title"] = "Não informado"

                    # get ticket price
                    get_price = movie.css.select_one(
                        ".movie .movie-info .movie-subtitle"
                    )

                    if re.search(r"[R$]", get_price.get_text()):
                        try:
                            ticket_price = get_price.get_text().split("|")[1].strip()
                            feature_film["price"] = ticket_price
                        except (IndexError, AttributeError):
                            ticket_price = get_price.get_text()
                            feature_film["price"] = ticket_price
                    elif re.search(r"[(]", get_price.get_text()):
                        ticket_price = (
                            get_price.get_text().split("(")[1].replace(")", "").strip()
                        )
                        feature_film["price"] = ticket_price
                    else:
                        feature_film["price"] = "Não informado"

                    # origin/year/length info
                    movie_director = movie.css.select_one(
                        ".movie-info .movie-text"
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
                                f'{cur_day.strftime("%Y-%m-%d")}T{match.group(1)}'
                            ]
                        else:
                            feature_film["time"] = feature_film["time"] + [
                                "Não informado"
                            ]
                features.append(feature_film)
            cur_day = cur_day + timedelta(days=1)

        return features
