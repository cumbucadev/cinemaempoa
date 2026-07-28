from flask import Blueprint, abort, render_template

from flask_backend.repository.cinemas import get_all, get_by_slug
from flask_backend.repository.screenings import (
    get_latest_screening_images_for_movies,
    get_past_movies_for_cinema,
    get_screenings_with_upcoming_dates,
)

bp = Blueprint("cinema", __name__)


@bp.route("/cinemas")
def index():
    cinemas = get_all()
    return render_template("cinema/index.html", cinemas=cinemas)


@bp.route("/cinemas/<slug>")
def show(slug):
    cinema = get_by_slug(slug)
    if cinema is None:
        abort(404)

    upcoming_screenings = get_screenings_with_upcoming_dates(cinema_id=cinema.id)
    past_movies = get_past_movies_for_cinema(cinema.id)
    past_movie_screenings = get_latest_screening_images_for_movies(
        cinema.id, [movie.id for movie, _exclusive in past_movies]
    )

    return render_template(
        "cinema/show.html",
        cinema=cinema,
        upcoming_screenings=upcoming_screenings,
        past_movies=past_movies,
        past_movie_screenings=past_movie_screenings,
    )
