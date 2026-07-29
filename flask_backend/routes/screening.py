import math
from datetime import date, datetime, timedelta
from typing import List, Optional

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from google.genai.errors import APIError
from werkzeug.exceptions import abort

from flask_backend.env_config import SESSION_LIFETIME_DAYS
from flask_backend.models import Screening
from flask_backend.repository.cinemas import (
    get_all as get_all_cinemas,
    get_by_id as get_cinema_by_id,
)
from flask_backend.repository.movies import (
    get_by_id as get_movie_by_id,
    get_by_title_or_create as get_movie_by_title_or_create,
)
from flask_backend.repository.screenings import (
    create as create_screening,
    delete as delete_screening,
    get_days_screenings_by_cinema_id,
    get_month_screening_dates,
    get_screening_by_id,
    get_screening_dates_for_movies,
    get_screenings_in_date_range,
    get_weekend_screening_dates,
    update as update_screening,
    update_screening_dates,
)
from flask_backend.repository.want_to_watch import (
    get_movie_ids_for_visitor,
    toggle as toggle_want_to_watch,
)
from flask_backend.routes.auth import login_required
from flask_backend.service.gemini_api import Gemini
from flask_backend.service.screening import (
    build_dates,
    build_favorites_feed,
    build_reels_feed,
    save_image,
    validate_image,
)
from flask_backend.service.weekend_export import build_weekend_export_images
from flask_backend.utils.mobile import is_mobile_user_agent
from flask_backend.utils.visitor import (
    VISITOR_COOKIE_NAME,
    get_visitor_id,
    new_visitor_id,
)

bp = Blueprint("screening", __name__)

# request-derived _external=True is unreliable behind this app's
# nginx/traefik setup (no ProxyFix, no Host-header rewrite) — see
# scripts/sitemap.py for the same workaround in a different context.
CANONICAL_BASE_URL = "https://cinemaempoa.com.br"


def _redirect_to_movie(screening: Screening):
    return redirect(
        url_for("movie.show", slug=screening.movie.slug, screening=screening.id)
    )


def _mobile_index(shared_screening: Optional[Screening] = None):
    now = datetime.now()
    today = now.date()
    window_end = today + timedelta(days=6)
    user_logged_in = g.user is not None

    screenings = get_screenings_in_date_range(today, window_end)
    movie_ids = list({screening.movie_id for screening in screenings})
    movie_dates = get_screening_dates_for_movies(
        movie_ids, today, window_end, include_drafts=user_logged_in
    )
    visitor_id = get_visitor_id(request)
    wanted_movie_ids = get_movie_ids_for_visitor(visitor_id) if visitor_id else set()
    cards = build_reels_feed(
        screenings,
        movie_dates,
        today,
        window_end,
        user_logged_in,
        earliest_datetime=now,
        wanted_movie_ids=wanted_movie_ids,
    )

    shared_card = None
    if shared_screening is not None:
        shared_card = next(
            (card for card in cards if card["screening_id"] == shared_screening.id),
            None,
        )
        if shared_card is None:
            return _redirect_to_movie(shared_screening)

    return render_template(
        "screening/index_mobile.html",
        cards=cards,
        shared_card=shared_card,
        canonical_base_url=CANONICAL_BASE_URL,
    )


@bp.route("/")
def index():
    screening_id = request.args.get("screening", type=int)
    shared_screening = get_screening_by_id(screening_id) if screening_id else None
    if shared_screening is not None and not shared_screening.movie.slug:
        shared_screening = None

    is_mobile = is_mobile_user_agent(request.headers.get("User-Agent", ""))

    if shared_screening is not None and not is_mobile:
        return _redirect_to_movie(shared_screening)

    if is_mobile:
        return _mobile_index(shared_screening)

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
            "short_name": cinema.short_name,
            "color": cinema.color,
            "url": cinema.url,
            "screening_dates": [],
        }
        screenings: List[Screening] = get_days_screenings_by_cinema_id(cinema.id, today)
        for screening in screenings:
            if screening.draft is True and not user_logged_in:
                continue
            # used to set <li> styling
            minHeight = None
            if screening.image is not None:
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
                    "image_alt": screening.image_alt,
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

    alert_html = "<p class='mb-0'>O cinemaempoa <strong>mostra os filmes em exibição</strong> no "
    qtt_links = len(quicklinks)
    for idx, link in enumerate(quicklinks):
        alert_html += f"<a href='#{link[0]}' class='alert-link'>{link[1]}</a>"
        if qtt_links > 0 and idx < len(quicklinks) - 1:
            if idx < len(quicklinks) - 2:
                alert_html += ", "
            else:
                alert_html += " e "
    alert_html += " em Porto Alegre. <a href='/about'>Saiba mais.</a></p>"

    return render_template(
        "screening/index.html",
        cinemas_with_screenings=cinemas_with_screenings,
        today=datetime.now().strftime("%d/%m/%Y"),
        alert_html=alert_html,
    )


@bp.route("/weekend")
def weekend():
    screening_dates, friday_date, saturday_date, sunday_date = (
        get_weekend_screening_dates()
    )
    return render_template(
        "screening/weekend.html",
        screening_dates=screening_dates,
        friday_date=friday_date,
        saturday_date=saturday_date,
        sunday_date=sunday_date,
    )


