from datetime import date, datetime
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from typing import Tuple
from werkzeug.exceptions import abort


from flask_backend.auth import login_required
from flask_backend.db import db_session
from flask_backend.models import ScreeningDate
from flask_backend.repository.cinemas import (
    get_all as get_all_cinemas,
    get_by_id as get_cinema_by_id,
)
from flask_backend.repository.screenings import (
    get_screening_by_id,
    get_todays_screenings_by_cinema_id,
    create as create_screening,
    update_screening_dates,
    update as update_screening,
)
from flask_backend.repository.movies import (
    get_by_title_or_create as get_movie_by_title_or_create,
)
from flask_backend.service.screening import build_dates, validate_image, save_image

bp = Blueprint("screening", __name__)


@bp.route("/")
def index():
    cinemas = get_all_cinemas()

    quicklinks = []
    cinemas_with_screenings = []

    for cinema in cinemas:
        quicklinks.append((cinema.slug, cinema.name))

        cinema_obj = {
            "name": cinema.name,
            "slug": cinema.slug,
            "url": cinema.url,
            "screening_dates": [],
        }
        screening_dates: Tuple[ScreeningDate, str] = get_todays_screenings_by_cinema_id(
            cinema.id
        )
        for screening_date, screening_times in screening_dates:
            parsed_screening_times = screening_times.split(",")
            cinema_obj["screening_dates"].append(
                {
                    "times": parsed_screening_times,
                    "image": screening_date.screening.image,
                    "title": screening_date.screening.movie.title,
                    "description": screening_date.screening.description,
                    "screening_url": screening_date.screening.url,
                    "screening_id": screening_date.screening.id,
                }
            )
        cinemas_with_screenings.append(cinema_obj)

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
        screening_dates = request.form.getlist("screening_dates")
        error = None

        if not movie_title:
            error = "O título do filme é obrigatório."
        if not description:
            error = "O campo descrição é obrigatório."
        if not cinema_id:
            error = "Selecione o cinema que irá passar essa sessão."
        if not screening_dates:
            error = "Selecione ao menos uma data de exibição."

        try:
            parsed_screening_dates = build_dates(screening_dates)
        except ValueError:
            error = "Data de exibição inválida."

        cinema = get_cinema_by_id(cinema_id)
        if cinema is None:
            error = "Selecione uma sala de cinema disponível na listagem."

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
            movie = get_movie_by_title_or_create(movie_title)
            create_screening(
                movie.id, description, cinema.id, parsed_screening_dates, image
            )
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

    if not screening:
        abort(404)

    if request.method == "POST":
        movie_title = request.form.get("movie_title")
        description = request.form.get("description")
        screening_dates = request.form.getlist("screening_dates")
        error = None

        if not movie_title:
            error = "O título do filme é obrigatório."
        if not description:
            error = "O campo descrição é obrigatório."
        if not screening_dates:
            error = "Selecione ao menos uma data de exibição."

        try:
            parsed_screening_dates = build_dates(screening_dates)
        except ValueError:
            error = "Data de exibição inválida."

        movie_poster = request.files.get("movie_poster", None)
        image = screening.image

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
            update_screening_dates(screening, parsed_screening_dates)

            movie = get_movie_by_title_or_create(movie_title)
            update_screening(screening, movie.id, description, image)
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
