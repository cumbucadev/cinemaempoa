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
from werkzeug.exceptions import abort

from flask_backend.repository import blog_posts
from flask_backend.routes.auth import login_required

bp = Blueprint("blog", __name__)


@bp.route("/blog")
def index():
    """Public blog listing page"""
    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 10))
    except ValueError:
        abort(400)

    user_logged_in = g.user is not None
    posts, pages, qtt_posts = blog_posts.get_all_paginated(
        page, limit, include_unpublished=user_logged_in
    )

    prev_page = page - 1 if page > 1 else None
    next_page = page + 1 if page < pages else None

    return render_template(
        "blog/index.html",
        posts=posts,
        show_unpublished=user_logged_in,
        curr_page=page,
        prev_page=prev_page,
        next_page=next_page,
        pages=pages,
        limit=limit,
        qtt_posts=qtt_posts,
    )


@bp.route("/blog/<slug>")
def post(slug):
    """Public individual post view"""
    user_logged_in = g.user is not None
    post = blog_posts.get_by_slug(slug)

    if not post:
        abort(404)

    # If post is not published and user is not logged in, show 404
    if not post.published and not user_logged_in:
        abort(404)

    return render_template("blog/post.html", post=post)


# Admin routes (all require login)
@bp.route("/admin/blog")
@login_required
def admin_index():
    """Admin blog management dashboard"""
    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
    except ValueError:
        abort(400)

    posts, pages, qtt_posts = blog_posts.get_all_paginated(
        page, limit, include_unpublished=True
    )

    prev_page = page - 1 if page > 1 else None
    next_page = page + 1 if page < pages else None

    return render_template(
        "blog/admin/index.html",
        posts=posts,
        curr_page=page,
        prev_page=prev_page,
        next_page=next_page,
        pages=pages,
        limit=limit,
        qtt_posts=qtt_posts,
    )


@bp.route("/admin/blog/new", methods=("GET", "POST"))
@login_required
def admin_new():
    """Create new blog post"""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        excerpt = request.form.get("excerpt", "").strip()
        slug = request.form.get("slug", "").strip()
        published = "published" in request.form
        featured_image = request.form.get("featured_image", "").strip()
        featured_image_alt = request.form.get("featured_image_alt", "").strip()

        error = None

        if not title:
            error = "Título é obrigatório."
        elif not content:
            error = "Conteúdo é obrigatório."

        if error is None:
            try:
                post = blog_posts.create(
                    title=title,
                    content=content,
                    author_id=g.user.id,
                    slug=slug if slug else None,
                    excerpt=excerpt if excerpt else None,
                    published=published,
                    featured_image=featured_image if featured_image else None,
                    featured_image_alt=featured_image_alt
                    if featured_image_alt
                    else None,
                )
                flash(f"Post '{post.title}' criado com sucesso!", "success")
                return redirect(url_for("blog.admin_edit", post_id=post.id))
            except Exception as e:
                error = f"Erro ao criar post: {str(e)}"

        flash(error, "danger")

    return render_template("blog/admin/new.html")


@bp.route("/admin/blog/<int:post_id>/edit", methods=("GET", "POST"))
@login_required
def admin_edit(post_id):
    """Edit blog post"""
    post = blog_posts.get_by_id(post_id)
    if not post:
        abort(404)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        excerpt = request.form.get("excerpt", "").strip()
        slug = request.form.get("slug", "").strip()
        published = "published" in request.form
        featured_image = request.form.get("featured_image", "").strip()
        featured_image_alt = request.form.get("featured_image_alt", "").strip()

        error = None

        if not title:
            error = "Título é obrigatório."
        elif not content:
            error = "Conteúdo é obrigatório."

        if error is None:
            try:
                updated_post = blog_posts.update(
                    post_id=post_id,
                    title=title,
                    content=content,
                    slug=slug if slug else None,
                    excerpt=excerpt if excerpt else None,
                    published=published,
                    featured_image=featured_image if featured_image else None,
                    featured_image_alt=featured_image_alt
                    if featured_image_alt
                    else None,
                )
                if updated_post:
                    flash(
                        f"Post '{updated_post.title}' atualizado com sucesso!",
                        "success",
                    )
                    return redirect(url_for("blog.admin_edit", post_id=post_id))
                else:
                    error = "Post não encontrado."
            except Exception as e:
                error = f"Erro ao atualizar post: {str(e)}"

        flash(error, "danger")

    return render_template("blog/admin/edit.html", post=post)


@bp.route("/admin/blog/<int:post_id>/delete", methods=("POST",))
@login_required
def admin_delete(post_id):
    """Delete blog post"""
    post = blog_posts.get_by_id(post_id)
    if not post:
        abort(404)

    try:
        success = blog_posts.delete(post_id)
        if success:
            flash(f"Post '{post.title}' deletado com sucesso!", "success")
        else:
            flash("Erro ao deletar post.", "danger")
    except Exception as e:
        flash(f"Erro ao deletar post: {str(e)}", "danger")

    return redirect(url_for("blog.admin_index"))


@bp.route("/admin/blog/<int:post_id>/toggle-publish", methods=("POST",))
@login_required
def admin_toggle_publish(post_id):
    """Toggle published status of blog post"""
    post = blog_posts.get_by_id(post_id)
    if not post:
        abort(404)

    try:
        updated_post = blog_posts.toggle_published(post_id)
        if updated_post:
            status = "publicado" if updated_post.published else "despublicado"
            flash(f"Post '{updated_post.title}' {status} com sucesso!", "success")
        else:
            flash("Erro ao alterar status do post.", "danger")
    except Exception as e:
        flash(f"Erro ao alterar status do post: {str(e)}", "danger")

    return redirect(url_for("blog.admin_index"))
