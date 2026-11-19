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


def titles(result):
    return [movie.title for movie in result.movies]


@pytest.mark.usefixtures("setup_cinemas")
class TestSearchMovies:
    def test_text_filters_ignore_accents_and_case(self):
        show(
            make_movie(
                "Bacurau",
                directors=["Kleber Mendonça Filho"],
                genres=["Ação"],
                countries=["Brasil"],
            ),
            "capitolio",
            "2026-03-01",
        )
        show(
            make_movie(
                "Cléo das 5 às 7",
                directors=["Agnès Varda"],
                genres=["Drama"],
                countries=["França"],
            ),
            "capitolio",
            "2026-03-02",
        )

        assert titles(catalog_tools.search_movies(genre="acao")) == ["Bacurau"]
        assert titles(catalog_tools.search_movies(director="MENDONCA")) == ["Bacurau"]
        assert titles(catalog_tools.search_movies(country="franca")) == [
            "Cléo das 5 às 7"
        ]
        assert titles(catalog_tools.search_movies(title="cleo das 5")) == [
            "Cléo das 5 às 7"
        ]

    def test_title_also_matches_the_original_title(self):
        show(
            make_movie("Acossado", original_title="À bout de souffle"),
            "capitolio",
            "2026-03-01",
        )
        show(make_movie("Outro"), "capitolio", "2026-03-01")

        assert titles(catalog_tools.search_movies(title="a bout")) == ["Acossado"]

    def test_filters_combine_with_and(self):
        show(
            make_movie("Drama Francês", genres=["Drama"], countries=["França"]),
            "capitolio",
            "2026-03-01",
        )
        show(
            make_movie("Drama Brasileiro", genres=["Drama"], countries=["Brasil"]),
            "capitolio",
            "2026-03-01",
        )

        result = catalog_tools.search_movies(genre="drama", country="brasil")

        assert titles(result) == ["Drama Brasileiro"]

    def test_a_blank_filter_is_no_filter(self):
        show(make_movie("Sem Metadados"), "capitolio", "2026-03-01")

        result = catalog_tools.search_movies(genre=" ", cinema="", shown_from="")

        assert titles(result) == ["Sem Metadados"]

    def test_a_year_filter_leaves_out_movies_without_a_year(self):
        show(make_movie("De 1960", release_year=1960), "capitolio", "2026-03-01")
        show(make_movie("De 1975", release_year=1975), "capitolio", "2026-03-01")
        show(make_movie("Sem Ano"), "capitolio", "2026-03-01")

        assert titles(catalog_tools.search_movies(year_from=1960, year_to=1960)) == [
            "De 1960"
        ]
        assert titles(catalog_tools.search_movies(year_from=1970)) == ["De 1975"]
        assert titles(catalog_tools.search_movies(year_to=1970)) == ["De 1960"]

    def test_reports_each_movie_with_its_sessions(self):
        movie = make_movie(
            "Bacurau",
            original_title="Bacurau",
            release_year=2019,
            directors=["Kleber Mendonça Filho", "Juliano Dornelles"],
            genres=["Ação"],
            countries=["Brasil"],
        )
        show(movie, "capitolio", "2026-01-05 19:00", "2026-01-06 19:00")
        show(movie, "cine-cinco", "2026-04-02")

        result = catalog_tools.search_movies()

        assert result.today == TODAY
        assert result.catalog_since == date(2026, 1, 5)
        assert (result.total, result.truncated) == (1, False)
        assert result.movies[0].model_dump() == {
            "movie_id": movie.id,
            "title": "Bacurau",
            "original_title": "Bacurau",
            "release_year": 2019,
            "directors": ["Kleber Mendonça Filho", "Juliano Dornelles"],
            "genres": ["Ação"],
            "countries": ["Brasil"],
            "url": "https://cinemaempoa.com.br/movies/bacurau",
            "first_shown": date(2026, 1, 5),
            "last_shown": date(2026, 1, 6),
            "next_showing": date(2026, 4, 2),
            "cinemas": ["capitolio", "cine-cinco"],
            "sessions": 3,
        }

    def test_a_movie_without_a_slug_has_no_url(self):
        show(make_movie("Sem Slug", slug=None), "capitolio", "2026-03-01")

        assert catalog_tools.search_movies().movies[0].url is None

    def test_a_session_today_is_both_the_last_and_the_next(self):
        show(make_movie("Hoje"), "capitolio", "2026-03-10")
        show(make_movie("Só Futuro"), "capitolio", "2026-03-11")
        show(make_movie("Só Passado"), "capitolio", "2026-03-09")

        movies = {m.title: m for m in catalog_tools.search_movies().movies}

        assert (movies["Hoje"].last_shown, movies["Hoje"].next_showing) == (
            TODAY,
            TODAY,
        )
        assert movies["Só Futuro"].last_shown is None
        assert movies["Só Futuro"].next_showing == date(2026, 3, 11)
        assert movies["Só Passado"].last_shown == date(2026, 3, 9)
        assert movies["Só Passado"].next_showing is None

    def test_a_cinema_filter_narrows_the_sessions_that_count(self):
        both = make_movie("Nos Dois")
        show(both, "capitolio", "2026-01-10")
        show(both, "cine-cinco", "2026-02-20", "2026-03-20")
        show(make_movie("Só no Cinco"), "cine-cinco", "2026-03-01")

        result = catalog_tools.search_movies(cinema="Capitólio")

        assert titles(result) == ["Nos Dois"]
        movie = result.movies[0]
        assert (movie.first_shown, movie.last_shown, movie.next_showing) == (
            date(2026, 1, 10),
            date(2026, 1, 10),
            None,
        )
        assert movie.cinemas == ["capitolio"]
        assert movie.sessions == 1

    def test_a_shown_period_narrows_the_sessions_that_count(self):
        movie = make_movie("Reprise")
        show(movie, "capitolio", "2025-06-01", "2025-12-31", "2026-01-01")
        show(make_movie("De 2026"), "capitolio", "2026-02-01")

        result = catalog_tools.search_movies(
            shown_from="2025-06-01", shown_to="2025-12-31"
        )

        assert titles(result) == ["Reprise"]
        assert result.movies[0].last_shown == date(2025, 12, 31)
        assert result.movies[0].sessions == 2

    def test_sorts_by_last_shown_with_future_only_movies_at_the_end(self):
        show(make_movie("Mais Longe"), "capitolio", "2026-05-01")
        show(make_movie("Mais Perto"), "capitolio", "2026-04-01")
        show(make_movie("Antigo"), "capitolio", "2025-01-01")
        show(make_movie("Recente"), "capitolio", "2026-03-01", "2026-06-01")

        assert titles(catalog_tools.search_movies()) == [
            "Recente",
            "Antigo",
            "Mais Perto",
            "Mais Longe",
        ]

    def test_sorts_by_first_shown_or_by_title(self):
        show(make_movie("água"), "capitolio", "2026-02-01")
        show(make_movie("Zebra"), "capitolio", "2026-01-01")
        show(make_movie("Árvore"), "capitolio", "2026-03-01")

        assert titles(catalog_tools.search_movies(sort="first_shown_asc")) == [
            "Zebra",
            "água",
            "Árvore",
        ]
        assert titles(catalog_tools.search_movies(sort="title")) == [
            "água",
            "Árvore",
            "Zebra",
        ]

    def test_ties_are_broken_by_movie_id(self):
        first = make_movie("Empate", slug="empate-1")
        second = make_movie("Empate", slug="empate-2")
        show(second, "capitolio", "2026-03-01")
        show(first, "capitolio", "2026-03-01")

        for sort in ("last_shown_desc", "first_shown_asc", "title"):
            result = catalog_tools.search_movies(sort=sort)
            assert [m.movie_id for m in result.movies] == [first.id, second.id]

    def test_limit_cuts_the_list_and_says_so(self):
        for day in range(1, 4):
            show(make_movie(f"Filme {day}"), "capitolio", f"2026-03-0{day}")

        result = catalog_tools.search_movies(limit=2)

        assert titles(result) == ["Filme 3", "Filme 2"]
        assert (result.total, result.truncated) == (3, True)
        assert len(catalog_tools.search_movies(limit=0).movies) == 1

    def test_limit_is_capped_at_50(self):
        for number in range(52):
            show(make_movie(f"Filme {number:02}"), "capitolio", "2026-03-01")

        result = catalog_tools.search_movies(limit=500)

        assert len(result.movies) == 50
        assert (result.total, result.truncated) == (52, True)

    def test_drafts_do_not_exist(self):
        published = make_movie("Publicado")
        show(published, "capitolio", "2026-03-01")
        show(published, "cine-cinco", "2026-03-05", draft=True)
        show(make_movie("Rascunho"), "capitolio", "2026-03-02", draft=True)

        result = catalog_tools.search_movies()

        assert titles(result) == ["Publicado"]
        assert result.movies[0].last_shown == date(2026, 3, 1)
        assert result.movies[0].cinemas == ["capitolio"]

    def test_refuses_a_period_that_ends_before_it_starts(self):
        with pytest.raises(CatalogToolError) as error:
            catalog_tools.search_movies(shown_from="2026-03-02", shown_to="2026-03-01")

        assert str(error.value) == (
            "Período inválido: a data final (2026-03-01) é anterior à "
            "inicial (2026-03-02)."
        )

    def test_refuses_an_invalid_date_or_cinema(self):
        with pytest.raises(CatalogToolError, match="Data inválida: 'ontem'"):
            catalog_tools.search_movies(shown_from="ontem")
        with pytest.raises(CatalogToolError, match="Cinema 'x' não encontrado"):
            catalog_tools.search_movies(cinema="x")


