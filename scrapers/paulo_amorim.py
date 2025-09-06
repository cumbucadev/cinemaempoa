import os
import re
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
        programacao_page = 1
        while True:
            programacao_html = self._get_page_html(
                os.path.join(self.todays_dir, f"programacao{programacao_page}.html"),
                f"{self.programacao_url}/pag/{programacao_page}",
            )
            programacao_soup = BeautifulSoup(programacao_html, "html.parser")
            ticket_links = programacao_soup.css.select("a.link-default > .ticket")
            if len(ticket_links) == 0:
                break
            movies = []
            for ticket_link in ticket_links:
                genre = ticket_link.css.select_one(".ticket-foto").css.select_one(
                    ".generos"
                )
                if genre is not None:
                    genre = genre.text.strip("\n")

                movie = {
                    "poster": ticket_link.css.select_one(".ticket-foto")["style"]
                    .replace(
                        "background-image:url(",
                        "https://www.cinematecapauloamorim.com.br/",
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
            self.movies = self.movies + movies
            programacao_page += 1

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

    def _parse_date_from_strong_text(self, strong_text):
        """Parse date from strong tag text like '30 de julho – quarta-feira' or '8 de dezembro | sexta'"""
        # Normalize the text
        normalized_text = unicodedata.normalize("NFKC", strong_text.lower())

        # Extract the date part (before the separator)
        if "–" in normalized_text:
            date_part = normalized_text.split("–")[0].strip()
        elif "|" in normalized_text:
            date_part = normalized_text.split("|")[0].strip()
        else:
            return None

        # Parse day and month
        try:
            # Handle formats like "30 de julho" or "8 de dezembro"
            parts = date_part.split(" de ")
            if len(parts) != 2:
                return None

            day = int(parts[0])
            month_name = parts[1]

            # Map month names to numbers
            month_map = {
                "janeiro": 1,
                "fevereiro": 2,
                "março": 3,
                "abril": 4,
                "maio": 5,
                "junho": 6,
                "julho": 7,
                "agosto": 8,
                "setembro": 9,
                "outubro": 10,
                "novembro": 11,
                "dezembro": 12,
            }

            if month_name not in month_map:
                return None

            month = month_map[month_name]
            year = datetime.now().year

            # Create date object
            return date(year, month, day)
        except (ValueError, KeyError):
            return None

    def _get_weekly_features(self):
        grade_html = self._get_page_html(
            os.path.join(self.todays_dir, "grade.html"), self.grade_url
        )
        grade_soup = BeautifulSoup(grade_html, "html.parser")

        # Reset movie times for new scraping
        for movie in self.movies:
            movie["time"] = []

        for p_tag in grade_soup.find_all("p"):
            # assume the first `<strong>` tag will have the day in the format `30 de julho – quarta-feira`
            strong_tag = p_tag.find("strong")
            if strong_tag is None:
                continue
            strong_text = unicodedata.normalize("NFKC", strong_tag.text)

            # Parse the date from the strong tag
            current_date = self._parse_date_from_strong_text(strong_text)
            if current_date is None:
                continue

            # we might be dealing with unformatted text inside <p> tags
            # <p>
            #     <strong>30 de julho – quarta-feira</strong>
            #     <br>
            #     14h30&nbsp;– EH&nbsp;–&nbsp;<a href="https://cinematecapauloamorim.com.br/programacao/2381/dreams">Dreams</a><br>
            #     14h45 – PA&nbsp;–&nbsp;<a href="https://cinematecapauloamorim.com.br/programacao/2395/vermiglio-a-noiva-da-montanha">Vermiglio </a><a href="https://cinematecapauloamorim.com.br/programacao/2428/iracema-uma-transa-amazonica">–</a><a href="https://cinematecapauloamorim.com.br/programacao/2395/vermiglio-a-noiva-da-montanha"> A Noiva da Montanha</a><br>
            #     15h&nbsp;– NL –&nbsp;<a href="https://cinematecapauloamorim.com.br/programacao/2406/um-lobo-entre-os-cisnes">Um Lobo Entre os Cisnes</a><br>
            #     16h45&nbsp;– EH&nbsp;–&nbsp;<a href="https://cinematecapauloamorim.com.br/programacao/2405/cazuza-boas-novas">Cazuza: Boas Novas</a><br>
            #     17h&nbsp;– PA&nbsp;– <a href="https://cinematecapauloamorim.com.br/programacao/2403/uma-bela-vida">Uma Bela Vida</a><br>
            #     17h15 – NL&nbsp;–&nbsp;<a href="https://cinematecapauloamorim.com.br/programacao/2428/iracema-uma-transa-amazonica">Iracema – Uma Transa Amazônica</a><br>
            #     18h45 – EH&nbsp;–&nbsp;<a href="https://cinematecapauloamorim.com.br/programacao/2427/apenas-alguns-dias">Apenas Alguns Dias</a><br>
            #     19h&nbsp;– PA&nbsp;–&nbsp;<a href="https://cinematecapauloamorim.com.br/programacao/2426/monsieur-aznavour">Monsieur Aznavour</a><br>
            #     19h15 – NL&nbsp;–&nbsp;<a href="https://cinematecapauloamorim.com.br/programacao/2429/razoes-africanas">Razões Africanas</a>
            # </p>
            feature_time_regex = r"(\d{2}h(?:\d{2})?)\s+–\s+\w+\s+–\s+(.*)"
            feature_time_matches = re.findall(feature_time_regex, p_tag.text)
            for feature_time_match in feature_time_matches:
                time_str = (
                    unicodedata.normalize("NFKC", feature_time_match[0])
                    .strip("\n")
                    .strip()
                    .split(" ")[0]
                )
                hour_str, min_str = time_str.split("h")
                if min_str:
                    parsed_time = dt_time(int(hour_str), int(min_str))
                else:
                    parsed_time = dt_time(int(hour_str))
                for movie in self.movies:
                    movie_title = movie["title"].strip().lower()
                    match_title = feature_time_match[1].strip().lower()
                    title_match = movie_title == match_title
                    if title_match:
                        movie["time"].append(
                            {"time": parsed_time, "date": current_date}
                        )
                        continue
                    partial_match = movie_title.startswith(match_title)
                    if partial_match:
                        movie["time"].append(
                            {"time": parsed_time, "date": current_date}
                        )
                        # TODO: warn admin user to check because this might be a mismatch
                        continue

        features = [movie for movie in self.movies if len(movie["time"]) > 0]

        # Sort features by date and time
        sorted_features = sorted(
            features,
            key=lambda feature: (
                feature["time"][0]["date"],
                feature["time"][0]["time"],
            ),
        )

        # Format the time strings to include date information
        for feature in sorted_features:
            formatted_times = []
            for time_entry in feature["time"]:
                time_str = time_entry["time"].strftime("%H:%M")
                date_str = time_entry["date"].strftime("%Y-%m-%d")
                formatted_times.append(f"{date_str}T{time_str}")
            feature["time"] = formatted_times

        return sorted_features

    def get_weekly_features_json(self):
        self._get_movies_on_programacao()
        self._get_movie_excerpt()
        return self._get_weekly_features()

    # Keep the old method for backward compatibility
    def get_daily_features_json(self):
        """Deprecated: Use get_weekly_features_json() instead"""
        return self.get_weekly_features_json()

    # Deprecated HTML structure
    def deprecated_strong_tag_followed_by_table(self, p_tag, current_date):
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
            self._get_movies_from_table(feature_timetable, current_date)

    # Deprecated HTML structure
    def _get_movies_from_table(self, feature_timetable, current_date):
        for feature_tr in feature_timetable.find_all("tr"):
            feature_tds = feature_tr.find_all("td")
            for movie in self.movies:
                if movie["title"].lower() == feature_tds[2].text.lower():
                    # Movie will be featured on the specified date
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

                    # Add date information to the time entry
                    movie["time"].append({"time": parsed_time, "date": current_date})

    # Deprecated HTML structure
    def deprecated_huge_html_table(self, grade_soup):
        # <table border="0" cellpadding="0" cellspacing="0" style="width:461px">
        #     <tbody>
        #         <tr>
        #             <td colspan="3"><strong>31 de outubro&nbsp;| quinta</strong></td>
        #         </tr>
        #         <tr>
        #             <td colspan="3">&nbsp;</td>
        #         </tr>
        #         <tr>
        #             <td>14h15</td>
        #             <td>PA</td>
        #             <td><a href="https://www.cinematecapauloamorim.com.br/programacao/2111/megalopolis">Megal&oacute;polis</a></td>
        #         </tr>
        #         <tr>
        #            ...
        #         </tr>
        #         <tr>
        #            ...
        #         </tr>
        #           ...
        #         <tr>
        #             <td colspan="3" rowspan="2">&nbsp;</td>
        #         </tr>
        #         <tr>
        #         </tr>
        #         <tr>
        #             <td colspan="3"><strong>1 de novembro&nbsp;| sexta</strong></td>
        #         </tr>
        #         <tr>
        #             <td colspan="3">&nbsp;</td>
        #         </tr>
        #         <tr>
        #             <td>14h15</td>
        #             <td>PA</td>
        #             <td><a href="...">...</td>
        #         </tr>
        for strong_tag in grade_soup.find_all("strong"):
            strong_text = unicodedata.normalize("NFKC", strong_tag.text)

            # Parse the date from the strong tag
            current_date = self._parse_date_from_strong_text(strong_text)
            if current_date is None:
                continue

            strong_tag_tr = strong_tag.parent.parent
            # get all trs after the current one
            rows_after = strong_tag_tr.find_next_siblings("tr")
            for feature_tr in rows_after:
                feature_tds = feature_tr.find_all("td")
                # needs to be in the following format
                # <tr>
                #    <td>19h</td>
                #    <td>PA</td>
                #    <td><a href="...">Movie name</a></td>
                # </tr>
                if len(feature_tds) != 3:
                    # not in the format we expect
                    continue
                for movie in self.movies:
                    # make sure we only get the first occurence of that movie
                    if movie.get("scrapped", False) is True:
                        continue
                    if movie["title"].lower() == feature_tds[2].text.lower():
                        # Movie will be featured on the specified date
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
                        movie["time"].append(
                            {"time": parsed_time, "date": current_date}
                        )
                        movie["scrapped"] = True
                # features = [movie for movie in self.movies if len(movie["time"]) > 0]
