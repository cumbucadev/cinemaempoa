import io
from datetime import date
from unittest.mock import MagicMock, patch

from google.genai.errors import ClientError, ServerError

from flask_backend.db import db_session
from flask_backend.models import Alert, Cinema, Movie, Screening, ScreeningDate


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
):
    cinema = _get_cinema(cinema_slug)
    movie = Movie(title=movie_title, slug=movie_title.lower().replace(" ", "-"))
    db_session.add(movie)
    db_session.commit()

    screening = Screening(
        movie_id=movie.id,
        cinema_id=cinema.id,
        description="A description",
        draft=draft,
        image=image,
        image_width=image_width,
        image_height=image_height,
        image_alt=image_alt,
        dates=[ScreeningDate(date=date.today(), time="20:00")],
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

    def test_delete_removes_alerts_scoped_to_the_screening(
        self, auth_headers, setup_cinemas
    ):
        with auth_headers.application.app_context():
            screening_id = _create_screening()
            screening = db_session.get(Screening, screening_id)
            db_session.add(
                Alert(
                    rule_name="new_movie",
                    movie_id=screening.movie_id,
                    screening_id=screening_id,
                    dedup_key=f"new_movie:{screening_id}",
                    drafted_text="text",
                )
            )
            db_session.commit()

        auth_headers.post(f"/screening/{screening_id}/delete", follow_redirects=True)

        with auth_headers.application.app_context():
            assert (
                db_session.query(Alert).filter_by(screening_id=screening_id).count()
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
