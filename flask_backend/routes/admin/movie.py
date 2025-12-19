from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from flask_backend.repository import (
    directors as directors_repository,
    movies as movies_repository,
)
from flask_backend.routes.auth import login_required

bp = Blueprint("admin_movie", __name__)


@bp.route("/admin/movie/<int:movie_id>/edit", methods=("GET", "POST"))
@login_required
def edit(movie_id):
    """Edit movie information"""
    movie = movies_repository.get_by_id(movie_id)
    if not movie:
        abort(404)

    directors = directors_repository.get_all()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        slug = request.form.get("slug", "").strip()
        director_ids = request.form.getlist("director_ids")
        error = None

        if not title:
            error = "Título é obrigatório."

        if error is None:
            try:
                updated_post = movies_repository.update(
                    movie=movie, title=title, slug=slug, director_ids=director_ids
                )
                if updated_post:
                    flash(
                        f"Filme '{updated_post.title}' atualizado com sucesso!",
                        "success",
                    )
                    return redirect(url_for("admin_movie.edit", movie_id=movie_id))
                else:
                    error = "Filme não encontrado."
            except Exception as e:
                error = f"Erro ao atualizar filme: {str(e)}"

        flash(error, "danger")

    return render_template("movie/admin/edit.html", movie=movie, directors=directors)
