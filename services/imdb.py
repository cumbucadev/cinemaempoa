import requests

from bs4 import BeautifulSoup
from Levenshtein import distance


class IMDBScrapper:
    """Taken from https://github.com/D3C0RU5/web-scraping-movie/blob/9a408e34688bf6d0f25be41df142efdaf83ab3f9/services/scrap.py"""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/111.0",
            "content-type": "text/html; charset=utf-8",
            "server": "server",
        }

    def get_image(self, movie_name):
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

            if smallest_distance == None or distance_value < smallest_distance:
                smallest_distance = distance_value
                selected_movie_index = index

        selected_movie = movie_list[selected_movie_index]
        selected_movie_name = selected_movie.find("a").text

        movie_link = f"https://www.imdb.com/{selected_movie.find('a')['href']}"

        movie_request = requests.get(movie_link, headers=self.headers)
        movie_html = movie_request.text
        movie_soup = BeautifulSoup(movie_html, "html.parser")

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
