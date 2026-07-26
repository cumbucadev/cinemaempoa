import uuid
from typing import Optional

from flask import Request

VISITOR_COOKIE_NAME = "visitor_id"


def get_visitor_id(request: Request) -> Optional[str]:
    """Reads the visitor_id cookie without creating one - a visitor who
    has never tapped want-to-watch has no cookie and no marks."""
    return request.cookies.get(VISITOR_COOKIE_NAME)


def new_visitor_id() -> str:
    return uuid.uuid4().hex
