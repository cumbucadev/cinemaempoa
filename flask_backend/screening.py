import os

from datetime import date, datetime
from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.exceptions import abort


from flask_backend.auth import login_required
from flask_backend.db import get_db
from flask_backend.repository.cinemas import get_all as get_all_cinemas
from flask_backend.repository.screenings import (
    get_screening_by_id,
    get_todays_screenings_by_cinema_id,
)
from flask_backend.service.screening import validate_image, save_image

bp = Blueprint("screening", __name__)


@bp.route("/")
def index():
    cinemas = get_all_cinemas()
    quicklinks = [(c["slug"], c["name"]) for c in cinemas]
    cinemas_with_screenings = [
        {
            "name": c["name"],
            "slug": c["slug"],
            "url": c["url"],
            "screenings": get_todays_screenings_by_cinema_id(c["id"]),
        }
        for c in cinemas
    ]
    return render_template(
        "screening/index.html",
        cinemas_with_screenings=cinemas_with_screenings,
        today=datetime.now().strftime("%d/%m/%Y"),
        quicklinks=quicklinks,
    )


@bp.route("/screening/assets/<filename>")
def upload(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@bp.route("/screening/new", methods=("GET", "POST"))
@login_required
def create():
    if request.method == "POST":
        movie_title = request.form.get("movie_title")
        description = request.form.get("description")
        cinema_id = request.form.get("cinema_id")
        screening_date = request.form.get("screening_date")
        error = None

        if not movie_title:
            error = "O título do filme é obrigatório."
        if not description:
            error = "O campo descrição é obrigatório."
        if not cinema_id:
            error = "Selecione o cinema que irá passar essa sessão."
        if not screening_date:
            error = "Selecione a data de exibição da sessão."

        movie_poster = request.files.get("movie_poster", None)
        image = None

        if movie_poster and movie_poster.filename:
            img_is_valid, message = validate_image(movie_poster)
            if img_is_valid:
                image = save_image(movie_poster, current_app)
            else:
                error = message

        if error is not None:
            flash(error, "danger")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO screening (movie_title, description, cinema_id, screening_date, image) VALUES (?, ?, ?, ?, ?)",
                (movie_title, description, cinema_id, screening_date, image),
            )
            db.commit()
            flash(f"Sessão «{movie_title}» criada com sucesso!", "success")
            return redirect(url_for("screening.index"))

    current_date = date.today()
    cinemas = get_all_cinemas()
    return render_template(
        "screening/create.html", cinemas=cinemas, current_date=current_date
    )


@bp.route("/screening/<int:id>/update", methods=("GET", "POST"))
@login_required
def update(id):
    screening = get_screening_by_id(id)

    if request.method == "POST":
        movie_title = request.form.get("movie_title")
        description = request.form.get("description")
        error = None

        if not movie_title:
            error = "O título do filme é obrigatório."
        if not description:
            error = "O campo descrição é obrigatório."

        movie_poster = request.files.get("movie_poster", None)
        image = screening["image"]

        if movie_poster and movie_poster.filename:
            img_is_valid, message = validate_image(movie_poster)
            if img_is_valid:
                new_img = save_image(movie_poster, current_app)
                image = new_img
            else:
                error = message

        if error is not None:
            flash(error, "danger")
        else:
            db = get_db()
            db.execute(
                "UPDATE screening SET movie_title = ?, description = ?, image = ?"
                " WHERE id = ?",
                (movie_title, description, image, id),
            )
            db.commit()
            flash(f"Sessão «{movie_title}» atualizada com sucesso!", "success")
            return redirect(url_for("screening.index"))

    return render_template("screening/update.html", screening=screening)


# @bp.route("/<int:id>/delete", methods=("POST",))
# @login_required
# def delete(id):
#     get_post(id)
#     db = get_db()
#     db.execute("DELETE FROM post WHERE id = ?", (id,))
#     db.commit()
#     return redirect(url_for("blog.index"))
