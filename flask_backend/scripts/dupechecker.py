"""Finds duplicated movies based on the `slug` field. Returns a list of duplicated movies and their screenings on each cinema."""

from datetime import datetime

from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening
from utils import dump_utf8_json


def dupe_checker():
    dupped_movies = (
        db_session.query(
            Movie.slug, func.group_concat(Movie.id), func.group_concat(Movie.title)
        )
        .group_by(Movie.slug)
        .having(func.count(Movie.slug) > 1)
    )

    dupped_info = []
    for slug, ids_str, titles_str in dupped_movies:
        dupped_movie = {
            "slug": slug,
            "movie_ids": ids_str,
            "movie_titles": titles_str,
            "cinemas": {},
        }
        ids = ids_str.split(",")
        movies = db_session.query(Movie).filter(Movie.id.in_(ids)).all()
        for movie in movies:
            screenings = (
                db_session.query(Screening).filter(Screening.movie_id == movie.id).all()
            )
            for screening in screenings:
                cinema = screening.cinema.slug
                if cinema not in dupped_movie["cinemas"]:
                    dupped_movie["cinemas"][cinema] = {"dates": set(), "images": set()}
                dupped_movie["cinemas"][cinema]["images"].add(screening.image)
                for _date in screening.dates:
                    dupped_movie["cinemas"][cinema]["dates"].add(
                        f"{_date.date}T{_date.time}"
                    )
        dupped_info.append(dupped_movie)

    for dupped_movie in dupped_info:
        for cin in dupped_movie["cinemas"].keys():
            dupped_movie["cinemas"][cin]["images"] = list(
                dupped_movie["cinemas"][cin]["images"]
            )
            dupped_movie["cinemas"][cin]["dates"] = sorted(
                list(dupped_movie["cinemas"][cin]["dates"]),
                key=lambda x: datetime.strptime(x, "%Y-%m-%dT%H:%M"),
            )

    print(dump_utf8_json(dupped_info))