def programme(schedule):
    """The schedule as {cinema slug: [movie title, ...]}."""
    return {
        cinema.slug: [movie.title for movie in cinema.movies]
        for cinema in schedule.cinemas
    }


@pytest.mark.usefixtures("setup_cinemas")
class TestGetSchedule:
    def test_defaults_to_today(self):
        show(make_movie("Ontem"), "capitolio", "2026-03-09 19:00")
        show(make_movie("Hoje"), "capitolio", "2026-03-10 19:00")
        show(make_movie("Amanhã"), "capitolio", "2026-03-11 19:00")

        schedule = catalog_tools.get_schedule()

        assert (schedule.today, schedule.date_from, schedule.date_to) == (
            TODAY,
            TODAY,
            TODAY,
        )
        assert programme(schedule) == {"capitolio": ["Hoje"]}

    def test_date_to_defaults_to_date_from(self):
        show(make_movie("No Dia"), "capitolio", "2026-03-14")
        show(make_movie("Depois"), "capitolio", "2026-03-15")

        schedule = catalog_tools.get_schedule(date_from="2026-03-14")

        assert schedule.date_to == date(2026, 3, 14)
        assert programme(schedule) == {"capitolio": ["No Dia"]}

    def test_lists_each_cinema_with_its_movies_and_their_times(self):
        movie = make_movie(
            "Bacurau", directors=["Kleber Mendonça Filho"], genres=["Ação"]
        )
        show(
            movie,
            "capitolio",
            "2026-03-11 19:30",
            "2026-03-10 21:00",
            "2026-03-10 14:00",
            "2026-03-10",
            "2026-03-12",
        )

        schedule = catalog_tools.get_schedule(
            date_from="2026-03-10", date_to="2026-03-12"
        )

        assert (schedule.total, schedule.truncated) == (1, False)
        assert [cinema.model_dump() for cinema in schedule.cinemas] == [
            {
                "slug": "capitolio",
                "name": "Cinemateca Capitólio",
                "movies": [
                    {
                        "movie_id": movie.id,
                        "title": "Bacurau",
                        "directors": ["Kleber Mendonça Filho"],
                        "genres": ["Ação"],
                        "url": "https://cinemaempoa.com.br/movies/bacurau",
                        "sessions": [
                            {"date": date(2026, 3, 10), "times": ["14:00", "21:00"]},
                            {"date": date(2026, 3, 11), "times": ["19:30"]},
                            {"date": date(2026, 3, 12), "times": []},
                        ],
                    }
                ],
            }
        ]

    def test_orders_cinemas_by_name_and_movies_by_their_first_session(self):
        show(make_movie("Tarde"), "sala-redencao", "2026-03-10 16:00")
        show(make_movie("Noite"), "capitolio", "2026-03-10 20:00")
        show(make_movie("Amanhã Cedo"), "capitolio", "2026-03-11 10:00")
        show(make_movie("Matinê"), "capitolio", "2026-03-10 14:00")

        schedule = catalog_tools.get_schedule(
            date_from="2026-03-10", date_to="2026-03-11"
        )

        assert list(programme(schedule).items()) == [
            ("capitolio", ["Matinê", "Noite", "Amanhã Cedo"]),
            ("sala-redencao", ["Tarde"]),
        ]

    def test_joins_two_screenings_of_a_movie_at_the_same_cinema(self):
        movie = make_movie("Duas Vezes")
        show(movie, "capitolio", "2026-03-10 14:00")
        show(movie, "capitolio", "2026-03-10 19:00")

        schedule = catalog_tools.get_schedule()

        assert (schedule.total, programme(schedule)) == (
            1,
            {"capitolio": ["Duas Vezes"]},
        )
        assert schedule.cinemas[0].movies[0].sessions[0].times == ["14:00", "19:00"]

    def test_a_cinema_filter_leaves_the_others_out(self):
        show(make_movie("No Capitólio"), "capitolio", "2026-03-10")
        show(make_movie("Na Redenção"), "sala-redencao", "2026-03-10")

        schedule = catalog_tools.get_schedule(cinema="redenção")

        assert programme(schedule) == {"sala-redencao": ["Na Redenção"]}

    def test_drafts_do_not_exist(self):
        show(make_movie("Rascunho"), "capitolio", "2026-03-10", draft=True)

        schedule = catalog_tools.get_schedule()

        assert (schedule.total, schedule.cinemas) == (0, [])

    def test_accepts_14_days_and_refuses_more(self):
        catalog_tools.get_schedule(date_from="2026-03-01", date_to="2026-03-14")

        with pytest.raises(CatalogToolError) as error:
            catalog_tools.get_schedule(date_from="2026-03-01", date_to="2026-03-15")

        assert str(error.value) == (
            "Período longo demais: get_schedule aceita no máximo 14 dias e "
            "foram pedidos 15. Para períodos maiores, use search_movies com "
            "shown_from e shown_to."
        )

    def test_refuses_an_invalid_date_or_a_period_that_ends_before_it_starts(self):
        with pytest.raises(CatalogToolError, match="Data inválida: 'sábado'"):
            catalog_tools.get_schedule(date_from="sábado")
        with pytest.raises(CatalogToolError, match="Período inválido"):
            catalog_tools.get_schedule(date_to="2026-03-09")

    def test_cuts_at_60_cinema_movie_pairs(self):
        for number in range(40):
            show(make_movie(f"Capitólio {number:02}"), "capitolio", "2026-03-10 19:00")
        for number in range(25):
            show(make_movie(f"Redenção {number:02}"), "sala-redencao", "2026-03-10")

        schedule = catalog_tools.get_schedule()

        assert (schedule.total, schedule.truncated) == (65, True)
        assert [(c.slug, len(c.movies)) for c in schedule.cinemas] == [
            ("capitolio", 40),
            ("sala-redencao", 20),
        ]


