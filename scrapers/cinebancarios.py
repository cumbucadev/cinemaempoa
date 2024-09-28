import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString, ResultSet

from utils import is_monday


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
        if tag is None:
            # break recursion if we attempt to access a non existing tag
            return movie_block
        # always check if there is an image inside our tag
        if movie_block["poster"] == "":
            nested_img = tag.find("img")
            if nested_img:
                # check if there is an srcset attribute
                if "srcset" in nested_img.attrs:
                    # srcset is a comma separated string in format
                    # "https://... 204w, https://... 545w, ..."
                    srcset = nested_img["srcset"]
                    # create a list in the format
                    # [{"url": "https://...", "width": 325}, ...]
                    srcset_list = []
                    for img_option in srcset.split(", "):
                        url, width = img_option.split(" ")
                        srcset_list.append(
                            {"url": url, "width": int(width.replace("w", ""))}
                        )
                    # sort srcset_list by width, largest first
                    sorted_srcset_list = sorted(
                        srcset_list,
                        key=lambda srcset_option: srcset_option["width"],
                        reverse=True,
                    )
                    movie_block["poster"] = sorted_srcset_list[0]["url"]
                else:
                    # no srcset, grab ye olde src attribute
                    movie_block["poster"] = tag.find("img")["src"]

                # after getting the img, continue with the previous tag
                return self._match_info_on_tags(
                    movie_block, tag.find_previous_sibling("p")
                )

        # handle empty tags by skipping to the one above
        if tag.text == "":
            return self._match_info_on_tags(movie_block, tag.find_previous_sibling("p"))

        # check if the current <p> tag has multiple nodes inside it, for ex.
        # <p>
        #   <span>PARA ONDE VOAM AS FEITICEIRAS<br /></span>
        #   Brasil/ Documentário/ 2020/ 89min<br/>
        #   Direção: Eliane Caffé, Carla Caffé e Beto Amaral
        # </p>
        # tag.contents would return the following list:
        # [
        #   0: <span>PARA ONDE VOAM AS FEITICEIRAS<br /></span>
        #   1: Brasil/ Documentário/ 2020/ 89min
        #   2: <br/>
        #   3: Direção: Eliane Caffé, Carla Caffé e Beto Amaral
        # ]
        if len(tag.contents) > 1:
            # filter out empty nodes (such as <br/>s, etc)
            non_empty_nodes = [node for node in tag.contents if node.text != ""]
            return self._match_info_on_text_nodes(
                movie_block, non_empty_nodes, non_empty_nodes[-1]
            )

        if movie_block["classification"] == "":
            if tag.text.lower().startswith("classificação indicativa:"):
                movie_block["classification"] = tag.text.strip()
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
                movie_block["general_info"] = tag.text.strip()
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

        movie_block["excerpt"] = unicodedata.normalize(
            "NFKD", p_tag.text.replace("\n", " ").strip()
        )

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
        # handle empty nodes by skipping to the one above
        if node.text == "":
            return self._match_info_on_text_nodes(
                movie_block, nodes, self._get_previous_node(nodes, node)
            )
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
                slash_check = len(previous_node.text.split("/")) > 1
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
        movie_block["excerpt"] = unicodedata.normalize("NFKD", node.text)
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
                if movie_block["title"] == "":
                    # couldn't parse the movie correctly, do not add to the list
                    continue
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
        text_nodes = soup.find_all(string=True)
        for text_node in text_nodes:
            # .normalize removes unwanted html artifacts, ex.
            # '17h:\xa0\xa0PARA ONDE VOAM AS FEITICEIRAS'
            text_node_content = unicodedata.normalize(
                "NFKD", text_node.text.replace("\n", " ")
            )
            for movie in movie_blocks:
                # sometimes the time block will have more than a single whitespace
                # between the screening time and the movie title
                # ex. "17h:   PARA ONDE VOAM AS FEITICEIRAS"
                if re.match(
                    rf"\d{{2}}h:\s+{movie['title']}",
                    text_node_content,
                    re.IGNORECASE,
                ):
                    movie["time"].append(
                        re.sub(rf":\s+{movie['title']}", "", text_node_content)
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
