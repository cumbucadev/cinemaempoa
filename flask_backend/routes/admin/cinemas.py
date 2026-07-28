from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from flask_backend.repository.cinemas import (
    get_all,
    get_by_id,
    update as update_cinema,
)
from flask_backend.routes.auth import login_required
from flask_backend.service.screening import save_image, validate_image

bp = Blueprint("admin_cinemas", __name__)


@bp.route("/admin/cinemas")
@login_required
def index():
    """Admin cinema list, for picking one to edit."""
    cinemas = get_all()
    return render_template("cinema/admin/index.html", cinemas=cinemas)


@bp.route("/admin/cinemas/<int:cinema_id>/update", methods=("GET", "POST"))
@login_required
def update(cinema_id):
    cinema = get_by_id(cinema_id)
    if cinema is None:
        abort(404)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        url_value = request.form.get("url", "").strip()
        address = request.form.get("address", "").strip()
        opening_hours = request.form.get("opening_hours", "").strip()
        instagram_url = request.form.get("instagram_url", "").strip()
        map_embed_url = request.form.get("map_embed_url", "").strip()
        error = None

        if not name:
            error = "O nome do cinema é obrigatório."
        if not url_value:
            error = "O site do cinema é obrigatório."

        photo = None
        photo_width = None
        photo_height = None
        cinema_photo = request.files.get("cinema_photo", None)
        if cinema_photo and cinema_photo.filename:
            img_is_valid, message = validate_image(cinema_photo)
            if img_is_valid:
                photo, photo_width, photo_height = save_image(cinema_photo, current_app)
            else:
                error = message

        if error is not None:
            flash(error, "danger")
        else:
            update_cinema(
                cinema,
                name=name,
                url=url_value,
                address=address or None,
                opening_hours=opening_hours or None,
                instagram_url=instagram_url or None,
                map_embed_url=map_embed_url or None,
                photo=photo,
                photo_width=photo_width,
                photo_height=photo_height,
            )
            flash(f"Cinema «{name}» atualizado com sucesso!", "success")
            return redirect(url_for("admin_cinemas.update", cinema_id=cinema_id))

    return render_template(
        "cinema/admin/update.html",
        cinema=cinema,
        max_file_size=current_app.config["MAX_CONTENT_LENGTH"],
    )
