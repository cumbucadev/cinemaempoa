import functools

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from markupsafe import Markup
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import abort
from werkzeug.security import check_password_hash, generate_password_hash

from flask_backend.repository import users as users_repository

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        abort(501)
        username = request.form["username"]
        password = request.form["password"]
        error = None

        if not username:
            error = "Username is required."
        elif not password:
            error = "Password is required."

        if error is None:
            try:
                user = users_repository.create(username, generate_password_hash(password))
            except IntegrityError:
                error = "Nome de usuário inválido. Tente um nome diferente."
            else:
                welcome_message = Markup(
                    f"Boas vindas, <strong>{user.username}</strong>!"
                )

                flash(welcome_message, "success")

                session["user_id"] = user.id
                return redirect(url_for("screening.index"))

        flash(error, "danger")
    return render_template("auth/register.html")


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        error = None
        user = users_repository.get_by_username(username)

        if user is None or not check_password_hash(user.password, password):
            error = "Usuário ou senha incorretos."

        if error is None:
            session.clear()
            welcome_message = Markup(f"Boas vindas, <strong>{user.username}</strong>!")
            flash(welcome_message, "success")
            session["user_id"] = user.id
            return redirect(url_for("screening.index"))

        flash(error, "danger")
    return render_template("auth/login.html")


@bp.route("/logout")
def logout():
    session.clear()
    flash("Você foi deslogado.", "info")
    return redirect(url_for("screening.index"))


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        g.user = users_repository.get_by_id(user_id)


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))

        return view(**kwargs)

    return wrapped_view
