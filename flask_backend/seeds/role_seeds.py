from flask_backend.models import Role
from flask_backend.utils.enums.role import RoleEnum


def create_roles(db_session):
    user = Role(id=RoleEnum.USER.id, role=RoleEnum.USER.role)

    admin = Role(id=RoleEnum.ADMIN.id, role=RoleEnum.ADMIN.role)
    db_session.add_all([user, admin])
    db_session.commit()
