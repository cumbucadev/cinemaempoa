from enum import Enum


class RoleEnum(Enum):
    USER = ("USER", 1)
    ADMIN = ("ADMIN", 2)

    def __init__(self, role_name: str, role_id: int):
        self.role_name = role_name
        self.role_id = role_id

    @property
    def role(self):
        return self.role_name

    @property
    def id(self):
        return self.role_id
