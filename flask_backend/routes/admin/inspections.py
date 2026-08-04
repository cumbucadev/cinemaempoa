from flask import (
    Blueprint,
    abort,
    flash,  # noqa: F401 -- used by revert() view in Task 7
    redirect,  # noqa: F401 -- used by revert() view in Task 7
    render_template,
    request,
    url_for,  # noqa: F401 -- used by revert() view in Task 7
)

from flask_backend.models import MOVIE_INSPECTION_STATUSES
from flask_backend.repository import movie_inspections
from flask_backend.routes.auth import login_required

bp = Blueprint("admin_inspections", __name__)

STATUS_FILTERS = (*MOVIE_INSPECTION_STATUSES, "all")


@bp.route("/admin/movies/inspections")
@login_required
def index():
    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
    except ValueError:
        abort(400)

    if page < 1 or limit < 1:
        abort(400)

    status = request.args.get("status", "all")
    if status not in STATUS_FILTERS:
        abort(400)

    inspections, pages, total = movie_inspections.get_paginated(
        None if status == "all" else status, page, limit
    )
    prev_page = page - 1 if page > 1 else None

    return render_template(
        "inspections/admin/index.html",
        status=status,
        inspections=inspections,
        curr_page=page,
        prev_page=prev_page,
        next_page=page + 1 if page < pages else None,
        pages=pages,
        limit=limit,
        total=total,
    )
