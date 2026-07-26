import io
from datetime import date, datetime, timedelta
from typing import Optional
from unittest.mock import MagicMock, patch

from flask import url_for
from google.genai.errors import ClientError, ServerError

from flask_backend.db import db_session
from flask_backend.models import AlertAction, Cinema, Movie, Screening, ScreeningDate
from flask_backend.service.shared import get_weekend_dates


def _get_cinema(slug="capitolio"):
    return db_session.query(Cinema).filter_by(slug=slug).first()


def _create_screening(
    cinema_slug="capitolio",
    movie_title="Test Movie",
    draft=False,
    image=None,
    image_width=None,
    image_height=None,
    image_alt=None,
    screening_date: Optional[date] = None,
    screening_time="20:00",
    movie_id: Optional[int] = None,
):
    cinema = _get_cinema(cinema_slug)
    if movie_id is None:
        movie = Movie(title=movie_title, slug=movie_title.lower().replace(" ", "-"))
        db_session.add(movie)
        db_session.commit()
        movie_id = movie.id

    screening = Screening(
        movie_id=movie_id,
        cinema_id=cinema.id,
        description="A description",
        draft=draft,
        image=image,
        image_width=image_width,
        image_height=image_height,
        image_alt=image_alt,
        dates=[ScreeningDate(date=screening_date or date.today(), time=screening_time)],
    )
    db_session.add(screening)
    db_session.commit()
    db_session.refresh(screening)
    return screening.id


def _valid_create_form(**overrides):
    form = {
        "movie_title": "Novo Filme",
        "description": "Uma descrição qualquer.",
        "screening_dates": ["2026-08-01T19:00"],
        "status": "published",
    }
    form.update(overrides)
    return form


