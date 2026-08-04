from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from flask_backend.models import MOVIE_INSPECTION_STATUSES
from flask_backend.repository import movie_inspections
from flask_backend.routes.auth import login_required
from flask_backend.service.movie_inspector import revert_inspection

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


@bp.route("/admin/movies/inspections/<int:inspection_id>/revert", methods=("POST",))
@login_required
def revert(inspection_id):
    inspection = movie_inspections.get_by_id(inspection_id)
    if inspection is None:
        abort(404)
    if inspection.status != "fixed":
        abort(400)

    revert_inspection(inspection_id)
    flash("Correção revertida.", "success")
    return redirect(
        url_for("admin_inspections.index", status=request.form.get("status", "all"))
    )
