import locale
import os
import unicodedata
from datetime import date, datetime, time as dt_time

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class CinematecaPauloAmorim:
    def __init__(self):
        self.url = "https://www.cinematecapauloamorim.com.br"
        self.grade_url = "https://www.cinematecapauloamorim.com.br/grade-semanal"
        self.programacao_url = "https://www.cinematecapauloamorim.com.br/programacao"
        self.movies = []  # saves movies scrapped from /programacao page

        self.dir = os.path.join("paulo-amorim")
        if not os.path.exists(self.dir):
            os.mkdir(self.dir)

        self.todays_dir = os.path.join(self.dir, self._get_today_ymd())
        if not os.path.exists(self.todays_dir):
            os.mkdir(self.todays_dir)

    def _get_today_ymd(self):
        cur_datetime = datetime.now()
        cur_date = cur_datetime.strftime("%Y-%m-%d")

        return cur_date

    def _get_page_html(self, file, url):
        """Returns contents from file, or GET from url and save to file"""
        if os.path.exists(file):
            with open(file, "r") as f:
                return f.read()

        session = requests.Session()
        retry = Retry(connect=3, backoff_factor=0.5)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        r = session.get(
            url,
            headers={
                "Host": "www.cinematecapauloamorim.com.br",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/116.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3",
                "Accept-Encoding": "gzip, deflate",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache",
            },
        )

        r.raise_for_status()
        with open(file, "w") as f:
            f.write(r.text)
        return r.text

    def _get_movies_on_programacao(self):
        # if a movie is listed under programacao, we
        # assume it is being featured that week
        programacao_html = self._get_page_html(
            os.path.join(self.todays_dir, "programacao.html"), self.programacao_url
        )
        programacao_soup = BeautifulSoup(programacao_html, "html.parser")
        ticket_links = programacao_soup.css.select("a.link-default > .ticket")
        movies = []
        for ticket_link in ticket_links:
            genre = ticket_link.css.select_one(".ticket-foto").css.select_one(".generos")
            if genre is not None:
                genre = genre.text.strip("\n")

            movie = {
                "poster": ticket_link.css.select_one(".ticket-foto")["style"]
                .replace(
                    "background-image:url(", "https://www.cinematecapauloamorim.com.br/"
                )
                .rstrip(")"),
                "title": ticket_link.css.select_one("h5").text,
                "general_info": ticket_link.css.select_one("h5")
                .parent.find_next_sibling()
                .find_next_sibling()
                .text.strip()
                .replace("\t", ""),
                "director": ticket_link.css.select_one("h5")
                .parent.find_next_sibling()
                .text.strip("\n"),
                "classification": ticket_link.css.select_one(".ticket-foto")
                .css.select_one(".classificacao")
                .text.strip("\n")
                .replace("\n", " "),
                "excerpt": "",
                "time": [],
                "read_more": f"{self.url}/{ticket_link.parent['href']}",
                "genre": genre,
                "room": ticket_link.css.select_one("h5")
                .parent.find_next_sibling()
                .find_next_sibling()
                .find_next_sibling()
                .text.strip("\n"),
            }
            movies.append(movie)
        self.movies = movies

    def _get_movie_excerpt(self):
        for movie in self.movies:
            movie_url_id = movie["read_more"].rstrip("/").split("/")[-1]
            movie_html = self._get_page_html(
                os.path.join(self.todays_dir, f"{movie_url_id}.html"),
                movie["read_more"],
            )
            movie_soup = BeautifulSoup(movie_html, "html.parser")

            movie["general_info"] = []

            info = (
                movie_soup.css.select_one("#mainbar h2")
                .find_next_sibling()
                .css.select_one("strong em")
            )

            if info is not None:
                movie["general_info"].append(info.text)

            if movie["room"] is not None:
                movie["general_info"].append(movie["room"])

            if movie["genre"] is not None:
                movie["general_info"].append(movie["genre"])

            movie["general_info"] = " | ".join(movie["general_info"])

            movie["excerpt"] = (
                movie_soup.css.select_one("#mainbar h2")
                .find_next_sibling()
                .find_next_sibling()
                .text
            )

    def _get_today_str(self):
        """returns de current day in
        {XX de mês} format, with and without a leading zero
        on the day. ex
            03 de setembro, 3 de setembro"""
        locale.setlocale(locale.LC_ALL, "pt_BR.UTF-8")
        today_str = date.today().strftime("%d de %B")
        today_str_no_leading_zero = date.today().strftime("%-d de %B")
        locale.setlocale(locale.LC_ALL, locale.getdefaultlocale())
        return today_str.lower(), today_str_no_leading_zero.lower()

    def _get_todays_features(self):
        grade_html = self._get_page_html(
            os.path.join(self.todays_dir, "grade.html"), self.grade_url
        )
        grade_soup = BeautifulSoup(grade_html, "html.parser")
        today_str, today_str_no_leading_zero = self._get_today_str()
        for p_tag in grade_soup.find_all("p"):
            strong_tag = p_tag.find("strong")
            if strong_tag is None:
                continue
            strong_text = unicodedata.normalize("NFKC", strong_tag.text)
            movie_matches_today = strong_text.lower().startswith(
                today_str
            ) or strong_text.lower().startswith(today_str_no_leading_zero)
            if not movie_matches_today:
                continue

            # they might be using the following html structure
            # <p>
            #   <strong> 8 de dezembro | sexta </strong>
            # </p>
            # <table border="0" cellpadding="0" cellspacing="0" style="width:567px">
            #   <tbody>
            #       <tr>
            #           <td>14h30</td>
            #           <td>Sala 2</td>
            #           <td>Filmes em competição Festival Cinema Negro em Ação</td>
            #       </tr>
            #       <tr>
            #           ...
            #       </tr>
            #   </tbody>
            # </table>

            feature_timetable = p_tag.find_next_sibling("table")
            if feature_timetable:
                for feature_tr in feature_timetable.find_all("tr"):
                    feature_tds = feature_tr.find_all("td")
                    for movie in self.movies:
                        if movie["title"].lower() == feature_tds[2].text.lower():
                            # Movie will be featured today
                            time_str = (
                                unicodedata.normalize("NFKC", feature_tds[0].text)
                                .strip("\n")
                                .strip()
                                .split(" ")[0]
                            )
                            hour_str, min_str = time_str.split("h")
                            if min_str:
                                parsed_time = dt_time(int(hour_str), int(min_str))
                            else:
                                parsed_time = dt_time(int(hour_str))
                            movie["time"].append(parsed_time)
            else:
                for strong in p_tag.find_all("strong"):
                    for movie in self.movies:
                        if movie["title"].lower() != strong.text.lower():
                            continue
                        # Movie will be featured today
                        # Lines are in the format
                        # 14h30 EH: Retratos Fantasmas, Kleber Mendonça Filho
                        time_str = (
                            unicodedata.normalize(
                                "NFKC", strong.find_previous_sibling(string=True)
                            )
                            .strip("\n")
                            .strip()
                            .split(" ")[0]
                        )
                        hour_str, min_str = time_str.split("h")
                        if min_str:
                            parsed_time = dt_time(int(hour_str), int(min_str))
                        else:
                            parsed_time = dt_time(int(hour_str))

                        movie["time"].append(parsed_time)
        features = [movie for movie in self.movies if len(movie["time"]) > 0]
        sorted_features = sorted(features, key=lambda feature: feature["time"][0])
        for feature in sorted_features:
            feature["time"] = "/ ".join(
                [parsed_time.strftime("%Hh%M") for parsed_time in feature["time"]]
            )
        return sorted_features

    def get_daily_features_json(self):
        self._get_movies_on_programacao()
        self._get_movie_excerpt()
        return self._get_todays_features()
