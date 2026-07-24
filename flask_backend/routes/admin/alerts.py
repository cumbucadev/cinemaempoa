from datetime import date
from math import ceil

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from flask_backend.models import ALERT_ACTIONS
from flask_backend.repository import alert_actions
from flask_backend.repository.screenings import (
    get_screening_by_id,
    get_screenings_with_upcoming_dates,
)
from flask_backend.routes.auth import login_required
from flask_backend.service.screening_alerts import get_pending_rows

bp = Blueprint("admin_alerts", __name__)

STATUS_FILTERS = ("pending", *ALERT_ACTIONS, "all")


@bp.route("/admin/alerts")
@login_required
def index():
    """Admin alert review queue"""
    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
    except ValueError:
        abort(400)

    if page < 1 or limit < 1:
        abort(400)

    status = request.args.get("status", "pending")
    if status not in STATUS_FILTERS:
        abort(400)

    prev_page = page - 1 if page > 1 else None

    if status == "pending":
        screenings = get_screenings_with_upcoming_dates()
        latest_actions = alert_actions.get_latest_by_screening_ids(
            [screening.id for screening in screenings]
        )
        rows = get_pending_rows(screenings, latest_actions)
        qtt_alerts = len(rows)
        pages = ceil(qtt_alerts / limit) if qtt_alerts else 0
        offset = (page - 1) * limit
        return render_template(
            "alerts/admin/index.html",
            status=status,
            pending_rows=rows[offset : offset + limit],
            curr_page=page,
            prev_page=prev_page,
            next_page=page + 1 if page < pages else None,
            pages=pages,
            limit=limit,
            qtt_alerts=qtt_alerts,
        )

    actions, pages, qtt_alerts = alert_actions.get_paginated(
        None if status == "all" else status, page, limit
    )

    return render_template(
        "alerts/admin/index.html",
        status=status,
        actions=actions,
        curr_page=page,
        prev_page=prev_page,
        next_page=page + 1 if page < pages else None,
        pages=pages,
        limit=limit,
        qtt_alerts=qtt_alerts,
    )


def _parse_remind_at(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        abort(400)


@bp.route("/admin/alerts/<int:screening_id>/mark-posted", methods=("POST",))
@login_required
def mark_posted(screening_id):
    """Mark a screening as posted, optionally with a reminder date."""
    remind_at = _parse_remind_at(request.form.get("remind_at"))
    if get_screening_by_id(screening_id) is None:
        abort(404)

    alert_actions.create(
        screening_id=screening_id,
        action="posted",
        remind_at=remind_at,
        created_by_user_id=g.user.id,
    )
    flash("Marcado como postado!", "success")

    return redirect(
        url_for("admin_alerts.index", status=request.form.get("status", "pending"))
    )


@bp.route("/admin/alerts/<int:screening_id>/dismiss", methods=("POST",))
@login_required
def dismiss(screening_id):
    """Dismiss a screening, optionally with a reminder date."""
    remind_at = _parse_remind_at(request.form.get("remind_at"))
    if get_screening_by_id(screening_id) is None:
        abort(404)

    alert_actions.create(
        screening_id=screening_id,
        action="dismissed",
        remind_at=remind_at,
        created_by_user_id=g.user.id,
    )
    flash("Descartado.", "success")

    return redirect(
        url_for("admin_alerts.index", status=request.form.get("status", "pending"))
    )
