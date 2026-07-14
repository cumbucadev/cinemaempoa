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
        with patch(
            "flask_backend.service.tmdb.requests.get",
            side_effect=requests.RequestException("boom"),
        ):
            with pytest.raises(requests.RequestException):
                tmdb_client.get_movie_details(123)