class TestScreeningIndex:
    def test_index_returns_200(self, client, setup_cinemas):
        response = client.get("/")
        assert response.status_code == 200

    def test_index_lists_published_screening_for_today(self, client, setup_cinemas):
        with client.application.app_context():
            _create_screening(
                movie_title="Filme Publicado",
                image="poster.jpg",
                image_width=100,
                image_height=200,
            )
        response = client.get("/")
        assert b"Filme Publicado" in response.data

    def test_index_hides_draft_screening_when_not_logged_in(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            _create_screening(movie_title="Filme Rascunho", draft=True)
        response = client.get("/")
        assert b"Filme Rascunho" not in response.data

    def test_index_shows_draft_screening_when_logged_in(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            _create_screening(movie_title="Filme Rascunho Logado", draft=True)
        response = auth_headers.get("/")
        assert b"Filme Rascunho Logado" in response.data


class TestScreeningIndexAltBadge:
    def test_shows_alt_badge_when_image_alt_present(self, client, setup_cinemas):
        with client.application.app_context():
            _create_screening(
                movie_title="Filme Com Alt",
                image="poster.jpg",
                image_width=100,
                image_height=200,
                image_alt="Descrição do poster",
            )
        response = client.get("/")
        html = response.get_data(as_text=True)
        assert 'class="alt-badge' in html
        assert 'data-bs-content="Descrição do poster"' in html

    def test_hides_alt_badge_when_image_alt_missing(self, client, setup_cinemas):
        with client.application.app_context():
            _create_screening(
                movie_title="Filme Sem Alt",
                image="poster.jpg",
                image_width=100,
                image_height=200,
            )
        response = client.get("/")
        html = response.get_data(as_text=True)
        assert 'class="alt-badge' not in html


class TestScreeningWeekend:
    def test_weekend_returns_200(self, client, setup_cinemas):
        response = client.get("/weekend")
        assert response.status_code == 200

    def test_weekend_links_to_export_page(self, client, setup_cinemas):
        response = client.get("/weekend")
        assert b"/weekend/export" in response.data


class TestScreeningWeekendExport:
    def test_weekend_export_returns_200(self, client, setup_cinemas):
        response = client.get("/weekend/export")
        assert response.status_code == 200

    def test_weekend_export_shows_no_images_when_no_screenings(
        self, client, setup_cinemas
    ):
        response = client.get("/weekend/export")
        html = response.get_data(as_text=True)
        assert html.count("data:image/png;base64,") == 0
        assert "Nenhuma sessão programada" in html

    def test_weekend_export_renders_one_image_for_a_day_with_few_screenings(
        self, client, setup_cinemas
    ):
        friday_date, _, _ = get_weekend_dates(date.today())
        with client.application.app_context():
            _create_screening(movie_title="Filme Sexta", screening_date=friday_date)
        response = client.get("/weekend/export")
        assert response.get_data(as_text=True).count("data:image/png;base64,") == 1

    def test_weekend_export_splits_into_multiple_parts_for_many_screenings(
        self, client, setup_cinemas
    ):
        friday_date, _, _ = get_weekend_dates(date.today())
        with client.application.app_context():
            for i in range(40):
                _create_screening(
                    movie_title=f"Filme Longo Numero {i} Com Título Bem Grande",
                    screening_date=friday_date,
                )
        response = client.get("/weekend/export")
        assert response.get_data(as_text=True).count("data:image/png;base64,") >= 2


class TestScreeningProgramacao:
    def test_programacao_returns_200(self, client, setup_cinemas):
        with client.application.app_context():
            _create_screening(movie_title="Filme do Mês")
        response = client.get("/program")
        assert response.status_code == 200
        assert b"Filme do M\xc3\xaas" in response.data

    def test_programacao_filters_by_cinema_query_param(self, client, setup_cinemas):
        response = client.get("/program?cinema=capitolio")
        assert response.status_code == 200

    def test_programacao_marks_today_with_scroll_anchor(self, client, setup_cinemas):
        with client.application.app_context():
            _create_screening(movie_title="Filme de Hoje")
        response = client.get("/program")
        today_id = f'id="day-{date.today().isoformat()}"'.encode()
        assert today_id in response.data
        assert b"scrollIntoView" in response.data


class TestScreeningUpload:
    def test_upload_nonexistent_file_returns_404(self, client):
        response = client.get("/screening/assets/does-not-exist.png")
        assert response.status_code == 404


class TestScreeningCreate:
    def test_create_get_requires_login(self, client):
        response = client.get("/screening/new")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_create_get_with_auth_returns_200(self, auth_headers, setup_cinemas):
        response = auth_headers.get("/screening/new")
        assert response.status_code == 200

    def test_create_post_missing_title_shows_error(self, auth_headers, setup_cinemas):
        cinema = _get_cinema("capitolio")
        form = _valid_create_form(movie_title="", cinema_id=str(cinema.id))
        response = auth_headers.post("/screening/new", data=form)
        assert response.status_code == 200
        assert "obrigatório" in response.get_data(as_text=True)

    def test_create_post_missing_description_shows_error(
        self, auth_headers, setup_cinemas
    ):
        cinema = _get_cinema("capitolio")
        form = _valid_create_form(description="", cinema_id=str(cinema.id))
        response = auth_headers.post("/screening/new", data=form)
        assert response.status_code == 200
        assert "descrição é obrigatório" in response.get_data(as_text=True)

    def test_create_post_missing_cinema_shows_error(self, auth_headers, setup_cinemas):
        # a missing cinema_id also fails the get_cinema_by_id(None) lookup,
        # so the final flashed message is the "no cinema found" one.
        form = _valid_create_form()
        response = auth_headers.post("/screening/new", data=form)
        assert response.status_code == 200
        assert "sala de cinema disponível" in response.get_data(as_text=True)

    def test_create_post_unknown_cinema_shows_error(self, auth_headers, setup_cinemas):
        form = _valid_create_form(cinema_id="999999")
        response = auth_headers.post("/screening/new", data=form)
        assert response.status_code == 200
        assert "sala de cinema disponível" in response.get_data(as_text=True)

    def test_create_post_missing_dates_shows_error(self, auth_headers, setup_cinemas):
        cinema = _get_cinema("capitolio")
        form = _valid_create_form(cinema_id=str(cinema.id))
        del form["screening_dates"]
        response = auth_headers.post("/screening/new", data=form)
        assert response.status_code == 200
        assert "ao menos uma data" in response.get_data(as_text=True)

    def test_create_post_missing_status_shows_error(self, auth_headers, setup_cinemas):
        cinema = _get_cinema("capitolio")
        form = _valid_create_form(cinema_id=str(cinema.id), status="")
        response = auth_headers.post("/screening/new", data=form)
        assert response.status_code == 200
        assert "Selecione o status" in response.get_data(as_text=True)

    def test_create_post_invalid_date_shows_error(self, auth_headers, setup_cinemas):
        cinema = _get_cinema("capitolio")
        form = _valid_create_form(
            cinema_id=str(cinema.id), screening_dates=["not-a-valid-date"]
        )
        response = auth_headers.post("/screening/new", data=form)
        assert response.status_code == 200
        assert "Data de exibição inválida" in response.get_data(as_text=True)

    def test_create_post_success_creates_screening(self, auth_headers, setup_cinemas):
        cinema = _get_cinema("capitolio")
        form = _valid_create_form(cinema_id=str(cinema.id))
        response = auth_headers.post("/screening/new", data=form, follow_redirects=True)
        assert response.status_code == 200
        with auth_headers.application.app_context():
            movie = db_session.query(Movie).filter_by(title="Novo Filme").first()
            assert movie is not None
            screening = db_session.query(Screening).filter_by(movie_id=movie.id).first()
            assert screening is not None
            assert screening.draft is False

    def test_create_post_with_valid_image_uploads_and_creates(
        self, auth_headers, setup_cinemas
    ):
        cinema = _get_cinema("capitolio")
        form = _valid_create_form(cinema_id=str(cinema.id))
        form["movie_poster"] = (io.BytesIO(b"fake-image-bytes"), "poster.jpg")

        with (
            patch(
                "flask_backend.routes.screening.validate_image",
                return_value=(True, None),
            ),
            patch(
                "flask_backend.routes.screening.save_image",
                return_value=("poster.jpg", 100, 200),
            ),
        ):
            response = auth_headers.post(
                "/screening/new",
                data=form,
                content_type="multipart/form-data",
                follow_redirects=True,
            )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            movie = db_session.query(Movie).filter_by(title="Novo Filme").first()
            screening = db_session.query(Screening).filter_by(movie_id=movie.id).first()
            assert screening.image == "poster.jpg"
            assert screening.image_width == 100
            assert screening.image_height == 200

    def test_create_post_with_invalid_image_shows_error(
        self, auth_headers, setup_cinemas
    ):
        cinema = _get_cinema("capitolio")
        form = _valid_create_form(cinema_id=str(cinema.id))
        form["movie_poster"] = (io.BytesIO(b"not-an-image"), "poster.txt")

        with patch(
            "flask_backend.routes.screening.validate_image",
            return_value=(False, "Extensão do arquivo inválida."),
        ):
            response = auth_headers.post(
                "/screening/new", data=form, content_type="multipart/form-data"
            )
        assert response.status_code == 200
        assert "Extensão do arquivo inválida" in response.get_data(as_text=True)
        with auth_headers.application.app_context():
            movie = db_session.query(Movie).filter_by(title="Novo Filme").first()
            assert movie is None


class TestScreeningPublish:
    def test_publish_requires_login(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening(draft=True)
        response = client.post(f"/screening/{screening_id}/publish")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_publish_nonexistent_returns_404(self, auth_headers):
        response = auth_headers.post("/screening/999999/publish")
        assert response.status_code == 404

    def test_publish_with_auth_publishes_screening(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening(draft=True)
        response = auth_headers.post(
            f"/screening/{screening_id}/publish", follow_redirects=True
        )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.draft is False


class TestScreeningUpdate:
    def test_update_get_requires_login(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening()
        response = client.get(f"/screening/{screening_id}/update")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_update_nonexistent_returns_404(self, auth_headers):
        response = auth_headers.get("/screening/999999/update")
        assert response.status_code == 404

    def test_update_get_with_auth_returns_200(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        response = auth_headers.get(f"/screening/{screening_id}/update")
        assert response.status_code == 200

    def test_update_post_missing_title_shows_error(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        form = _valid_create_form(movie_title="")
        response = auth_headers.post(f"/screening/{screening_id}/update", data=form)
        assert response.status_code == 200
        assert "obrigatório" in response.get_data(as_text=True)

    def test_update_post_missing_description_shows_error(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        form = _valid_create_form(description="")
        response = auth_headers.post(f"/screening/{screening_id}/update", data=form)
        assert response.status_code == 200
        assert "descrição é obrigatório" in response.get_data(as_text=True)

    def test_update_post_missing_dates_shows_error(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        form = _valid_create_form()
        del form["screening_dates"]
        response = auth_headers.post(f"/screening/{screening_id}/update", data=form)
        assert response.status_code == 200
        assert "ao menos uma data" in response.get_data(as_text=True)

    def test_update_post_missing_status_shows_error(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        form = _valid_create_form(status="")
        response = auth_headers.post(f"/screening/{screening_id}/update", data=form)
        assert response.status_code == 200
        assert "Selecione o status" in response.get_data(as_text=True)

    def test_update_post_invalid_date_shows_error(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        form = _valid_create_form(screening_dates=["not-a-valid-date"])
        response = auth_headers.post(f"/screening/{screening_id}/update", data=form)
        assert response.status_code == 200
        assert "Data de exibição inválida" in response.get_data(as_text=True)

    def test_update_post_success_updates_screening(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening(movie_title="Titulo Antigo")
        form = _valid_create_form(movie_title="Titulo Novo")
        response = auth_headers.post(
            f"/screening/{screening_id}/update", data=form, follow_redirects=True
        )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.movie.title == "Titulo Novo"

    def test_update_post_with_valid_image_replaces_image(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        form = _valid_create_form()
        form["movie_poster"] = (io.BytesIO(b"fake-image-bytes"), "new-poster.jpg")

        with (
            patch(
                "flask_backend.routes.screening.validate_image",
                return_value=(True, None),
            ),
            patch(
                "flask_backend.routes.screening.save_image",
                return_value=("new-poster.jpg", 150, 250),
            ),
        ):
            response = auth_headers.post(
                f"/screening/{screening_id}/update",
                data=form,
                content_type="multipart/form-data",
                follow_redirects=True,
            )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.image == "new-poster.jpg"
            assert screening.image_width == 150

    def test_update_post_with_invalid_image_shows_error(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        form = _valid_create_form()
        form["movie_poster"] = (io.BytesIO(b"not-an-image"), "poster.txt")

        with patch(
            "flask_backend.routes.screening.validate_image",
            return_value=(False, "Arquivo corrompido ou inválido."),
        ):
            response = auth_headers.post(
                f"/screening/{screening_id}/update",
                data=form,
                content_type="multipart/form-data",
            )
        assert response.status_code == 200
        assert "Arquivo corrompido ou inválido" in response.get_data(as_text=True)


class TestScreeningDelete:
    def test_delete_requires_login(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening()
        response = client.post(f"/screening/{screening_id}/delete")
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_delete_nonexistent_returns_404(self, auth_headers):
        response = auth_headers.post("/screening/999999/delete")
        assert response.status_code == 404

    def test_delete_with_auth_deletes_screening(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        response = auth_headers.post(
            f"/screening/{screening_id}/delete", follow_redirects=True
        )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            assert db_session.get(Screening, screening_id) is None

    def test_delete_removes_alert_actions_scoped_to_the_screening(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
            db_session.add(
                AlertAction(
                    screening_id=screening_id,
                    action="posted",
                    created_at=datetime.now(),
                )
            )
            db_session.commit()

        auth_headers.post(f"/screening/{screening_id}/delete", follow_redirects=True)

        with auth_headers.application.app_context():
            assert (
                db_session.query(AlertAction)
                .filter_by(screening_id=screening_id)
                .count()
                == 0
            )


class TestScreeningDescribeImage:
    def test_describe_image_requires_login(self, client):
        response = client.post("/screening/image/describe", data={})
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_describe_image_missing_image_returns_400(self, auth_headers):
        response = auth_headers.post("/screening/image/describe", data={})
        assert response.status_code == 400
        assert response.get_json()["details"] == "Imagem não encontrada."

    def test_describe_image_missing_api_key_returns_500(self, auth_headers):
        with patch("flask_backend.routes.screening.Gemini", side_effect=ValueError):
            response = auth_headers.post(
                "/screening/image/describe",
                data={"image": (io.BytesIO(b"fake"), "photo.jpg")},
                content_type="multipart/form-data",
            )
        assert response.status_code == 500
        assert "Chave de API Gemini" in response.get_data(as_text=True)

    def test_describe_image_empty_response(self, auth_headers):
        mock_gemini = MagicMock()
        mock_gemini.prompt_image.return_value = None
        with patch("flask_backend.routes.screening.Gemini", return_value=mock_gemini):
            response = auth_headers.post(
                "/screening/image/describe",
                data={"image": (io.BytesIO(b"fake"), "photo.jpg")},
                content_type="multipart/form-data",
            )
        assert response.status_code == 200
        assert (
            response.get_json()["details"]
            == "Não foi possível gerar uma descrição para a imagem."
        )

    def test_describe_image_rate_limit_returns_502(self, auth_headers):
        mock_gemini = MagicMock()
        mock_gemini.prompt_image.side_effect = ClientError(code=429, response_json={})
        with patch("flask_backend.routes.screening.Gemini", return_value=mock_gemini):
            response = auth_headers.post(
                "/screening/image/describe",
                data={"image": (io.BytesIO(b"fake"), "photo.jpg")},
                content_type="multipart/form-data",
            )
        assert response.status_code == 502
        assert (
            response.get_json()["details"]
            == "Erro ao gerar descrição da imagem. Tente novamente."
        )

    def test_describe_image_server_error_returns_502(self, auth_headers):
        mock_gemini = MagicMock()
        mock_gemini.prompt_image.side_effect = ServerError(code=503, response_json={})
        with patch("flask_backend.routes.screening.Gemini", return_value=mock_gemini):
            response = auth_headers.post(
                "/screening/image/describe",
                data={"image": (io.BytesIO(b"fake"), "photo.jpg")},
                content_type="multipart/form-data",
            )
        assert response.status_code == 502
        assert (
            response.get_json()["details"]
            == "Erro ao gerar descrição da imagem. Tente novamente."
        )

    def test_describe_image_success(self, auth_headers):
        mock_gemini = MagicMock()
        mock_gemini.prompt_image.return_value = "  Uma bela descrição.  "
        with patch("flask_backend.routes.screening.Gemini", return_value=mock_gemini):
            response = auth_headers.post(
                "/screening/image/describe",
                data={"image": (io.BytesIO(b"fake"), "photo.jpg")},
                content_type="multipart/form-data",
            )
        assert response.status_code == 200
        assert response.get_json() == {"text": "Uma bela descrição."}


MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
)


class TestScreeningIndexMobile:
    def test_returns_200_for_mobile_user_agent(self, client, setup_cinemas):
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        assert response.status_code == 200

    def test_renders_reels_feed_for_mobile_user_agent(self, client, setup_cinemas):
        with client.application.app_context():
            _create_screening(
                movie_title="Filme Mobile",
                screening_date=date.today() + timedelta(days=1),
            )
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert "Filme Mobile" in html
        assert 'class="reels-feed"' in html

    def test_desktop_user_agent_still_gets_the_existing_layout(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            _create_screening(movie_title="Filme Desktop")
        response = client.get("/")
        html = response.get_data(as_text=True)
        assert "Filme Desktop" in html
        assert 'class="reels-feed"' not in html

    def test_hides_draft_screening_on_mobile_when_not_logged_in(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            _create_screening(
                movie_title="Filme Rascunho Mobile",
                draft=True,
                screening_date=date.today() + timedelta(days=1),
            )
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        assert b"Filme Rascunho Mobile" not in response.data

    def test_shows_draft_screening_on_mobile_when_logged_in(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            _create_screening(
                movie_title="Filme Rascunho Mobile Logado",
                draft=True,
                screening_date=date.today() + timedelta(days=1),
            )
        response = auth_headers.get("/", headers={"User-Agent": MOBILE_UA})
        assert b"Filme Rascunho Mobile Logado" in response.data

    def test_draft_admin_actions_appear_in_the_info_panel_when_logged_in(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            _create_screening(
                movie_title="Filme Rascunho Ações",
                draft=True,
                screening_date=date.today() + timedelta(days=1),
            )
        response = auth_headers.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'data-function="publish"' in html
        assert 'data-function="delete"' in html

    def test_next_dates_hide_a_drafts_dates_from_anonymous_visitors(
        self, client, setup_cinemas
    ):
        # same movie showing at two cinemas: published at Capitólio, still a
        # draft at Sala Redenção. the published card's "next dates" must not
        # expose the draft's cinema or date to a logged out visitor.
        today = date.today()
        published_date = today + timedelta(days=1)
        draft_date = today + timedelta(days=3)
        with client.application.app_context():
            published_id = _create_screening(
                movie_title="Filme Compartilhado",
                cinema_slug="capitolio",
                screening_date=published_date,
            )
            movie_id = db_session.get(Screening, published_id).movie_id
            _create_screening(
                movie_title="Filme Compartilhado",
                cinema_slug="sala-redencao",
                draft=True,
                screening_date=draft_date,
                movie_id=movie_id,
            )

        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)

        assert "Filme Compartilhado" in html
        assert f"{published_date.strftime('%d/%m')} · Capitólio" in html
        assert "Sala Redenção" not in html
        assert draft_date.strftime("%d/%m") not in html

    def test_shows_placeholder_for_screening_without_poster(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            _create_screening(
                movie_title="Filme Sem Poster",
                image=None,
                screening_date=date.today() + timedelta(days=1),
            )
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'class="reels-poster-placeholder"' in html

    def test_poster_panel_has_a_swipe_hint(self, client, setup_cinemas):
        with client.application.app_context():
            _create_screening(
                movie_title="Filme Com Dica",
                screening_date=date.today() + timedelta(days=1),
            )
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'class="reels-swipe-hint"' in html

    def test_loads_analytics_for_anonymous_visitors(self, client, setup_cinemas):
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'data-goatcounter="https://cinemaempoa.goatcounter.com/count"' in html

    def test_renders_the_analytics_opt_out_marker_outside_production(
        self, client, setup_cinemas
    ):
        # base.html carries the skip marker on its dev banner / logged in
        # marker; the reels shell renders it hidden, same effect.
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert '<div style="display: none;" data-goatcounter-skip></div>' in html

    def test_menu_button_is_present(self, client, setup_cinemas):
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'id="reels-menu-toggle"' in html
        with client.application.test_request_context():
            about_url = url_for("page.about")
        assert about_url in html

    def test_shows_empty_state_when_no_screenings_in_range(self, client, setup_cinemas):
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert "Não há sessões" in html

    def test_first_poster_loads_eagerly_and_later_posters_are_deferred(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            for i in range(3):
                _create_screening(
                    movie_title=f"Filme {i}",
                    image=f"poster{i}.jpg",
                    image_width=100,
                    image_height=200,
                    screening_date=date.today() + timedelta(days=i + 1),
                )
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'src="poster0.jpg"' in html
        # index 1 is the other side of the `loop.index0 < 2` boundary: still eager
        assert 'src="poster1.jpg"' in html
        assert 'data-src="poster1.jpg"' not in html
        assert 'data-src="poster2.jpg"' in html

    def test_hides_screenings_that_have_already_started(self, client, setup_cinemas):
        with client.application.app_context():
            _create_screening(
                movie_title="Filme Já Começou",
                screening_date=date.today(),
                screening_time="00:00",
            )
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert "Filme Já Começou" not in html


def _create_movie(title="Filme"):
    movie = Movie(title=title, slug=title.lower().replace(" ", "-"))
    db_session.add(movie)
    db_session.commit()
    return movie.id


class TestWantToWatchToggle:
    def test_first_toggle_marks_the_movie_and_sets_visitor_cookie(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            movie_id = _create_movie()

        response = client.post(f"/movie/{movie_id}/want-to-watch")

        assert response.status_code == 200
        assert response.get_json() == {"wanted": True}
        set_cookie_headers = response.headers.get_all("Set-Cookie")
        visitor_cookie = next(
            header for header in set_cookie_headers if header.startswith("visitor_id=")
        )
        assert "HttpOnly" in visitor_cookie

    def test_second_toggle_unmarks_using_the_same_visitor(self, client, setup_cinemas):
        with client.application.app_context():
            movie_id = _create_movie()

        first = client.post(f"/movie/{movie_id}/want-to-watch")
        second = client.post(f"/movie/{movie_id}/want-to-watch")

        assert first.get_json() == {"wanted": True}
        assert second.get_json() == {"wanted": False}

    def test_returns_404_for_unknown_movie(self, client, setup_cinemas):
        response = client.post("/movie/99999/want-to-watch")

        assert response.status_code == 404


class TestReelsWantToWatchState:
    def test_homepage_marks_card_as_wanted_for_matching_visitor(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Querido",
                screening_date=date.today() + timedelta(days=1),
            )
            movie_id = db_session.query(Screening).get(screening_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(movie_id, "visitor-a")

        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)

        assert f'data-movie-id="{movie_id}"' in html
        assert 'data-wanted="true"' in html

    def test_homepage_card_not_wanted_without_a_visitor_cookie(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            _create_screening(
                movie_title="Filme Qualquer",
                screening_date=date.today() + timedelta(days=1),
            )

        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)

        assert 'data-wanted="true"' not in html
