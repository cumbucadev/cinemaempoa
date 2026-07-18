from unittest.mock import MagicMock, patch

from flask_backend.import_json import ScrappedFeature
from scrapers.imdb import IMDBScrapper, infer_movie_country

SEARCH_HTML = """
<html><body>
<li class="find-title-result"><a href="/title/tt0001/">Oldboy</a></li>
</body></html>
"""

MOVIE_HTML_SINGLE_DIRECTOR = """
<html><body>
<span>Director</span>
<div><ul><li><a>Park Chan-wook</a></li></ul></div>
<div class="hero-media__watchlist"></div>
<a href="/title/tt0001/mediaviewer/rm001/">poster link</a>
</body></html>
"""

MOVIE_HTML_MULTIPLE_DIRECTORS = """
<html><body>
<span>Directors</span>
<div>
  <ul>
    <li><a>ronald mcguffyn</a></li>
    <li><a>dude mcguy</a></li>
  </ul>
</div>
<div class="hero-media__watchlist"></div>
<a href="/title/tt0001/mediaviewer/rm001/">poster link</a>
</body></html>
"""

MOVIE_HTML_NO_DIRECTOR_INFO = """
<html><body>
<div class="hero-media__watchlist"></div>
<a href="/title/tt0001/mediaviewer/rm001/">poster link</a>
</body></html>
"""

MOVIE_HTML_COUNTRY_MATCH = """
<html><body>
<span>Country of origin</span>
<div>South Korea</div>
<div class="hero-media__watchlist"></div>
<a href="/title/tt0001/mediaviewer/rm001/">poster link</a>
</body></html>
"""

MOVIE_HTML_COUNTRY_MISMATCH = """
<html><body>
<span>Country of origin</span>
<div>Brazil</div>
<div class="hero-media__watchlist"></div>
<a href="/title/tt0001/mediaviewer/rm001/">poster link</a>
</body></html>
"""

POSTER_HTML = """
<html><body>
<img src="thumb.jpg"/>
<img src="full-poster.jpg"/>
</body></html>
"""

NO_RESULTS_HTML = "<html><body></body></html>"


def _feature(director=False, general_info=""):
    return ScrappedFeature(
        poster=None,
        time=None,
        title="Oldboy",
        original_title=None,
        price=None,
        director=director,
        classification=None,
        general_info=general_info,
        excerpt="",
        read_more=None,
    )


def _fake_get(movie_html):
    def handler(url, headers=None):
        resp = MagicMock()
        if "/find/" in url:
            resp.text = SEARCH_HTML
        elif "mediaviewer" in url:
            resp.text = POSTER_HTML
        else:
            resp.text = movie_html
        return resp

    return handler


class TestGetImage:
    def test_no_search_results_returns_none(self):
        with patch(
            "scrapers.imdb.requests.get",
            return_value=MagicMock(text=NO_RESULTS_HTML),
        ):
            result = IMDBScrapper().get_image(_feature(director="Park Chan-wook"))
        assert result is None

    def test_matching_director_returns_poster_url(self):
        with patch(
            "scrapers.imdb.requests.get",
            side_effect=_fake_get(MOVIE_HTML_SINGLE_DIRECTOR),
        ):
            result = IMDBScrapper().get_image(_feature(director="Park Chan-wook"))
        assert result == "full-poster.jpg"

    def test_matching_one_of_multiple_directors_returns_poster_url(self):
        with patch(
            "scrapers.imdb.requests.get",
            side_effect=_fake_get(MOVIE_HTML_MULTIPLE_DIRECTORS),
        ):
            result = IMDBScrapper().get_image(_feature(director="dude mcguy"))
        assert result == "full-poster.jpg"

    def test_non_matching_director_returns_none(self):
        with patch(
            "scrapers.imdb.requests.get",
            side_effect=_fake_get(MOVIE_HTML_SINGLE_DIRECTOR),
        ):
            result = IMDBScrapper().get_image(_feature(director="Someone Else"))
        assert result is None

    def test_no_director_matching_country_returns_poster_url(self):
        with patch(
            "scrapers.imdb.requests.get",
            side_effect=_fake_get(MOVIE_HTML_COUNTRY_MATCH),
        ):
            result = IMDBScrapper().get_image(
                _feature(director=False, general_info="Coreia do Sul")
            )
        assert result == "full-poster.jpg"

    def test_no_director_mismatched_country_returns_none(self):
        with patch(
            "scrapers.imdb.requests.get",
            side_effect=_fake_get(MOVIE_HTML_COUNTRY_MISMATCH),
        ):
            result = IMDBScrapper().get_image(
                _feature(director=False, general_info="Coreia do Sul")
            )
        assert result is None

    def test_no_director_and_no_inferable_country_returns_none(self):
        with patch(
            "scrapers.imdb.requests.get",
            side_effect=_fake_get(MOVIE_HTML_COUNTRY_MATCH),
        ):
            result = IMDBScrapper().get_image(
                _feature(director=False, general_info="Terra do Nunca")
            )
        assert result is None


class TestGetImdbDirectors:
    def test_single_director(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MOVIE_HTML_SINGLE_DIRECTOR, "html.parser")
        directors = IMDBScrapper()._get_imdb_directors(soup)
        assert directors == ["park chan-wook"]

    def test_multiple_directors(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MOVIE_HTML_MULTIPLE_DIRECTORS, "html.parser")
        directors = IMDBScrapper()._get_imdb_directors(soup)
        assert directors == ["ronald mcguffyn", "dude mcguy"]

    def test_no_directors_found(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(MOVIE_HTML_NO_DIRECTOR_INFO, "html.parser")
        directors = IMDBScrapper()._get_imdb_directors(soup)
        assert directors == []


class TestInferMovieCountry:
    def test_matches_known_country(self):
        assert infer_movie_country("Coreia do Sul") == "South Korea"

    def test_returns_none_when_no_country_matches(self):
        assert infer_movie_country("Terra do Nunca") is None
