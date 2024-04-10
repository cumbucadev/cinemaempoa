from werkzeug.security import generate_password_hash

from flask_backend.models import User


def create_user(db_session):
    db_session.add(
        User(username="cinemaempoa", password=generate_password_hash("123123"))
    )
    db_session.commit()


def create_user_from_data(db_session, username, pwd):
    db_session.add(User(username=username, password=generate_password_hash(pwd)))
    db_session.commit()
