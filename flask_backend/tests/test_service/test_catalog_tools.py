from datetime import date

import pytest

from flask_backend.db import db_session
from flask_backend.models import (
    Cinema,
    Country,
    Director,
    Genre,
    Movie,
    Screening,
    ScreeningDate,
)
from flask_backend.service import catalog_tools
from flask_backend.service.catalog_tools import CatalogToolError

TODAY = date(2026, 3, 10)


@pytest.fixture(autouse=True)
def app_context(app):
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(catalog_tools, "today", lambda: TODAY)


def _named(model, name):
    """The `model` row called `name`, created on first use, so two movies
    can share a director, genre or country."""
    row = db_session.query(model).filter(model.name == name).first()
    return row or model(name=name)


def make_movie(title, directors=(), genres=(), countries=(), **fields):
    fields.setdefault("slug", title.lower().replace(" ", "-"))
    movie = Movie(title=title, **fields)
    movie.directors = [_named(Director, name) for name in directors]
    movie.genres = [_named(Genre, name) for name in genres]
    movie.countries = [_named(Country, name) for name in countries]
    db_session.add(movie)
    db_session.commit()
    return movie


def make_cinema(slug, name, **fields):
    cinema = Cinema(slug=slug, name=name, url=f"https://{slug}.example", **fields)
    db_session.add(cinema)
    db_session.commit()
    return cinema


def cinema(slug):
    return db_session.query(Cinema).filter(Cinema.slug == slug).one()


def show(movie, cinema_slug, *sessions, draft=False, **fields):
    """Adds a screening of `movie` at the cinema. Each session is a
    "YYYY-MM-DD" date, optionally followed by a time: "2026-03-10 19:30"."""
    fields.setdefault("description", f"Sessão de {movie.title}.")
    screening = Screening(
        movie_id=movie.id, cinema_id=cinema(cinema_slug).id, draft=draft, **fields
    )
    for session in sessions:
        day, _, time = session.partition(" ")
        screening.dates.append(
            ScreeningDate(date=date.fromisoformat(day), time=time or None)
        )
    db_session.add(screening)
    db_session.commit()
    return screening


class TestNormalize:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("Capitólio", "capitolio"),
            ("AÇÃO", "acao"),
            ("sala-redencao", "sala redencao"),
            ("paulo_amorim", "paulo amorim"),
            ("  Cine   Cinco \n", "cine cinco"),
        ],
    )
    def test_ignores_accents_case_separators_and_extra_spaces(self, text, expected):
        assert catalog_tools.normalize(text) == expected


class TestToday:
    def test_is_the_date_in_sao_paulo_not_in_utc(self, monkeypatch):
        from datetime import datetime, timezone

        class LateEveningInSaoPaulo(datetime):
            @classmethod
            def now(cls, tz=None):
                # 01:30 UTC on the 11th is 22:30 on the 10th in São Paulo.
                return datetime(2026, 3, 11, 1, 30, tzinfo=timezone.utc).astimezone(tz)

        monkeypatch.undo()
        monkeypatch.setattr(catalog_tools, "datetime", LateEveningInSaoPaulo)

        assert catalog_tools.today() == date(2026, 3, 10)


@pytest.mark.usefixtures("setup_cinemas")
class TestResolveCinema:
    @pytest.mark.parametrize(
        "text, slug",
        [
            ("capitolio", "capitolio"),
            ("capitólio", "capitolio"),
            ("Capitolio", "capitolio"),
            ("Cinemateca Capitólio", "capitolio"),
            ("sala redencao", "sala-redencao"),
            ("SALA-REDENÇÃO", "sala-redencao"),
            ("redenção", "sala-redencao"),
            ("Paulo Amorim", "paulo-amorim"),
            ("bancarios", "cinebancarios"),
        ],
    )
    def test_finds_the_cinema_by_slug_name_or_short_name(self, text, slug):
        assert catalog_tools.resolve_cinema(text).slug == slug

    def test_an_exact_name_wins_over_being_part_of_another(self):
        make_cinema("cine-cinco-anexo", "Cine Cinco Anexo")

        assert catalog_tools.resolve_cinema("cine cinco").slug == "cine-cinco"

    @pytest.mark.parametrize("text", ["cinemateca", "cine", "drive-in"])
    def test_an_ambiguous_or_unknown_cinema_lists_the_valid_slugs(self, text):
        with pytest.raises(CatalogToolError) as error:
            catalog_tools.resolve_cinema(text)

        assert str(error.value) == (
            f"Cinema '{text}' não encontrado. Use um destes slugs: "
            "capitolio, cine-cinco, cinebancarios, paulo-amorim, sala-redencao."
        )


class TestParseDate:
    def test_reads_an_iso_date(self):
        assert catalog_tools.parse_date("2026-03-10") == date(2026, 3, 10)

    @pytest.mark.parametrize("text", ["10/03/2026", "amanhã", "2026-02-30"])
    def test_refuses_anything_else(self, text):
        with pytest.raises(CatalogToolError) as error:
            catalog_tools.parse_date(text)

        assert str(error.value) == (
            f"Data inválida: '{text}'. Use o formato AAAA-MM-DD."
        )


@pytest.mark.usefixtures("setup_cinemas")
class TestCatalogCoverage:
    def test_the_period_spans_the_published_sessions(self):
        show(make_movie("Antigo"), "capitolio", "2025-01-02")
        show(make_movie("Futuro"), "cine-cinco", "2026-08-28", "2026-04-01")
        show(make_movie("Rascunho"), "capitolio", "2024-01-01", draft=True)

        assert catalog_tools.catalog_period() == (
            date(2025, 1, 2),
            date(2026, 8, 28),
        )

    def test_the_period_of_an_empty_catalog_is_unknown(self):
        assert catalog_tools.catalog_period() == (None, None)

    def test_metadata_coverage_counts_the_published_movies(self):
        full = make_movie(
            "Completo",
            directors=["Agnès Varda"],
            genres=["Drama"],
            countries=["França"],
            tmdb_id=1,
        )
        show(full, "capitolio", "2026-03-01")
        show(full, "cine-cinco", "2026-03-02")
        show(make_movie("Só TMDB", tmdb_id=2), "capitolio", "2026-03-01")
        show(make_movie("Sem nada"), "capitolio", "2026-03-01")
        show(make_movie("Rascunho", tmdb_id=3), "capitolio", "2026-03-01", draft=True)
        make_movie("Sem sessão", tmdb_id=4)

        assert catalog_tools.metadata_coverage().model_dump() == {
            "movies_total": 3,
            "with_tmdb": 2,
            "with_directors": 1,
            "with_genres": 1,
            "with_countries": 1,
        }