class TestListCinemas:
    def test_lists_the_cinemas_by_name_with_where_to_find_them(self):
        make_cinema("sala-redencao", "Sala Redenção")
        make_cinema(
            "capitolio",
            "Cinemateca Capitólio",
            address="Rua Demétrio Ribeiro, 1085",
            opening_hours="Terça a domingo",
            instagram_url="https://instagram.com/cinematecacapitolio",
        )

        result = catalog_tools.list_cinemas()

        assert [cinema.model_dump() for cinema in result.cinemas] == [
            {
                "slug": "capitolio",
                "name": "Cinemateca Capitólio",
                "short_name": "Capitólio",
                "address": "Rua Demétrio Ribeiro, 1085",
                "opening_hours": "Terça a domingo",
                "website": "https://capitolio.example",
                "instagram_url": "https://instagram.com/cinematecacapitolio",
                "page_url": "https://cinemaempoa.com.br/cinemas/capitolio",
            },
            {
                "slug": "sala-redencao",
                "name": "Sala Redenção",
                "short_name": "Sala Redenção",
                "address": None,
                "opening_hours": None,
                "website": "https://sala-redencao.example",
                "instagram_url": None,
                "page_url": "https://cinemaempoa.com.br/cinemas/sala-redencao",
            },
        ]

    @pytest.mark.usefixtures("setup_cinemas")
    def test_says_what_the_catalog_covers(self):
        show(make_movie("Antigo", tmdb_id=1), "capitolio", "2025-01-02")
        show(make_movie("Futuro"), "cine-cinco", "2026-08-28")
        show(make_movie("Rascunho"), "capitolio", "2024-01-01", draft=True)

        result = catalog_tools.list_cinemas()

        assert result.today == TODAY
        assert result.catalog_since == date(2025, 1, 2)
        assert result.catalog_until == date(2026, 8, 28)
        assert result.metadata_coverage.model_dump() == {
            "movies_total": 2,
            "with_tmdb": 1,
            "with_directors": 0,
            "with_genres": 0,
            "with_countries": 0,
        }


