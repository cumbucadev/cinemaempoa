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
from werkzeug.security import check_password_hash, generate_password_hash

from flask_backend.db import get_db

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        db = get_db()
        error = None

        if not username:
            error = "Username is required."
        elif not password:
            error = "Password is required."

        if error is None:
            try:
                db.execute(
                    "INSERT INTO USER (username, password) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
                db.commit()
            except db.IntegrityError:
                error = f"Usuário {username} já existe no sistema."
            else:
                user = db.execute(
                    "SELECT * FROM user WHERE username = ?", (username,)
                ).fetchone()

                welcome_message = Markup(
                    f"Boas vindas, <strong>{user['username']}</strong>!"
                )

                flash(welcome_message, "success")

                session["user_id"] = user["id"]
                return redirect(url_for("screening.index"))

        flash(error, "danger")
    return render_template("auth/register.html")


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        db = get_db()
        error = None
        user = db.execute(
            "SELECT * FROM user WHERE username = ?", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["password"], password):
            error = "Usuário ou senha incorretos."

        if error is None:
            session.clear()
            welcome_message = Markup(
                f"Boas vindas, <strong>{user['username']}</strong>!"
            )
            flash(welcome_message, "success")
            session["user_id"] = user["id"]
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
        g.user = (
            get_db().execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
        )


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))

        return view(**kwargs)

    return wrapped_view
