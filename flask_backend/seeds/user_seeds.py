from werkzeug.security import generate_password_hash

from flask_backend.models import Role, User
from flask_backend.utils.enums.role import RoleEnum


def _build_roles():
    user_role = Role(
        id=RoleEnum.USER.id,
        role=RoleEnum.USER.role,
    )

    admin_role = Role(
        id=RoleEnum.ADMIN.id,
        role=RoleEnum.ADMIN.role,
    )

    return [user_role, admin_role]


def create_user(db_session):
    roles = _build_roles()

    db_session.add(
        User(
            username="cinemaempoa",
            password=generate_password_hash("123123"),
            roles=roles,
        ),
    )
    db_session.commit()


def create_user_from_data(db_session, username, pwd):
    roles = _build_roles()
    db_session.add(
        User(username=username, password=generate_password_hash(pwd), roles=roles)
    )
    db_session.commit()