@pytest.mark.usefixtures("setup_cinemas")
class TestGetMovie:
    def test_describes_the_movie_and_each_of_its_screenings(self):
        movie = make_movie(
            "Acossado",
            original_title="À bout de souffle",
            release_year=1960,
            original_language="fr",
            directors=["Jean-Luc Godard"],
            genres=["Drama"],
            countries=["França"],
        )
        show(
            movie,
            "sala-redencao",
            "2026-03-12 19:00",
            "2026-03-10 16:00",
            "2026-03-10 14:00",
            "2026-03-09 19:00",
            "2026-03-09 16:00",
            "2025-11-02",
            description="Mostra Nouvelle Vague.",
            url="https://sala.example/acossado",
        )
        show(movie, "capitolio", "2025-06-01", description="Clássico.")

        result = catalog_tools.get_movie(movie.id)

        assert result.model_dump() == {
            "today": TODAY,
            "movie_id": movie.id,
            "title": "Acossado",
            "original_title": "À bout de souffle",
            "release_year": 1960,
            "original_language": "fr",
            "directors": ["Jean-Luc Godard"],
            "genres": ["Drama"],
            "countries": ["França"],
            "url": "https://cinemaempoa.com.br/movies/acossado",
            "screenings": [
                {
                    "cinema": "capitolio",
                    "cinema_name": "Cinemateca Capitólio",
                    "description": "Clássico.",
                    "source_url": None,
                    "upcoming": [],
                    "upcoming_total": 0,
                    "past_first": date(2025, 6, 1),
                    "past_last": date(2025, 6, 1),
                    "past_count": 1,
                },
                {
                    "cinema": "sala-redencao",
                    "cinema_name": "Sala Redenção",
                    "description": "Mostra Nouvelle Vague.",
                    "source_url": "https://sala.example/acossado",
                    "upcoming": [
                        {"date": date(2026, 3, 10), "times": ["14:00", "16:00"]},
                        {"date": date(2026, 3, 12), "times": ["19:00"]},
                    ],
                    "upcoming_total": 2,
                    "past_first": date(2025, 11, 2),
                    "past_last": date(2026, 3, 9),
                    "past_count": 2,
                },
            ],
        }

    def test_a_screening_only_ahead_has_no_past(self):
        movie = make_movie("Estreia")
        show(movie, "capitolio", "2026-03-20")

        screening = catalog_tools.get_movie(movie.id).screenings[0]

        assert (screening.past_first, screening.past_last, screening.past_count) == (
            None,
            None,
            0,
        )

    def test_cuts_upcoming_at_30_dates_and_the_description_at_1500_chars(self):
        movie = make_movie("Em Cartaz")
        days = [f"2026-04-{day:02}" for day in range(1, 31)] + ["2026-05-01"]
        show(movie, "capitolio", *days, description="x" * 2000)

        screening = catalog_tools.get_movie(movie.id).screenings[0]

        assert len(screening.upcoming) == 30
        assert screening.upcoming[-1].date == date(2026, 4, 30)
        assert screening.upcoming_total == 31
        assert screening.description == "x" * 1500

    def test_leaves_draft_screenings_out(self):
        movie = make_movie("Meio Publicado")
        show(movie, "capitolio", "2026-03-01")
        show(movie, "cine-cinco", "2026-03-02", draft=True)

        result = catalog_tools.get_movie(movie.id)

        assert [screening.cinema for screening in result.screenings] == ["capitolio"]

    def test_a_movie_that_is_unknown_or_only_drafted_is_not_found(self):
        drafted = make_movie("Rascunho")
        show(drafted, "capitolio", "2026-03-01", draft=True)

        for movie_id in (drafted.id, 9999):
            with pytest.raises(CatalogToolError) as error:
                catalog_tools.get_movie(movie_id)
            assert str(error.value) == f"Filme {movie_id} não encontrado."
