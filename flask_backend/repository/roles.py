from typing import Optional

from flask_backend.db import db_session
from flask_backend.models import Role


def get_by_role_name(name: str) -> Optional[Role]:
    return db_session.query(Role).filter(Role.role == name).first()


def get_by_id(id: int) -> Optional[Role]:
    return db_session.query(Role).filter(Role.id == id).first()


def create(role: str) -> Role:
    role = Role(role=role)
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role
