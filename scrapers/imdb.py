import requests
from bs4 import BeautifulSoup
from country_list import countries_for_language
from Levenshtein import distance


def infer_movie_country(general_info):
    country_names_pt_br = {code: name for code, name in countries_for_language("pt-br")}
    country_names_eng = {code: name for code, name in countries_for_language("en")}

    movie_country_code = False
    for code in country_names_pt_br:
        if country_names_pt_br[code] in general_info:
            movie_country_code = code
            break
    if movie_country_code is False:
        return None
    return country_names_eng[movie_country_code]


class IMDBScrapper:
    """Adapted from https://github.com/D3C0RU5/web-scraping-movie"""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/111.0",
            "content-type": "text/html; charset=utf-8",
            "server": "server",
        }

    def _get_imdb_directors(self, movie_soup) -> list[str]:
        """IMDB will list directors differently when it's a single director or multiple directors. ex:
        1. Single director
        <span ...>Director</span>
        <div ...><ul ...><li ...><a ...>ronald mcguffyn</a></li></ul></div>
        2. Multiple directors
        <span ...>Directors</span>
        <div ...>
            <ul ...>
                <li ...>
                    <a ...>ronald mcguffyn</a>
                </li>
                <li ...>
                    <a ...>dude mcguy</a>
                </li>
            </ul>
        </div>

        Return:
            list[str]: list of lowercased director names. Empty if none found"""
        director_span = movie_soup.find("span", string="Director")
        if director_span is not None:
            # movie has a single credited director
            return [director_span.find_next_sibling("div").text.lower()]
        director_span = movie_soup.find("span", string="Directors")
        if director_span is not None:
            # movie has multiple credited directors,
            # expect names to be in list items
            return [
                director_li.text.lower()
                for director_li in director_span.find_next_sibling("div").find_all("li")
            ]
        # couldn't find anything :^/
        return []

    def get_image(self, movie):
        movie_name = movie["title"]
        director = movie["director"]
        search_request = requests.get(
            f"https://www.imdb.com/find/?q={movie_name}", headers=self.headers
        )
        search_html = search_request.text
        search_soup = BeautifulSoup(search_html, "html.parser")

        movie_list = search_soup.find_all(class_="find-title-result")
        if len(movie_list) == 0:
            return None

        # will hold data in format {"imdb_movie_url": "https://...", "levenshtein_distance": "20"}
        imdb_search_result_movies = []

        for index, movie_item in enumerate(movie_list):
            movie_item_name = movie_item.find("a").text
            distance_value = distance(movie_name, movie_item_name)
            movie_a_tag = movie_item.find("a")
            # skip if link isn't well formated
            if not movie_a_tag:
                continue
            imdb_search_result_movies.append(
                {
                    "imdb_movie_url": f"https://www.imdb.com{movie_a_tag['href']}",
                    "levenshtein_distance": distance_value,
                }
            )

        sorted_imdb_results = sorted(
            imdb_search_result_movies,
            key=lambda search_result: search_result["levenshtein_distance"],
        )

        matching_result_soup = False
        for imdb_result in sorted_imdb_results:
            movie_link = imdb_result["imdb_movie_url"]

            movie_request = requests.get(movie_link, headers=self.headers)
            movie_html = movie_request.text
            movie_soup = BeautifulSoup(movie_html, "html.parser")

            if director is not False:
                imdb_movie_directors = self._get_imdb_directors(movie_soup)
                if director.lower() not in imdb_movie_directors:
                    # director doesn't match, try next movie in result list
                    continue
            else:
                country = infer_movie_country(movie["general_info"])
                if country is None:
                    # scrapped movie has no defined director,
                    # no point in trying all movies in the imbd result list
                    # as we have no parameter for comparison
                    break
                country_span = movie_soup.find("span", string="Country of origin")
                imdb_movie_country = country_span.find_next_sibling("div").text
                if imdb_movie_country.lower() != country.lower():
                    # country doesn't match, try next in movie in result list
                    continue

            # if we got here, it's a match!
            matching_result_soup = movie_soup
            break

        if not matching_result_soup:
            return None

        # TODO: attempt to get movie featured poster first,
        # sometimes images listed here are random stills
        # from the movie
        image_poster_link = movie_soup.find(class_="hero-media__watchlist").findNext("a")[
            "href"
        ]

        poster_request = requests.get(
            f"https://www.imdb.com/{image_poster_link}", headers=self.headers
        )
        poster_html = poster_request.text
        poster_soup = BeautifulSoup(poster_html, "html.parser")

        image_poster_link = poster_soup.findAll("img")[1]["src"]

        return image_poster_link
