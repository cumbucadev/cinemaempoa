from typing import Optional

from flask_backend.db import db_session
from flask_backend.models import User


def get_by_username(username: str) -> Optional[User]:
    return db_session.query(User).filter(User.username == username).first()


def get_by_id(id: int) -> Optional[User]:
    return db_session.query(User).filter(User.id == id).first()


def create(username: str, password: str, roles: list[str]) -> User:
    user = User(username=username, password=password, roles=roles)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
