from typing import List, Tuple

from sqlalchemy import func

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening
from flask_backend.repository.movies import delete as delete_movie
from flask_backend.repository.screenings import (
    create as create_screening,
    delete as delete_screening,
    get_by_movie_id_and_cinema_id as get_screening_by_movie_id_and_cinema_id,
    update_screening_dates,
)
from flask_backend.service.screening import build_dates


def dedupper():
    # gets all duplicated movies based on generated slug
    dupped_movies: List[Tuple[str, str]] = (
        db_session.query(Movie.slug, func.group_concat(Movie.id))
        .group_by(Movie.slug)
        .having(func.count(Movie.slug) > 1)
        .all()
    )

    for slug, ids_str in dupped_movies:
        ids = ids_str.split(",")
        movies = (
            db_session.query(Movie)
            .join(Screening)
            .filter(Movie.id.in_(ids))
            .order_by(Movie.id)
            .all()
        )

        # Keeps the oldest record
        resulting_movie = movies[0]
        print(f"Keeping movie id {resulting_movie.id} for {slug}")

        for idx, movie in enumerate(movies):
            if idx == 0:
                continue
            for screening in movie.screenings:
                # checks if cinema already has screening for the movie we kept
                screening_exists = get_screening_by_movie_id_and_cinema_id(
                    resulting_movie.id, screening.cinema.id
                )
                if not screening_exists:
                    # if the screening doesnt exist, copy it over and delete the original
                    create_screening(
                        movie_id=resulting_movie.id,
                        cinema_id=screening.cinema_id,
                        url_origin=screening.url,
                        image=screening.image,
                        image_alt=screening.image_alt,
                        description=screening.description,
                        is_draft=screening.draft,
                        image_width=screening.image_width,
                        image_height=screening.image_height,
                        screening_dates=build_dates(
                            [f"{sd.date}T{sd.time}" for sd in screening.dates]
                        ),
                    )
                    delete_screening(screening)
                    continue
                # screening already exists. we need to copy the dates over
                existing_dates = build_dates(
                    [f"{sd.date}T{sd.time}" for sd in screening_exists.dates]
                )
                screening_dates = build_dates(
                    [f"{sd.date}T{sd.time}" for sd in screening.dates]
                )
                for new_date in screening_dates:
                    already_registered = False
                    for existing_date in existing_dates:
                        same_date = existing_date.date == new_date.date
                        same_time = existing_date.time == new_date.time
                        if same_date and same_time:
                            already_registered = True
                            break
                    if not already_registered:
                        existing_dates.append(new_date)
                # deletes the original screening since we already copied the necessary dates
                delete_screening(screening)
                # adds the copied dates to the existing screening
                update_screening_dates(screening_exists, existing_dates)
            # removes the duplicated movie
            assert (
                len(movie.screenings) == 0
            ), "There should be no screenings left at this point"
            delete_movie(movie)
