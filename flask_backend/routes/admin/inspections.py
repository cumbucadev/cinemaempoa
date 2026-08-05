import json

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


def _build_row(inspection):
    """Flattens one MovieInspection into what the dashboard renders: the
    row itself, its decoded before/after snapshots, and the cinemas showing
    the movie."""
    return {
        "inspection": inspection,
        "previous": json.loads(inspection.previous_snapshot)
        if inspection.previous_snapshot
        else None,
        "new": json.loads(inspection.new_snapshot) if inspection.new_snapshot else None,
        "cinemas": sorted({s.cinema.name for s in inspection.movie.screenings}),
    }


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
        rows=[_build_row(i) for i in inspections],
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

    try:
        revert_inspection(inspection_id)
    except ValueError:
        # e.g. a newer fix has already moved this movie on - reverting now
        # would silently discard it.
        abort(400)

    flash("Correção revertida.", "success")
    return redirect(
        url_for("admin_inspections.index", status=request.form.get("status", "all"))
    )
