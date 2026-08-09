from flask import Blueprint, current_app, render_template

from flask_backend.repository.screenings import get_weekend_screening_dates
from flask_backend.routes.auth import login_required
from flask_backend.service.weekend_export import (
    build_weekend_cover_image,
    build_weekend_export_images,
)

bp = Blueprint("admin_weekend", __name__)


@bp.route("/admin/weekend")
@login_required
def index():
    screening_dates, friday_date, saturday_date, sunday_date = (
        get_weekend_screening_dates()
    )
    day_exports = build_weekend_export_images(
        screening_dates, friday_date, saturday_date, sunday_date
    )
    cover_image_base64 = build_weekend_cover_image(
        screening_dates,
        current_app.config["UPLOAD_FOLDER"],
        friday_date,
        saturday_date,
        sunday_date,
    )
    return render_template(
        "screening/admin/weekend.html",
        day_exports=day_exports,
        cover_image_base64=cover_image_base64,
    )