@bp.route("/weekend/export")
def weekend_export():
    screening_dates, friday_date, saturday_date, sunday_date = (
        get_weekend_screening_dates()
    )
    day_exports = build_weekend_export_images(
        screening_dates, friday_date, saturday_date, sunday_date
    )
    return render_template(
        "screening/weekend_export.html",
        day_exports=day_exports,
    )


@bp.route("/program")
def programacao():
    all_cinemas = get_all_cinemas()

    # check if there is a query parameter "cinema" and if so, filter the cinemas by the query parameter
    queried_cinemas = request.args.getlist("cinema")
    checked_cinemas = (
        [cinema.slug for cinema in all_cinemas if cinema.slug in queried_cinemas]
        if queried_cinemas
        else [cinema.slug for cinema in all_cinemas]
    )

    screening_dates = get_month_screening_dates(checked_cinemas)
    # group by date
    screening_dates_grouped = {}
    for screening_date in screening_dates:
        if screening_date.date not in screening_dates_grouped:
            screening_dates_grouped[screening_date.date] = []
        screening_dates_grouped[screening_date.date].append(screening_date)

    return render_template(
        "screening/programacao.html",
        screening_dates=screening_dates_grouped,
        cinemas=all_cinemas,
        checked_cinemas=checked_cinemas,
        today=date.today(),
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
        image_alt = request.form.get("image_alt")
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
            movie, _ = get_movie_by_title_or_create(movie_title)
            create_screening(
                movie.id,
                description,
                cinema.id,
                parsed_screening_dates,
                image,
                image_width,
                image_height,
                status == "draft",
                image_alt,
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
        max_file_size=current_app.config["MAX_CONTENT_LENGTH"],
    )


@bp.route("/screening/<int:id>/publish", methods=("POST",))
@login_required
def publish(id):
    screening = get_screening_by_id(id)
    if request.method != "POST":
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
    image = None
    if not screening:
        abort(404)

    if request.method == "POST":
        movie_title = request.form.get("movie_title")
        description = request.form.get("description")
        screening_dates = request.form.getlist("screening_dates")
        status = request.form.get("status")
        image_alt = request.form.get("image_alt")
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

            movie, _ = get_movie_by_title_or_create(movie_title)
            update_screening(
                screening,
                movie.id,
                description,
                image,
                image_width,
                image_height,
                status == "draft",
                image_alt,
            )
            flash(f"Sessão «{movie_title}» atualizada com sucesso!", "success")
            return redirect(url_for("screening.index"))

    return render_template(
        "screening/update.html",
        current_movie_poster=image or screening.image,
        screening=screening,
        max_file_size=current_app.config["MAX_CONTENT_LENGTH"],
    )


@bp.route("/screening/<int:id>/delete", methods=("POST",))
@login_required
def delete(id):
    if request.method != "POST":
        abort(405)

    screening = get_screening_by_id(id)

    if not screening:
        abort(404)

    movie_title = screening.movie.title

    delete_screening(screening)
    flash(f"Sessão «{movie_title}» deletado com sucesso!", "success")
    return redirect(url_for("screening.index"))


@bp.route("/screening/image/describe", methods=("POST",))
@login_required
def describe_image():
    if request.method != "POST":
        abort(405)
    if "image" not in request.files:
        return jsonify({"details": "Imagem não encontrada."}), 400
    image = request.files["image"]
    try:
        gemini = Gemini()
    except ValueError:
        return jsonify({"details": "Chave de API Gemini não configurada."}), 500

    prompt_text = "Descreva essa imagem de forma a auxiliar uma pessoa com dificuldade de visão a entender o seu contexto, em português brasileiro."
    try:
        image_description = gemini.prompt_image(image, prompt_text)
    except APIError as e:
        return jsonify(
            {
                "details": "Erro ao gerar descrição da imagem. Tente novamente.",
                "info": str(e),
            }
        ), 502

    if not image_description:
        return jsonify(
            {"details": "Não foi possível gerar uma descrição para a imagem."}
        )
    return jsonify(text=image_description.strip())


@bp.route("/movie/<int:movie_id>/want-to-watch", methods=("POST",))
def want_to_watch(movie_id):
    if request.method != "POST":
        abort(405)

    movie = get_movie_by_id(movie_id)
    if not movie:
        abort(404)

    visitor_id = get_visitor_id(request) or new_visitor_id()
    wanted = toggle_want_to_watch(movie_id, visitor_id)

    response = jsonify({"wanted": wanted})
    response.set_cookie(
        VISITOR_COOKIE_NAME,
        visitor_id,
        max_age=SESSION_LIFETIME_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="Lax",
    )
    return response


@bp.route("/favoritos")
def favoritos():
    visitor_id = get_visitor_id(request)
    movie_ids = list(get_movie_ids_for_visitor(visitor_id)) if visitor_id else []
    user_logged_in = g.user is not None
    cards = build_favorites_feed(movie_ids, date.today(), user_logged_in)
    em_exibicao = [card for card in cards if not card["no_sessions"]]
    todos = sorted(
        (card for card in cards if card["no_sessions"]),
        key=lambda card: card["movie_title"],
    )
    return render_template(
        "screening/favoritos.html",
        em_exibicao=em_exibicao,
        todos=todos,
    )
