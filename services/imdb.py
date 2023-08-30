import requests

from bs4 import BeautifulSoup
from country_list import countries_for_language
from Levenshtein import distance


def infer_movie_country(general_info):
    country_names_pt_br = {code: name for code, name in countries_for_language('pt-br')}
    country_names_eng = {code: name for code, name in countries_for_language('en')}
    
    movie_country_code = False
    for code in country_names_pt_br:
        if country_names_pt_br[code] in general_info:
            movie_country_code = code
            break
    if movie_country_code is False:
        return None
    return country_names_eng[movie_country_code]

class IMDBScrapper:
    """Taken from https://github.com/D3C0RU5/web-scraping-movie/blob/9a408e34688bf6d0f25be41df142efdaf83ab3f9/services/scrap.py"""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/111.0",
            "content-type": "text/html; charset=utf-8",
            "server": "server",
        }

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

        selected_movie_index = 0
        smallest_distance = None

        for index, movie_item in enumerate(movie_list):
            movie_item_name = movie_item.find("a").text
            distance_value = distance(movie_name, movie_item_name)

            if smallest_distance is None or distance_value < smallest_distance:
                smallest_distance = distance_value
                selected_movie_index = index

        selected_movie = movie_list[selected_movie_index]

        movie_link = f"https://www.imdb.com/{selected_movie.find('a')['href']}"

        movie_request = requests.get(movie_link, headers=self.headers)
        movie_html = movie_request.text
        movie_soup = BeautifulSoup(movie_html, "html.parser")
        
        if director is not False:
            director_span = movie_soup.find("span", string="Director")
            imdb_movie_director = director_span.find_next_sibling("div").text
            if imdb_movie_director.lower() != director.lower():
                return None
        else:
            country = infer_movie_country(movie["general_info"])
            if country is None:
                return None
            country_span = movie_soup.find("span", string="Country of origin")
            imdb_movie_country = country_span.find_next_sibling("div").text
            if imdb_movie_country.lower() != country.lower():
                return None

        image_poster_link = movie_soup.find(class_="hero-media__watchlist").findNext(
            "a"
        )["href"]

        poster_request = requests.get(
            f"https://www.imdb.com/{image_poster_link}", headers=self.headers
        )
        poster_html = poster_request.text
        poster_soup = BeautifulSoup(poster_html, "html.parser")

        image_poster_link = poster_soup.findAll("img")[1]["src"]

        return image_poster_link