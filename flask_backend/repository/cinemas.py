from flask_backend.db import get_db


def get_all():
    cinemas = (
        get_db().execute("SELECT *" " FROM cinema" " ORDER BY name ASC").fetchall()
    )

    return cinemas
