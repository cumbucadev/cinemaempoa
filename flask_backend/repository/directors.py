from flask_backend.db import db_session
from flask_backend.models import Director


def get_all():
    return db_session.query(Director).all()
