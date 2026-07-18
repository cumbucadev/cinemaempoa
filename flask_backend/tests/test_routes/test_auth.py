from werkzeug.security import generate_password_hash

from flask_backend.db import db_session
from flask_backend.models import User


def _create_user_with_password(username="loginuser", password="correct-password"):
    user = User(username=username, password=generate_password_hash(password))
    db_session.add(user)
    db_session.commit()
    return user.id


class TestAuthRegister:
    def test_register_get_returns_200(self, client):
        response = client.get("/auth/register")
        assert response.status_code == 200

    def test_register_post_not_implemented(self, client):
        # registration is intentionally disabled - the route aborts
        # before any of its (dead) validation/creation logic runs.
        response = client.post(
            "/auth/register", data={"username": "new", "password": "new"}
        )
        assert response.status_code == 501


class TestAuthLogin:
    def test_login_get_returns_200(self, client):
        response = client.get("/auth/login")
        assert response.status_code == 200

    def test_login_post_unknown_username_shows_error(self, client):
        response = client.post(
            "/auth/login", data={"username": "nobody", "password": "whatever"}
        )
        assert response.status_code == 200
        assert "Usuário ou senha incorretos" in response.get_data(as_text=True)

    def test_login_post_wrong_password_shows_error(self, client, app):
        with app.app_context():
            _create_user_with_password(username="realuser", password="right-pass")

        response = client.post(
            "/auth/login", data={"username": "realuser", "password": "wrong-pass"}
        )
        assert response.status_code == 200
        assert "Usuário ou senha incorretos" in response.get_data(as_text=True)

    def test_login_post_success_redirects_and_sets_session(self, client, app):
        with app.app_context():
            _create_user_with_password(username="realuser", password="right-pass")

        response = client.post(
            "/auth/login",
            data={"username": "realuser", "password": "right-pass"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        with client.session_transaction() as sess:
            assert sess["user_id"] is not None


class TestAuthLogout:
    def test_logout_redirects_and_clears_session(self, client, app):
        with app.app_context():
            user_id = _create_user_with_password()
        with client.session_transaction() as sess:
            sess["user_id"] = user_id

        response = client.get("/auth/logout", follow_redirects=True)
        assert response.status_code == 200

        with client.session_transaction() as sess:
            assert "user_id" not in sess


class TestLoadLoggedInUser:
    def test_authenticated_request_loads_user(self, client, app):
        with app.app_context():
            user_id = _create_user_with_password()
        with client.session_transaction() as sess:
            sess["user_id"] = user_id

        response = client.get("/screening/new")
        # login_required's pass-through branch: no redirect to /auth/login
        assert response.status_code == 200


class TestLoginRequired:
    def test_protected_route_redirects_when_not_logged_in(self, client):
        response = client.get("/screening/new")
        assert response.status_code == 302
        assert b"/auth/login" in response.data
