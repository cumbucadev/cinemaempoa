from unittest.mock import Mock, patch

import pytest
import requests

from flask_backend.service.tmdb import TMDBClient


@pytest.fixture()
def tmdb_client():
    return TMDBClient(api_token="fake-token")


class TestGetMovieDetails:
    def test_returns_genres_and_directors(self, tmdb_client):
        response = Mock()
        response.json.return_value = {
            "genres": [{"id": 28, "name": "Ação"}, {"id": 12, "name": "Aventura"}],
            "credits": {
                "crew": [
                    {"id": 1, "name": "Someone Else", "job": "Producer"},
                    {"id": 2, "name": "Jane Director", "job": "Director"},
                ]
            },
        }
        with patch("flask_backend.service.tmdb.requests.get", return_value=response):
            details = tmdb_client.get_movie_details(123)

        assert details["genres"] == [
            {"id": 28, "name": "Ação"},
            {"id": 12, "name": "Aventura"},
        ]
        assert details["directors"] == [{"id": 2, "name": "Jane Director"}]

    def test_supports_co_direction(self, tmdb_client):
        response = Mock()
        response.json.return_value = {
            "genres": [],
            "credits": {
                "crew": [
                    {"id": 1, "name": "Director One", "job": "Director"},
                    {"id": 2, "name": "Director Two", "job": "Director"},
                ]
            },
        }
        with patch("flask_backend.service.tmdb.requests.get", return_value=response):
            details = tmdb_client.get_movie_details(123)

        assert details["directors"] == [
            {"id": 1, "name": "Director One"},
            {"id": 2, "name": "Director Two"},
        ]

    def test_returns_empty_directors_when_none_in_crew(self, tmdb_client):
        response = Mock()
        response.json.return_value = {
            "genres": [{"id": 28, "name": "Ação"}],
            "credits": {"crew": [{"id": 1, "name": "Someone", "job": "Editor"}]},
        }
        with patch("flask_backend.service.tmdb.requests.get", return_value=response):
            details = tmdb_client.get_movie_details(123)

        assert details["directors"] == []

    def test_raises_on_request_exception(self, tmdb_client):
        with (
            patch(
                "flask_backend.service.tmdb.requests.get",
                side_effect=requests.RequestException("boom"),
            ),
            pytest.raises(requests.RequestException),
        ):
            tmdb_client.get_movie_details(123)

    def test_returns_original_title_year_language_and_countries(self, tmdb_client):
        response = Mock()
        response.json.return_value = {
            "genres": [],
            "credits": {"crew": []},
            "original_title": "Cão e Lobo",
            "release_date": "2025-03-14",
            "original_language": "pt",
            "production_countries": [
                {"iso_3166_1": "BR", "name": "Brazil"},
                {"iso_3166_1": "UY", "name": "Uruguay"},
            ],
        }
        with patch("flask_backend.service.tmdb.requests.get", return_value=response):
            details = tmdb_client.get_movie_details(123)

        assert details["original_title"] == "Cão e Lobo"
        assert details["release_year"] == 2025
        assert details["original_language"] == "pt"
        assert details["countries"] == [
            {"iso_3166_1": "BR", "name": "Brazil"},
            {"iso_3166_1": "UY", "name": "Uruguay"},
        ]

    def test_release_year_is_none_when_release_date_missing(self, tmdb_client):
        response = Mock()
        response.json.return_value = {"genres": [], "credits": {"crew": []}}
        with patch("flask_backend.service.tmdb.requests.get", return_value=response):
            details = tmdb_client.get_movie_details(123)

        assert details["release_year"] is None
        assert details["original_title"] is None
        assert details["original_language"] is None
        assert details["countries"] == []

    def test_release_year_is_none_when_release_date_malformed(self, tmdb_client):
        response = Mock()
        response.json.return_value = {
            "genres": [],
            "credits": {"crew": []},
            "release_date": "not-a-date",
        }
        with patch("flask_backend.service.tmdb.requests.get", return_value=response):
            details = tmdb_client.get_movie_details(123)

        assert details["release_year"] is None

    def test_returns_collection_when_belongs_to_collection_present(self, tmdb_client):
        response = Mock()
        response.json.return_value = {
            "genres": [],
            "credits": {"crew": []},
            "belongs_to_collection": {
                "id": 10,
                "name": "Bacurau Collection",
                "poster_path": "/poster.jpg",
                "backdrop_path": "/backdrop.jpg",
            },
        }
        with patch("flask_backend.service.tmdb.requests.get", return_value=response):
            details = tmdb_client.get_movie_details(123)

        assert details["collection"] == {"id": 10, "name": "Bacurau Collection"}

    def test_returns_none_collection_when_belongs_to_collection_missing(
        self, tmdb_client
    ):
        response = Mock()
        response.json.return_value = {
            "genres": [],
            "credits": {"crew": []},
            "belongs_to_collection": None,
        }
        with patch("flask_backend.service.tmdb.requests.get", return_value=response):
            details = tmdb_client.get_movie_details(123)

        assert details["collection"] is None
