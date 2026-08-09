from datetime import date
from io import BytesIO
from typing import Optional

from PIL import Image

from flask_backend.db import db_session
from flask_backend.models import Cinema, Movie, Screening, ScreeningDate
from flask_backend.service.shared import get_weekend_dates


def _fake_png_bytes():
    img = Image.new("RGB", (300, 450), (200, 50, 50))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _get_cinema(slug="capitolio"):
    return db_session.query(Cinema).filter_by(slug=slug).first()


def _create_screening(
    cinema_slug="capitolio",
    movie_title="Test Movie",
    image=None,
    image_width=None,
    image_height=None,
    screening_date: Optional[date] = None,
    screening_time="20:00",
):
    cinema = _get_cinema(cinema_slug)
    movie = Movie(title=movie_title, slug=movie_title.lower().replace(" ", "-"))
    db_session.add(movie)
    db_session.commit()

    screening = Screening(
        movie_id=movie.id,
        cinema_id=cinema.id,
        description="A description",
        image=image,
        image_width=image_width,
        image_height=image_height,
        dates=[ScreeningDate(date=screening_date or date.today(), time=screening_time)],
    )
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    return screening.id


class TestAdminWeekendRequiresLogin:
    def test_admin_weekend_requires_login(self, client, setup_cinemas):
        response = client.get("/admin/weekend")
        assert response.status_code == 302
        assert b"/auth/login" in response.data


class TestAdminWeekendIndex:
    def test_admin_weekend_with_auth_returns_200(self, auth_headers, setup_cinemas):
        response = auth_headers.get("/admin/weekend")
        assert response.status_code == 200

    def test_admin_weekend_shows_no_images_when_no_screenings(
        self, auth_headers, setup_cinemas
    ):
        response = auth_headers.get("/admin/weekend")
        html = response.get_data(as_text=True)
        assert html.count("data:image/png;base64,") == 0
        assert "Nenhuma sessão programada" in html

    def test_admin_weekend_renders_one_image_for_a_day_with_few_screenings(
        self, auth_headers, setup_cinemas
    ):
        friday_date, _, _ = get_weekend_dates(date.today())
        with auth_headers.application.app_context():
            _create_screening(movie_title="Filme Sexta", screening_date=friday_date)
        response = auth_headers.get("/admin/weekend")
        assert response.get_data(as_text=True).count("data:image/png;base64,") == 1

    def test_admin_weekend_splits_into_multiple_parts_for_many_screenings(
        self, auth_headers, setup_cinemas
    ):
        friday_date, _, _ = get_weekend_dates(date.today())
        with auth_headers.application.app_context():
            for i in range(40):
                _create_screening(
                    movie_title=f"Filme Longo Numero {i} Com Título Bem Grande",
                    screening_date=friday_date,
                )
        response = auth_headers.get("/admin/weekend")
        assert response.get_data(as_text=True).count("data:image/png;base64,") >= 2

    def test_admin_weekend_shows_no_cover_when_no_screenings_have_images(
        self, auth_headers, setup_cinemas
    ):
        friday_date, _, _ = get_weekend_dates(date.today())
        with auth_headers.application.app_context():
            _create_screening(
                movie_title="Filme Sem Poster", screening_date=friday_date
            )
        response = auth_headers.get("/admin/weekend")
        html = response.get_data(as_text=True)
        assert "Capa" not in html

    def test_admin_weekend_shows_cover_when_a_screening_has_an_image(
        self, auth_headers, setup_cinemas, monkeypatch
    ):
        monkeypatch.setattr(
            "flask_backend.service.weekend_export._load_poster_bytes",
            lambda _image_path, _upload_folder: _fake_png_bytes(),
        )
        friday_date, _, _ = get_weekend_dates(date.today())
        with auth_headers.application.app_context():
            _create_screening(
                movie_title="Filme Com Poster",
                screening_date=friday_date,
                image="/screening/assets/poster.jpg",
                image_width=300,
                image_height=450,
            )
        response = auth_headers.get("/admin/weekend")
        html = response.get_data(as_text=True)
        assert "Capa" in html
        assert html.count("data:image/png;base64,") == 2  # cover + 1 day image
