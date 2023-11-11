from sqlite3 import Row

from flask_backend.db import get_db


def get_todays_screenings():
    screenings = (
        get_db()
        .execute(
            "SELECT s.id, s.screening_time, s.description, c.name, c.url"
            " FROM screening s JOIN cinema c ON s.cinema_id = c.id"
            " ORDER BY c.name ASC"
        )
        .fetchall()
    )

    return screenings


def get_screening_by_id(screening_id: int) -> Row | None:
    screening = (
        get_db()
        .execute(
            "SELECT cinema_id, screening_date, screening_time, movie_title, screening_url, description, image FROM screening WHERE id = ?",
            (screening_id,),
        )
        .fetchone()
    )
    return screening


def get_todays_screenings_by_cinema_id(cinema_id: int):
    screenings = (
        get_db()
        .execute(
            "SELECT s.id, s.screening_time, image, movie_title, description, c.name, c.url"
            " FROM screening s JOIN cinema c ON s.cinema_id = c.id"
            " WHERE c.id = ?",
            (cinema_id,),
        )
        .fetchall()
    )

    return screenings
