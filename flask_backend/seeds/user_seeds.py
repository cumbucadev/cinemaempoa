from werkzeug.security import generate_password_hash

from flask_backend.models import User


def create_user(db_session):
    db_session.add(User(username="guites", password=generate_password_hash("123123")))
    db_session.commit()
