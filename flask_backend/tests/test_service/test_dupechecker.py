import json
from datetime import date

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.scripts.dupechecker import dupe_checker


class TestDupeChecker:
    def test_prints_duplicated_movies_grouped_by_cinema(
        self, app, setup_cinemas, capsys
    ):
        with app.app_context():
            capitolio_id = get_cinema_by_slug("capitolio").id

            for _ in range(2):
                movie = Movie(title="Filme Duplicado", slug="filme-duplicado")
                movie.screenings = [
                    Screening(
                        cinema_id=capitolio_id,
                        description="d",
                        image="poster.jpg",
                        dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                    )
                ]
                db_session.add(movie)
            db_session.commit()

        dupe_checker()

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert len(output) == 1
        assert output[0]["slug"] == "filme-duplicado"
        assert "capitolio" in output[0]["cinemas"]
        assert output[0]["cinemas"]["capitolio"]["dates"] == ["2026-08-01T19:00"]
        assert output[0]["cinemas"]["capitolio"]["images"] == ["poster.jpg"]

    def test_prints_empty_list_when_no_duplicates(self, app, setup_cinemas, capsys):
        with app.app_context():
            movie = Movie(title="Filme Único", slug="filme-unico")
            movie.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    dates=[ScreeningDate(date=date(2026, 8, 1), time="19:00")],
                )
            ]
            db_session.add(movie)
            db_session.commit()

        dupe_checker()

        captured = capsys.readouterr()
        assert json.loads(captured.out) == []
