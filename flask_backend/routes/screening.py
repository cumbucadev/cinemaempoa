import json
import math
from datetime import date, datetime
from typing import List

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

from flask_backend.import_json import ScrappedCinema, ScrappedFeature, ScrappedResult
from flask_backend.models import Screening
from flask_backend.repository.cinemas import get_all as get_all_cinemas
from flask_backend.repository.cinemas import get_by_id as get_cinema_by_id
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.movies import (
    get_by_title_or_create as get_movie_by_title_or_create,
)
from flask_backend.repository.screenings import create as create_screening
from flask_backend.repository.screenings import (
    get_days_screenings_by_cinema_id,
    get_screening_by_id,
)
from flask_backend.repository.screenings import update as update_screening
from flask_backend.repository.screenings import update_screening_dates
from flask_backend.routes.auth import login_required
from flask_backend.service.screening import (
    build_dates,
    download_image_from_url,
    get_image_metadata,
    get_img_filename_from_url,
    get_img_path_from_filename,
    save_image,
    validate_image,
)

bp = Blueprint("screening", __name__)


@bp.route("/")
def index():
    cinemas = get_all_cinemas()
    today = date.today()
    # limits how wide a movie image can be on the listing
    imgDisplayWidth = 325

    quicklinks = []
    cinemas_with_screenings = []

    user_logged_in = g.user is not None

    for cinema in cinemas:
        quicklinks.append((cinema.slug, cinema.name))

        cinema_obj = {
            "name": cinema.name,
            "slug": cinema.slug,
            "url": cinema.url,
            "screening_dates": [],
        }
        screenings: List[Screening] = get_days_screenings_by_cinema_id(cinema.id, today)
        for screening in screenings:
            if screening.draft and not user_logged_in:
                continue
            # used to set <li> styling
            minHeight = None
            if screening.image:
                minHeight = math.ceil(
                    imgDisplayWidth / screening.image_width * screening.image_height
                )
            screening_times = [
                screening_date.time
                for screening_date in screening.dates
                if screening_date.date == today
            ]
            cinema_obj["screening_dates"].append(
                {
                    "times": screening_times,
                    "image": screening.image,
                    "min_height": minHeight,
                    "image_display_width": imgDisplayWidth,
                    "title": screening.movie.title,
                    "description": screening.description,
                    "screening_url": screening.url,
                    "screening_id": screening.id,
                    "draft": screening.draft,
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
    screening_dates = []
    if request.method == "POST":
        movie_title = request.form.get("movie_title")
        description = request.form.get("description")
        cinema_id = request.form.get("cinema_id")
        screening_dates = request.form.getlist("screening_dates")
        status = request.form.get("status")
        error = None

        if not movie_title:
            error = "O título do filme é obrigatório."
        if not description:
            error = "O campo descrição é obrigatório."
        if not cinema_id:
            error = "Selecione o cinema que irá passar essa sessão."
        if not screening_dates:
            error = "Selecione ao menos uma data de exibição."
        if not status:
            error = "Selecione o status do cadastro."

        try:
            parsed_screening_dates = build_dates(screening_dates)
        except ValueError:
            error = "Data de exibição inválida."

        cinema = get_cinema_by_id(cinema_id)
        if cinema is None:
            error = "Selecione uma sala de cinema disponível na listagem."

        movie_poster = request.files.get("movie_poster", None)
        image = None
        image_width = None
        image_height = None

        if movie_poster and movie_poster.filename:
            img_is_valid, message = validate_image(movie_poster)
            if img_is_valid:
                image, image_width, image_height = save_image(movie_poster, current_app)
            else:
                error = message

        if error is not None:
            flash(error, "danger")
        else:
            movie = get_movie_by_title_or_create(movie_title)
            create_screening(
                movie.id,
                description,
                cinema.id,
                parsed_screening_dates,
                image,
                image_width,
                image_height,
                status == "draft",
            )
            flash(f"Sessão «{movie_title}» criada com sucesso!", "success")
            return redirect(url_for("screening.index"))

    current_date = date.today()
    max_year = datetime.now().year + 1
    cinemas = get_all_cinemas()

    valid_dates = []
    for received_date in screening_dates:
        try:
            parsed_date = datetime.strptime(received_date, "%Y-%m-%dT%H:%M")
            valid_dates.append(f"{parsed_date.date()}T{str(parsed_date.time())[0:5]}")
        except ValueError:
            pass

    return render_template(
        "screening/create.html",
        cinemas=cinemas,
        current_date=current_date,
        received_dates=valid_dates,
        max_year=max_year,
    )


@bp.route("/screening/<int:id>/publish", methods=("POST",))
@login_required
def publish(id):
    screening = get_screening_by_id(id)
    if not request.method == "POST":
        abort(405)

    if not screening:
        abort(404)

    update_screening(
        screening,
        screening.movie_id,
        screening.description,
        None,
        None,
        None,
        False,
    )
    flash(f"Sessão «{screening.movie.title}» publicada com sucesso!", "success")
    return redirect(url_for("screening.index"))


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
        status = request.form.get("status")
        error = None

        if not movie_title:
            error = "O título do filme é obrigatório."
        if not description:
            error = "O campo descrição é obrigatório."
        if not screening_dates:
            error = "Selecione ao menos uma data de exibição."
        if not status:
            error = "Selecione o status do cadastro."

        try:
            parsed_screening_dates = build_dates(screening_dates)
        except ValueError:
            error = "Data de exibição inválida."

        movie_poster = request.files.get("movie_poster", None)
        image = screening.image
        image_width = screening.image_width
        image_height = screening.image_height

        if movie_poster and movie_poster.filename:
            img_is_valid, message = validate_image(movie_poster)
            if img_is_valid:
                new_img, image_width, image_height = save_image(
                    movie_poster, current_app
                )
                image = new_img
            else:
                error = message

        if error is not None:
            flash(error, "danger")
        else:
            update_screening_dates(screening, parsed_screening_dates)

            movie = get_movie_by_title_or_create(movie_title)
            update_screening(
                screening,
                movie.id,
                description,
                image,
                image_width,
                image_height,
                status == "draft",
            )
            flash(f"Sessão «{movie_title}» atualizada com sucesso!", "success")
            return redirect(url_for("screening.index"))

    return render_template("screening/update.html", screening=screening)


@bp.route("/screening/import", methods=("GET", "POST"))
@login_required
def import_screenings():
    suggestions = []
    if request.method == "POST":
        json_file = request.files.get("json_file", None)

        if json_file is None:
            flash("Arquivo .json inválido", "danger")
            return render_template("screening/import.html", suggestions=suggestions)

        try:
            parsed_json = json.load(json_file)
        except (json.decoder.JSONDecodeError, UnicodeDecodeError):
            flash("Arquivo .json inválido", "danger")
            return render_template("screening/import.html", suggestions=suggestions)

        try:
            scrapped_results: ScrappedResult = ScrappedResult.from_jsonable(parsed_json)
        except Exception as e:
            flash("Arquivo .json inválido", "danger")
            print(e)
            return render_template("screening/import.html", suggestions=suggestions)

        created_features = 0

        # validate all cinemas are valid
        for json_cinema in scrapped_results.cinemas:
            cinema = get_cinema_by_slug(json_cinema.slug)
            if cinema is None:
                flash(f"Sala {json_cinema.slug} não encontrada.")
                return render_template("screening/import.html", suggestions=suggestions)

        # all validations passed, import screenings :)
        scrapped_cinema: ScrappedCinema
        for scrapped_cinema in scrapped_results.cinemas:
            cinema = get_cinema_by_slug(scrapped_cinema.slug)
            scrapped_feature: ScrappedFeature
            for scrapped_feature in scrapped_cinema.features:
                movie = get_movie_by_title_or_create(scrapped_feature.title)

                description: str = ""
                screenings_dates = None
                if scrapped_feature.time:
                    screenings_dates = build_dates(scrapped_feature.time)
                if scrapped_feature.original_title:
                    description += f"\n{scrapped_feature.original_title.strip()}"
                if scrapped_feature.price:
                    description += f"\n{scrapped_feature.price}"
                if scrapped_feature.director:
                    description += f"\n{scrapped_feature.director}"
                if scrapped_feature.classification:
                    description += f"\n{scrapped_feature.classification}"
                if scrapped_feature.general_info:
                    description += f"\n{scrapped_feature.general_info}"
                if scrapped_feature.excerpt:
                    description += f"\n{scrapped_feature.excerpt}"

                if screenings_dates is None:
                    screenings_dates = build_dates(
                        [datetime.now().strftime("%Y-%m-%dT%H:%M")]
                    )

                image_filename, image_width, image_height = None, None, None
                if scrapped_feature.poster:
                    image_filename = get_img_filename_from_url(scrapped_feature.poster)

                    # if the file from that URL already exists locally, use that
                    img_path = get_img_path_from_filename(image_filename, current_app)
                    if img_path:
                        image_width, image_height = get_image_metadata(
                            scrapped_feature.poster, current_app
                        )
                    # file doesnt exist locally, attempt to download
                    else:
                        img, filename = download_image_from_url(
                            scrapped_feature.poster, current_app
                        )
                        image_filename, image_width, image_height = None, None, None
                        if img is not None:
                            # if we fail to download or validate the image, just ignore it for now
                            image_filename, image_width, image_height = save_image(
                                img, current_app, filename
                            )

                create_screening(
                    movie.id,
                    description,
                    cinema.id,
                    screenings_dates,
                    image_filename,
                    image_width,
                    image_height,
                    True,
                )
                created_features += 1
        flash(f"«{created_features}» sessões criadas com sucesso!", "success")

    return render_template("screening/import.html", suggestions=suggestions)


# @bp.route("/<int:id>/delete", methods=("POST",))
# @login_required
# def delete(id):
#     get_post(id)
#     db = get_db()
#     db.execute("DELETE FROM post WHERE id = ?", (id,))
#     db.commit()
#     return redirect(url_for("blog.index"))
