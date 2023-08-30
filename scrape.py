#!/usr/bin/env python

import argparse
import json
import locale
import os
import re
import requests
import unicodedata
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from bs4.element import NavigableString, ResultSet
from datetime import date, datetime, time as dt_time


def string_is_current_day(date_string: str) -> bool:
    """Checks whether a date string in the format

    24 de agosto | quinta-feira | 16h

    matches the current day."""

    # Convert month name to month number
    month_mapping = {
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

    # Extract day, month, and time
    day_month, week_day, time = date_string.split(" | ")
    day_month_split = day_month.split()
    day = int(day_month_split[0])
    month = month_mapping[day_month_split[-1]]

    # Get current date
    current_date = datetime.now().date()

    # Create a datetime object for the parsed date
    parsed_date = datetime(current_date.year, month, day).date()

    # Check if the parsed date is the current date
    return parsed_date == current_date


def is_monday():
    return date.today().weekday() == 0


def dump_utf8_json(jsonable_object) -> str:
    """Returns a json string while keeping utf8 artifacts such as accents, etc.
    Adapted from https://stackoverflow.com/a/18337754/14427854"""
    return json.dumps(jsonable_object, ensure_ascii=False).encode("utf8").decode()


class CineBancarios:
    def __init__(self):
        self.url = "http://cinebancarios.blogspot.com/feeds/posts/default?alt=rss"
        self.dir = os.path.join("cinebancarios")

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

    def _match_info_on_tags(self, movie_block: dict, tag):
        if movie_block["classification"] == "":
            if tag.text.lower().startswith("classificação indicativa:"):
                movie_block["classification"] = tag.text
                return self._match_info_on_tags(
                    movie_block, tag.find_previous_sibling("p")
                )

            movie_block["classification"] = False
            return self._match_info_on_tags(movie_block, tag)

        if movie_block["director"] == "":
            if tag.text.startswith("Direção:"):
                movie_block["director"] = tag.text.replace("Direção:", "").strip()
                return self._match_info_on_tags(
                    movie_block, tag.find_previous_sibling("p")
                )

            movie_block["director"] = False
            return self._match_info_on_tags(movie_block, tag)

        if movie_block["general_info"] == "":
            if re.search(r"\d{2,3}\s?min\.?", tag.text):
                movie_block["general_info"] = tag.text
                return self._match_info_on_tags(
                    movie_block, tag.find_previous_sibling("p")
                )

            movie_block["general_info"] = False
            return self._match_info_on_tags(movie_block, tag)

        movie_block["title"] = tag.text
        return movie_block

    def _parse_p_tag_movie_block(self, p_tag):
        """attempts to parse a movie block in the following format
        ```
        <p>RETRATOS FANTASMAS</p>
        <p>Brasil/Documentário/2022/ 93min.</p>  # <!--- optional
        <p>Direção: Kleber Mendonça Filho</p>    # <!--- optional
        <p>Classificação indicativa: 16 anos</p> # <!--- optional
        <p>Sinopse: O filme tem o centro da cidade do Recife como personagem
        principal, sendo um espaço histórico e humano, revisitado através
        dos grandes cinemas que serviram como espaços de convívio durante o
        século XX. Foram lugares de sonho e de indústria, e a relação das
        pessoas com esse universo é um marcador de tempo para as mudanças
        dos costumes em sociedade.</p>
        ```"""
        movie_block = {
            "poster": "",
            "title": "",
            "general_info": "",
            "director": "",
            "classification": "",
            "excerpt": "",
            "time": [],
            "read_more": "http://cinebancarios.blogspot.com/?view=classic",
        }

        movie_block["excerpt"] = p_tag.text

        movie_block = self._match_info_on_tags(
            movie_block, p_tag.find_previous_sibling("p")
        )
        return movie_block

    def _get_previous_node(
        self, nodes: ResultSet, node: NavigableString
    ) -> NavigableString:
        current_index = nodes.index(node)
        return nodes[current_index - 1]

    def _match_info_on_text_nodes(
        self, movie_block: dict, nodes: ResultSet, node: NavigableString
    ):
        if movie_block["classification"] == "":
            if node.text.lower().startswith("classificação indicativa:"):
                movie_block["classification"] = node.text
                return self._match_info_on_text_nodes(
                    movie_block, nodes, self._get_previous_node(nodes, node)
                )

            movie_block["classification"] = False
            return self._match_info_on_text_nodes(movie_block, nodes, node)

        if movie_block["director"] == "":
            if node.text.startswith("Direção:"):
                movie_block["director"] = node.text.replace("Direção:", "").strip()
                return self._match_info_on_text_nodes(
                    movie_block, nodes, self._get_previous_node(nodes, node)
                )

            movie_block["director"] = False
            return self._match_info_on_text_nodes(movie_block, nodes, node)

        if movie_block["general_info"] == "":
            if re.search(r"\d{2,3}\s?min\.?", node.text):
                # in some cases the Country/Genre/Year/Duration block
                # gets split into two text nodes, for example
                #   Brasil/Documentário/2023/
                #   102min.
                # so whenever the regex above matches the duration, we need to check if
                # the previous node has information divided by slashes
                previous_node = self._get_previous_node(nodes, node)
                slash_check = len(previous_node.split("/")) > 1
                if slash_check:
                    # previous node has the rest of the general information
                    movie_block["general_info"] = previous_node.text + node.text
                    # call the function with the node before the previous node :P
                    return self._match_info_on_text_nodes(
                        movie_block,
                        nodes,
                        self._get_previous_node(nodes, previous_node),
                    )
                # the current node probably has all of the general information,
                # continue with the previous node
                # TODO: run the slash_check on the current node?
                movie_block["general_info"] = node.text
                return self._match_info_on_text_nodes(
                    movie_block, nodes, self._get_previous_node(nodes, node)
                )

            movie_block["general_info"] = False
            return self._match_info_on_text_nodes(movie_block, nodes, node)

        movie_block["title"] = node.text
        return movie_block

    def _parse_text_node_movie_block(self, nodes: ResultSet, node: NavigableString):
        """attempts to parse a movie block in the following format
        (notice the lack of proper html tags, text is in #text nodes in the browser)
        ```
        <b>
        ESTREIA
        <br>
        <br>
        VENTO NA FRONTEIRA
        </b>
        <br>
        Brasil/ Documentário/ 2022/ 78min.       # <!--- optional
        <br>
        Direção: Laura Faerman, Marina Weis      # <!--- optional
        <br>
        Classificação Indicativa: 14 anos        # <!--- optional
        <br>
        Sinopse: No coração do agronegócio brasileiro,
        uma professora indígena luta pelo direito de sua comunidade
        às terras ancestrais. No lado oposto, está a herdeira dessas
        terras, uma advogada com fortes relações com o poder federal bolsonarista.
        <br>
        ```"""
        movie_block = {
            "poster": "",
            "title": "",
            "general_info": "",
            "director": "",
            "classification": "",
            "excerpt": "",
            "time": [],
            "read_more": "http://cinebancarios.blogspot.com/?view=classic",
        }
        movie_block["excerpt"] = node.text
        movie_block = self._match_info_on_text_nodes(
            movie_block, nodes, self._get_previous_node(nodes, node)
        )
        return movie_block

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

    def _get_current_movie_blocks(self, soup):
        p_tags = soup.find_all("p")
        movie_blocks = []
        for p_tag in p_tags:
            if p_tag.text.startswith("Sinopse:"):
                # Found a movie block
                movie_block = self._parse_p_tag_movie_block(p_tag)
                movie_blocks.append(movie_block)
        if len(movie_blocks) == 0:
            # Couldn't find any movie blocks with proper <p> tags
            # try using #text nodes
            text_nodes = soup.find_all(string=True)
            for node in text_nodes:
                if node.text.startswith("Sinopse:"):
                    # Found a movie block
                    movie_block = self._parse_text_node_movie_block(text_nodes, node)
                    movie_blocks.append(movie_block)
        # only parse the first post
        return movie_blocks

    def _get_movies_show_time(self, soup, movie_blocks):
        p_tags = soup.find_all("p")
        for p_tag in p_tags:
            p_tag_content = p_tag.text.replace("\n", " ")
            for movie in movie_blocks:
                if re.match(
                    rf"\d{{2}}h: {movie['title']}",
                    p_tag_content,
                    re.IGNORECASE,
                ):
                    movie["time"].append(
                        p_tag_content.replace(f": {movie['title']}", "")
                    )
        for movie in movie_blocks:
            movie["time"] = " / ".join(movie["time"])
        return movie_blocks

    def get_daily_features_json(self):
        current_post_soup = self._get_current_blog_post_soup()
        current_movie_blocks = self._get_current_movie_blocks(current_post_soup)
        current_movie_blocks = self._get_movies_show_time(
            current_post_soup, current_movie_blocks
        )
        return {
            "url": "http://cinebancarios.blogspot.com",
            "cinema": "CineBancários",
            "slug": "cinebancarios",
            "warning": "Não há sessões nas segundas-feiras" if is_monday() else False,
            "features": current_movie_blocks,
        }


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
        r = requests.get(url)
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
                "genre": ticket_link.css.select_one(".ticket-foto")
                .css.select_one(".generos")
                .text.strip("\n"),
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
            movie["general_info"] = (
                (
                    movie_soup.css.select_one("#mainbar h2")
                    .find_next_sibling()
                    .css.select_one("strong em")
                    .text
                )
                + " | "
                + movie["room"]
                + " | "
                + movie["genre"]
            )
            movie["excerpt"] = (
                movie_soup.css.select_one("#mainbar h2")
                .find_next_sibling()
                .find_next_sibling()
                .text
            )

    def _get_today_str(self):
        """returns de current day in
        {XX de mês} format"""
        locale.setlocale(locale.LC_ALL, "pt_BR.UTF-8")
        today_str = date.today().strftime("%d de %B")
        locale.setlocale(locale.LC_ALL, locale.getdefaultlocale())
        return today_str.lower()

    def _get_todays_features(self):
        grade_html = self._get_page_html(
            os.path.join(self.todays_dir, "grade.html"), self.grade_url
        )
        grade_soup = BeautifulSoup(grade_html, "html.parser")
        today_str = self._get_today_str()
        for p_tag in grade_soup.find_all("p"):
            strong_tag = p_tag.find("strong")
            if strong_tag is None:
                continue
            strong_text = unicodedata.normalize("NFKC", strong_tag.text)
            if not strong_text.lower().startswith(today_str):
                continue

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
        sorted_features = sorted(features, key=lambda feature: feature['time'][0])
        for feature in sorted_features:
            feature["time"] = "/ ".join([parsed_time.strftime("%Hh%M") for parsed_time in feature["time"]])
        return sorted_features

    def get_daily_features_json(self):
        self._get_movies_on_programacao()
        self._get_movie_excerpt()
        return self._get_todays_features()


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
            for l in iter(movie_director.splitlines()):
                line = l.strip()
                if len(line) == 0:
                    continue
                if line.startswith("Direção"):
                    feature_film["director"] = line.replace("Direção", "").strip()
                elif line.startswith("Classificação"):
                    feature_film["classification"] = line
                else:
                    general_info += f"\n{line}"
            feature_film["general_info"] = general_info

            movie_text = movie.css.select_one(".movie-info .movie-text")
            feature_film["excerpt"] = movie_text.get_text()

            read_more = movie.css.select_one(".movie-info .read-more")
            feature_film["read_more"] = (
                "http://www.capitolio.org.br" + read_more["href"]
            )
            features.append(feature_film)

        return features


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="cinematecabot",
        description="Grab the schedule for Porto Alegre's finest features",
    )

    allowed_rooms = ["capitolio", "sala-redencao", "cinebancarios", "paulo-amorim"]

    parser.add_argument(
        "-r",
        "--rooms",
        nargs="+",
        help=f"Filter specific rooms. Available: {', '.join(allowed_rooms)}",
        required=True,
    )

    args = parser.parse_args()

    if args.rooms:
        if not all(room in allowed_rooms for room in args.rooms):
            parser.error(
                f"Invalid selected rooms. Available: {', '.join(allowed_rooms)}"
            )
        features = []
        if "capitolio" in args.rooms:
            feature = {
                "url": "http://www.capitolio.org.br",
                "cinema": "Cinemateca Capitólio",
                "slug": "capitolio"
            }
            cap = Capitolio()
            feature["features"] = cap.get_daily_features_json()
            features.append(feature)
        if "sala-redencao" in args.rooms:
            feature = {
                "url": "https://www.ufrgs.br/difusaocultural/salaredencao/",
                "cinema": "Sala Redenção",
                "slug": "sala-redencao",
            }
            redencao = SalaRedencao()
            feature["features"] = redencao.get_daily_features_json()
            features.append(feature)
        if "cinebancarios" in args.rooms:
            cineBancarios = CineBancarios()
            features.append(cineBancarios.get_daily_features_json())
        if "paulo-amorim" in args.rooms:
            feature = {
                "url": "https://www.cinematecapauloamorim.com.br",
                "cinema": "Cinemateca Paulo Amorim",
                "slug": "paulo-amorim"
            }
            pauloAmorim = CinematecaPauloAmorim()
            feature["features"] = pauloAmorim.get_daily_features_json()
            features.append(feature)
        print(dump_utf8_json(features))
