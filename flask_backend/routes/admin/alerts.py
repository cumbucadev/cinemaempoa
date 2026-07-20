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

from flask_backend.models import ALERT_STATUSES
from flask_backend.repository import alerts
from flask_backend.routes.auth import login_required
from flask_backend.service import alert_text

bp = Blueprint("admin_alerts", __name__)

STATUS_FILTERS = (*ALERT_STATUSES, "all")


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

    pending_alerts, pages, qtt_alerts = alerts.get_all_paginated(
        page, limit, status=None if status == "all" else status
    )
    alert_text.refresh_pending(pending_alerts)

    prev_page = page - 1 if page > 1 else None
    next_page = page + 1 if page < pages else None

    return render_template(
        "alerts/admin/index.html",
        alerts=pending_alerts,
        status=status,
        curr_page=page,
        prev_page=prev_page,
        next_page=next_page,
        pages=pages,
        limit=limit,
        qtt_alerts=qtt_alerts,
    )


@bp.route("/admin/alerts/<int:alert_id>/mark-posted", methods=("POST",))
@login_required
def mark_posted(alert_id):
    """Mark alert as posted"""
    if alerts.mark_posted(alert_id, user_id=g.user.id) is None:
        abort(404)
    flash("Alerta marcado como postado!", "success")

    return redirect(
        url_for("admin_alerts.index", status=request.form.get("status", "pending"))
    )


@bp.route("/admin/alerts/<int:alert_id>/dismiss", methods=("POST",))
@login_required
def dismiss(alert_id):
    """Dismiss alert"""
    if alerts.dismiss(alert_id, user_id=g.user.id) is None:
        abort(404)
    flash("Alerta descartado.", "success")

    return redirect(
        url_for("admin_alerts.index", status=request.form.get("status", "pending"))
    )
