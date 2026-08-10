import io
import re
from datetime import date, datetime, timedelta
from typing import Optional
from unittest.mock import MagicMock, patch

from flask import url_for
from google.genai.errors import ClientError, ServerError

from flask_backend.db import db_session
from flask_backend.models import AlertAction, Cinema, Movie, Screening, ScreeningDate


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

    def test_weekend_does_not_link_to_the_admin_export_page(
        self, client, setup_cinemas
    ):
        response = client.get("/weekend")
        assert b"/admin/weekend" not in response.data


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

    def test_update_post_success_updates_description(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        form = _valid_create_form(description="Nova descrição de teste.")
        response = auth_headers.post(
            f"/screening/{screening_id}/update", data=form, follow_redirects=True
        )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.description == "Nova descrição de teste."

    def test_update_post_ignores_movie_title_field(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening(movie_title="Titulo Original")
        form = _valid_create_form(movie_title="Titulo Que Deveria Ser Ignorado")
        auth_headers.post(f"/screening/{screening_id}/update", data=form)
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.movie.title == "Titulo Original"

    def test_update_post_success_redirects_to_update_page(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        form = _valid_create_form()
        response = auth_headers.post(
            f"/screening/{screening_id}/update", data=form, follow_redirects=False
        )
        assert response.status_code == 302
        assert response.location == f"/screening/{screening_id}/update"

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


class TestScreeningChangeMovie:
    def test_requires_login(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening()
        response = client.post(f"/screening/{screening_id}/movie", json={"movie_id": 1})
        assert response.status_code == 302
        assert b"/auth/login" in response.data

    def test_returns_404_for_missing_screening(self, auth_headers):
        response = auth_headers.post("/screening/999999/movie", json={"movie_id": 1})
        assert response.status_code == 404

    def test_returns_400_when_neither_field_given(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        response = auth_headers.post(f"/screening/{screening_id}/movie", json={})
        assert response.status_code == 400

    def test_returns_400_when_both_fields_given(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        response = auth_headers.post(
            f"/screening/{screening_id}/movie",
            json={"movie_id": 1, "new_title": "X"},
        )
        assert response.status_code == 400

    def test_returns_404_when_movie_id_does_not_exist(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
        response = auth_headers.post(
            f"/screening/{screening_id}/movie", json={"movie_id": 999999}
        )
        assert response.status_code == 404

    def test_reattaches_to_existing_movie_by_id(self, auth_headers, setup_cinemas):
        with auth_headers.application.app_context():
            screening_id = _create_screening(movie_title="Filme Antigo")
            target = Movie(title="Filme Novo", slug="filme-novo-alvo")
            db_session.add(target)
            db_session.commit()
            target_id = target.id

        response = auth_headers.post(
            f"/screening/{screening_id}/movie", json={"movie_id": target_id}
        )
        assert response.status_code == 200
        assert response.get_json()["movie"]["id"] == target_id
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.movie_id == target_id

    def test_creates_new_movie_when_new_title_has_no_match(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening(movie_title="Filme Antigo 2")

        response = auth_headers.post(
            f"/screening/{screening_id}/movie",
            json={"new_title": "Filme Totalmente Novo"},
        )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.movie.title == "Filme Totalmente Novo"

    def test_reattaches_to_existing_movie_when_new_title_matches_by_slug(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening(movie_title="Filme Antigo 3")
            existing = Movie(title="Filme Existente", slug="filme-existente")
            db_session.add(existing)
            db_session.commit()
            existing_id = existing.id

        response = auth_headers.post(
            f"/screening/{screening_id}/movie",
            json={"new_title": "Filme Existente"},
        )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.movie_id == existing_id
            assert (
                db_session.query(Movie).filter_by(slug="filme-existente").count() == 1
            )

    def test_creates_a_second_movie_when_forced_despite_matching_title(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening(movie_title="Filme Antigo 4")
            existing = Movie(title="Filme Colidido", slug="filme-colidido")
            db_session.add(existing)
            db_session.commit()
            existing_id = existing.id

        response = auth_headers.post(
            f"/screening/{screening_id}/movie",
            json={"new_title": "Filme Colidido", "force_new_movie": True},
        )
        assert response.status_code == 200
        new_movie_id = response.get_json()["movie"]["id"]
        assert new_movie_id != existing_id

        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.movie_id == new_movie_id
            assert screening.movie.slug == "filme-colidido-2"
            assert (
                db_session.query(Movie).filter_by(title="Filme Colidido").count() == 2
            )

    def test_force_new_movie_without_collision_creates_a_single_movie(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening(movie_title="Filme Antigo 5")

        response = auth_headers.post(
            f"/screening/{screening_id}/movie",
            json={"new_title": "Filme Sem Colisao", "force_new_movie": True},
        )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            assert (
                db_session.query(Movie).filter_by(slug="filme-sem-colisao").count() == 1
            )

    def test_is_a_noop_when_target_equals_current_movie(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening(movie_title="Filme Mesmo")
            screening = db_session.get(Screening, screening_id)
            current_movie_id = screening.movie_id

        response = auth_headers.post(
            f"/screening/{screening_id}/movie",
            json={"movie_id": current_movie_id},
        )
        assert response.status_code == 200
        with auth_headers.application.app_context():
            screening = db_session.get(Screening, screening_id)
            assert screening.movie_id == current_movie_id


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

    def test_describe_image_all_models_exhausted_returns_502(self, auth_headers):
        from flask_backend.service.gemini_models import AllGeminiModelsExhausted

        mock_gemini = MagicMock()
        mock_gemini.prompt_image.side_effect = AllGeminiModelsExhausted()
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

    def test_want_to_watch_toast_markup_is_present(self, client, setup_cinemas):
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'id="reels-wtw-toast"' in html
        assert 'data-bs-autohide="true"' in html
        assert 'data-bs-delay="3000"' in html
        assert "Filme adicionado! Veja em Meus Filmes ☰" in html

    def test_share_script_and_toast_markup_are_present(self, client, setup_cinemas):
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'src="/static/reels-share.js"' in html
        assert 'id="reels-share-toast"' in html
        assert "Link copiado!" in html

    def test_sidebar_lists_home_and_favoritos_first_and_highlights_home(
        self, client, setup_cinemas
    ):
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)

        with client.application.test_request_context():
            home_url = url_for("screening.index")
            favoritos_url = url_for("screening.favoritos")
            about_url = url_for("page.about")
            posters_url = url_for("movie.posters")

        assert html.index(home_url) < html.index(favoritos_url)
        assert html.index(favoritos_url) < html.index(about_url)
        assert posters_url in html

        home_link = re.search(
            rf'<a class="(nav-link[^"]*)"\s+href="{re.escape(home_url)}"', html
        )
        favoritos_link = re.search(
            rf'<a class="(nav-link[^"]*)"\s+href="{re.escape(favoritos_url)}"', html
        )
        assert "active" in home_link.group(1).split()
        assert "active" not in favoritos_link.group(1).split()

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

    def test_share_button_is_present_with_deep_link_data(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Compartilhável",
                cinema_slug="capitolio",
                screening_date=date.today() + timedelta(days=1),
                screening_time="21:00",
            )
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert 'data-function="share"' in html
        assert f"/?screening={screening_id}" in html
        assert 'data-movie-title="Filme Compartilhável"' in html
        assert "Capitólio" in html

    def test_share_url_uses_the_canonical_production_domain(
        self, client, setup_cinemas
    ):
        # url_for(..., _external=True) can't be trusted behind this app's
        # nginx setup (no Host-header rewrite), so the share link is built
        # from a hardcoded canonical domain instead - see screening.py's
        # CANONICAL_BASE_URL.
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Compartilhável Externo",
                screening_date=date.today() + timedelta(days=1),
            )
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert (
            f'data-share-url="https://cinemaempoa.com.br/?screening={screening_id}"'
            in html
        )


class TestScreeningSharedLink:
    def test_mobile_with_screening_in_current_feed_renders_and_highlights_card(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Compartilhável",
                screening_date=date.today() + timedelta(days=1),
            )
        response = client.get(
            f"/?screening={screening_id}", headers={"User-Agent": MOBILE_UA}
        )
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Filme Compartilhável" in html

    def test_desktop_with_valid_screening_redirects_to_movie_page(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Redirecionado",
                screening_date=date.today() + timedelta(days=1),
            )
        response = client.get(f"/?screening={screening_id}")
        assert response.status_code == 302
        assert (
            response.headers["Location"]
            == f"/movies/filme-redirecionado?screening={screening_id}"
        )

    def test_mobile_with_screening_aged_out_of_feed_redirects_to_movie_page(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Expirado",
                screening_date=date.today() - timedelta(days=30),
            )
        response = client.get(
            f"/?screening={screening_id}", headers={"User-Agent": MOBILE_UA}
        )
        assert response.status_code == 302
        assert (
            response.headers["Location"]
            == f"/movies/filme-expirado?screening={screening_id}"
        )

    def test_invalid_screening_id_falls_back_to_normal_mobile_feed(
        self, client, setup_cinemas
    ):
        response = client.get("/?screening=999999", headers={"User-Agent": MOBILE_UA})
        assert response.status_code == 200

    def test_non_integer_screening_param_falls_back_to_normal_mobile_feed(
        self, client, setup_cinemas
    ):
        response = client.get("/?screening=abc", headers={"User-Agent": MOBILE_UA})
        assert response.status_code == 200

    def test_screening_with_movie_missing_slug_falls_back_to_normal_mobile_feed(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            cinema = _get_cinema()
            movie = Movie(title="Filme Sem Slug", slug=None)
            db_session.add(movie)
            db_session.commit()
            screening = Screening(
                movie_id=movie.id,
                cinema_id=cinema.id,
                description="A description",
                dates=[
                    ScreeningDate(date=date.today() + timedelta(days=1), time="20:00")
                ],
            )
            db_session.add(screening)
            db_session.commit()
            screening_id = screening.id
        response = client.get(
            f"/?screening={screening_id}", headers={"User-Agent": MOBILE_UA}
        )
        assert response.status_code == 200

    def test_shared_card_renders_movie_specific_og_tags(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme OG",
                image="poster-og.jpg",
                image_width=100,
                image_height=200,
                screening_date=date.today() + timedelta(days=1),
            )
        response = client.get(
            f"/?screening={screening_id}", headers={"User-Agent": MOBILE_UA}
        )
        html = response.get_data(as_text=True)
        assert '<meta property="og:title" content="Filme OG">' in html
        assert '<meta property="og:image" content="poster-og.jpg">' in html

    def test_plain_feed_keeps_generic_og_tags(self, client, setup_cinemas):
        response = client.get("/", headers={"User-Agent": MOBILE_UA})
        html = response.get_data(as_text=True)
        assert "Programação do dia" in html
        assert 'property="og:title"' not in html

    def test_shared_card_scrolls_to_its_card_on_load(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Scroll",
                screening_date=date.today() + timedelta(days=1),
            )
        response = client.get(
            f"/?screening={screening_id}", headers={"User-Agent": MOBILE_UA}
        )
        html = response.get_data(as_text=True)
        assert f'getElementById("reels-card-{screening_id}")' in html


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

        assert re.search(rf'data-movie-id="{movie_id}"\s+data-wanted="true"', html)

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


class TestFavoritos:
    def test_returns_200(self, client, setup_cinemas):
        response = client.get("/favoritos")

        assert response.status_code == 200

    def test_shows_empty_state_without_a_visitor_cookie(self, client, setup_cinemas):
        response = client.get("/favoritos")

        assert "ainda não marcou" in response.get_data(as_text=True)

    def test_shows_marked_movie_with_upcoming_screening(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Futuro",
                screening_date=date.today() + timedelta(days=2),
            )
            movie_id = db_session.query(Screening).get(screening_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(movie_id, "visitor-a")

        response = client.get("/favoritos")

        assert b"Filme Futuro" in response.data

    def test_shows_marked_movie_with_no_upcoming_screening_as_stale(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Antigo",
                screening_date=date.today() - timedelta(days=30),
            )
            movie_id = db_session.query(Screening).get(screening_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(movie_id, "visitor-a")

        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        assert "Filme Antigo" in html
        assert "Todos os filmes" in html

    def test_toggle_then_favoritos_then_untoggle_round_trip(
        self, client, setup_cinemas
    ):
        # exercises the real user flow end to end through the HTTP layer,
        # instead of seeding state by calling the want_to_watch repository
        # directly - every other /favoritos test does the latter.
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Round Trip",
                screening_date=date.today() + timedelta(days=1),
            )
            movie_id = db_session.query(Screening).get(screening_id).movie_id

        toggle_on = client.post(f"/movie/{movie_id}/want-to-watch")
        assert toggle_on.get_json() == {"wanted": True}
        set_cookie_headers = toggle_on.headers.get_all("Set-Cookie")
        assert any(header.startswith("visitor_id=") for header in set_cookie_headers)

        marked_response = client.get("/favoritos")
        assert "Filme Round Trip" in marked_response.get_data(as_text=True)

        toggle_off = client.post(f"/movie/{movie_id}/want-to-watch")
        assert toggle_off.get_json() == {"wanted": False}

        unmarked_response = client.get("/favoritos")
        unmarked_html = unmarked_response.get_data(as_text=True)
        assert "ainda não marcou" in unmarked_html
        assert "Filme Round Trip" not in unmarked_html

    def test_sidebar_links_back_to_home_and_highlights_meus_filmes(
        self, client, setup_cinemas
    ):
        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        with client.application.test_request_context():
            home_url = url_for("screening.index")
            favoritos_url = url_for("screening.favoritos")

        assert home_url in html

        home_link = re.search(
            rf'<a class="(nav-link[^"]*)"\s+href="{re.escape(home_url)}"', html
        )
        favoritos_link = re.search(
            rf'<a class="(nav-link[^"]*)"\s+href="{re.escape(favoritos_url)}"', html
        )
        assert "active" not in home_link.group(1).split()
        assert "active" in favoritos_link.group(1).split()

    def test_splits_movies_into_em_exibicao_and_todos_sections(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            showing_id = _create_screening(
                movie_title="Filme Em Cartaz",
                screening_date=date.today() + timedelta(days=2),
            )
            showing_movie_id = db_session.query(Screening).get(showing_id).movie_id
            stale_id = _create_screening(
                movie_title="Filme Arquivado",
                screening_date=date.today() - timedelta(days=30),
            )
            stale_movie_id = db_session.query(Screening).get(stale_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(showing_movie_id, "visitor-a")
            toggle(stale_movie_id, "visitor-a")

        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        em_exibicao_index = html.index("Em exibição")
        todos_index = html.index("Todos os filmes")
        showing_index = html.index("Filme Em Cartaz")
        archived_index = html.index("Filme Arquivado")
        assert em_exibicao_index < showing_index < todos_index < archived_index

    def test_todos_section_sorted_alphabetically(self, client, setup_cinemas):
        with client.application.app_context():
            zeta_id = _create_screening(
                movie_title="Filme Zeta",
                screening_date=date.today() - timedelta(days=10),
            )
            zeta_movie_id = db_session.query(Screening).get(zeta_id).movie_id
            alfa_id = _create_screening(
                movie_title="Filme Alfa",
                screening_date=date.today() - timedelta(days=5),
            )
            alfa_movie_id = db_session.query(Screening).get(alfa_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(zeta_movie_id, "visitor-a")
            toggle(alfa_movie_id, "visitor-a")

        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        assert html.index("Filme Alfa") < html.index("Filme Zeta")

    def test_hides_todos_section_when_everything_is_showing(
        self, client, setup_cinemas
    ):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Único",
                screening_date=date.today() + timedelta(days=1),
            )
            movie_id = db_session.query(Screening).get(screening_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(movie_id, "visitor-a")

        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        assert "Todos os filmes" not in html

    def test_shows_no_screenings_message_when_none_showing(self, client, setup_cinemas):
        with client.application.app_context():
            screening_id = _create_screening(
                movie_title="Filme Parado",
                screening_date=date.today() - timedelta(days=15),
            )
            movie_id = db_session.query(Screening).get(screening_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(movie_id, "visitor-a")

        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        assert "Nenhum dos seus filmes está em cartaz agora." in html

    def test_tiles_never_show_a_date_badge(self, client, setup_cinemas):
        # favoritos tiles are poster-only (poster + want-to-watch star): the
        # section split (Em exibição / Todos os filmes) already signals
        # whether a movie has upcoming sessions, so no per-tile date badge.
        with client.application.app_context():
            showing_id = _create_screening(
                movie_title="Filme Com Data",
                screening_date=date.today() + timedelta(days=3),
            )
            showing_movie_id = db_session.query(Screening).get(showing_id).movie_id
            stale_id = _create_screening(
                movie_title="Filme Sem Data",
                screening_date=date.today() - timedelta(days=20),
            )
            stale_movie_id = db_session.query(Screening).get(stale_id).movie_id

        client.set_cookie("visitor_id", "visitor-a")
        with client.application.app_context():
            from flask_backend.repository.want_to_watch import toggle

            toggle(showing_movie_id, "visitor-a")
            toggle(stale_movie_id, "visitor-a")

        response = client.get("/favoritos")
        html = response.get_data(as_text=True)

        assert "poster-tile-badge" not in html
