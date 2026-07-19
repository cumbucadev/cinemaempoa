from datetime import datetime
from unittest.mock import Mock, patch

from flask_backend.db import db_session
from flask_backend.models import (
    Collection,
    Country,
    Director,
    Genre,
    Movie,
    MovieMetadataFetchAttempt,
)
from flask_backend.service.movie_metadata_pipeline import run_pipeline


def _create_movie(title, slug):
    movie = Movie(title=title, slug=slug)
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


def _tmdb_client(search_result=None, details=None, raise_on_details=None):
    client = Mock()
    client.search_movie.return_value = search_result
    if raise_on_details is not None:
        client.get_movie_details.side_effect = raise_on_details
    else:
        client.get_movie_details.return_value = details
    return client


class TestRunPipeline:
    def test_happy_path_persists_directors_and_genres(self, client, app):
        with client.application.app_context():
            movie = _create_movie("Lobo e Cão", "lobo-e-cao")
            movie_id = movie.id

            tmdb_client = _tmdb_client(
                search_result={"id": 999},
                details={
                    "genres": [{"id": 28, "name": "Ação"}],
                    "directors": [{"id": 42, "name": "Jane Director"}],
                    "original_title": "Cão e Lobo",
                    "release_year": 2025,
                    "original_language": "pt",
                    "countries": [{"iso_3166_1": "BR", "name": "Brazil"}],
                },
            )
            with patch(
                "flask_backend.service.movie_metadata_pipeline.TMDBClient",
                return_value=tmdb_client,
            ):
                result = run_pipeline()

            assert result.metadata_found == 1
            assert result.processed == 1

            movie = db_session.query(Movie).filter(Movie.id == movie_id).first()
            assert [d.name for d in movie.directors] == ["Jane Director"]
            assert [g.name for g in movie.genres] == ["Ação"]
            assert movie.original_title == "Cão e Lobo"
            assert movie.release_year == 2025
            assert movie.original_language == "pt"
            assert [c.name for c in movie.countries] == ["Brazil"]

            attempts = (
                db_session.query(MovieMetadataFetchAttempt)
                .filter(MovieMetadataFetchAttempt.movie_id == movie_id)
                .all()
            )
            assert len(attempts) == 1
            assert attempts[0].status == "success"
            assert attempts[0].source == "tmdb"

    def test_happy_path_sets_collection_when_present(self, client, app):
        with client.application.app_context():
            movie = _create_movie("Bacurau 2", "bacurau-2")
            movie_id = movie.id

            tmdb_client = _tmdb_client(
                search_result={"id": 999},
                details={
                    "genres": [],
                    "directors": [],
                    "countries": [],
                    "collection": {"id": 10, "name": "Bacurau Collection"},
                },
            )
            with patch(
                "flask_backend.service.movie_metadata_pipeline.TMDBClient",
                return_value=tmdb_client,
            ):
                run_pipeline()

            movie = db_session.query(Movie).filter(Movie.id == movie_id).first()
            assert movie.collection is not None
            assert movie.collection.name == "Bacurau Collection"

            collections = (
                db_session.query(Collection).filter(Collection.tmdb_id == 10).all()
            )
            assert len(collections) == 1

    def test_leaves_collection_unset_and_does_not_abort_batch_when_name_missing(
        self, client, app
    ):
        with client.application.app_context():
            no_name_movie = _create_movie("Bacurau 3", "bacurau-3")
            no_name_movie_id = no_name_movie.id
            other_movie = _create_movie("Outro Filme", "outro-filme")
            other_movie_id = other_movie.id

            tmdb_client = _tmdb_client(
                search_result={"id": 999},
                details={
                    "genres": [],
                    "directors": [],
                    "countries": [],
                    "collection": {"id": 10, "name": None},
                },
            )
            with patch(
                "flask_backend.service.movie_metadata_pipeline.TMDBClient",
                return_value=tmdb_client,
            ):
                result = run_pipeline()

            # both movies were processed - a missing collection name on the
            # first one must not raise and abort the rest of the batch
            assert result.processed == 2

            no_name_movie = (
                db_session.query(Movie).filter(Movie.id == no_name_movie_id).first()
            )
            assert no_name_movie.collection_id is None
            assert db_session.query(Collection).filter_by(tmdb_id=10).first() is None

            other_movie = (
                db_session.query(Movie).filter(Movie.id == other_movie_id).first()
            )
            assert other_movie is not None

    def test_happy_path_leaves_collection_unset_when_absent(self, client, app):
        with client.application.app_context():
            movie = _create_movie("Filme Solo", "filme-solo")
            movie_id = movie.id

            tmdb_client = _tmdb_client(
                search_result={"id": 999},
                details={"genres": [], "directors": [], "countries": []},
            )
            with patch(
                "flask_backend.service.movie_metadata_pipeline.TMDBClient",
                return_value=tmdb_client,
            ):
                run_pipeline()

            movie = db_session.query(Movie).filter(Movie.id == movie_id).first()
            assert movie.collection_id is None

    def test_not_found_on_tmdb_search(self, client, app):
        with client.application.app_context():
            movie = _create_movie("Filme Inexistente", "filme-inexistente")
            movie_id = movie.id

            tmdb_client = _tmdb_client(search_result=None)
            with patch(
                "flask_backend.service.movie_metadata_pipeline.TMDBClient",
                return_value=tmdb_client,
            ):
                result = run_pipeline()

            assert result.metadata_not_found == 1

            movie = db_session.query(Movie).filter(Movie.id == movie_id).first()
            assert movie.directors == []
            assert movie.genres == []

            attempts = (
                db_session.query(MovieMetadataFetchAttempt)
                .filter(MovieMetadataFetchAttempt.movie_id == movie_id)
                .all()
            )
            assert len(attempts) == 1
            assert attempts[0].status == "not_found"

    def test_records_error_on_exception(self, client, app):
        with client.application.app_context():
            movie = _create_movie("Filme Com Erro", "filme-com-erro")
            movie_id = movie.id

            tmdb_client = _tmdb_client(
                search_result={"id": 999}, raise_on_details=RuntimeError("boom")
            )
            with patch(
                "flask_backend.service.movie_metadata_pipeline.TMDBClient",
                return_value=tmdb_client,
            ):
                result = run_pipeline()

            assert result.errors == 1

            attempts = (
                db_session.query(MovieMetadataFetchAttempt)
                .filter(MovieMetadataFetchAttempt.movie_id == movie_id)
                .all()
            )
            assert len(attempts) == 1
            assert attempts[0].status == "error"
            assert "boom" in attempts[0].error_message

    def test_skips_movie_with_all_sources_exhausted(self, client, app):
        with client.application.app_context():
            movie = _create_movie("Já Tentado", "ja-tentado")
            db_session.add(
                MovieMetadataFetchAttempt(
                    movie_id=movie.id,
                    source="tmdb",
                    status="not_found",
                    attempted_at=datetime.now(),
                )
            )
            db_session.commit()

            tmdb_client = Mock()
            with patch(
                "flask_backend.service.movie_metadata_pipeline.TMDBClient",
                return_value=tmdb_client,
            ):
                result = run_pipeline()

            assert result.skipped_all_sources_tried == 1
            tmdb_client.search_movie.assert_not_called()

    def test_dedupes_genres_directors_and_countries_across_movies(self, client, app):
        with client.application.app_context():
            movie_a = _create_movie("Filme A", "filme-a")
            movie_b = _create_movie("Filme B", "filme-b")
            movie_a_id, movie_b_id = movie_a.id, movie_b.id

            details = {
                "genres": [{"id": 28, "name": "Ação"}],
                "directors": [{"id": 42, "name": "Jane Director"}],
                "countries": [{"iso_3166_1": "BR", "name": "Brazil"}],
            }

            with patch(
                "flask_backend.service.movie_metadata_pipeline.TMDBClient",
                side_effect=lambda: _tmdb_client(
                    search_result={"id": 999}, details=details
                ),
            ):
                run_pipeline()

            genres = db_session.query(Genre).filter(Genre.tmdb_id == 28).all()
            directors = db_session.query(Director).filter(Director.tmdb_id == 42).all()
            countries = (
                db_session.query(Country).filter(Country.iso_3166_1 == "BR").all()
            )
            assert len(genres) == 1
            assert len(directors) == 1
            assert len(countries) == 1

            movie_a = db_session.query(Movie).filter(Movie.id == movie_a_id).first()
            movie_b = db_session.query(Movie).filter(Movie.id == movie_b_id).first()
            assert genres[0] in movie_a.genres
            assert genres[0] in movie_b.genres
            assert directors[0] in movie_a.directors
            assert directors[0] in movie_b.directors
            assert countries[0] in movie_a.countries
            assert countries[0] in movie_b.countries
