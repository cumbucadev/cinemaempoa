from flask_backend.repository import blog_posts
from flask_backend.routes.auth import login_required
from flask import Blueprint, request, redirect, url_for, flash, render_template, abort, g

bp = Blueprint("admin_blog", __name__)

@bp.route("/admin/blog")
@login_required
def index():
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
def new():
    """Create new blog post"""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        excerpt = request.form.get("excerpt", "").strip()
        slug = request.form.get("slug", "").strip()
        published = "published" in request.form
        featured_image = request.form.get("featured_image", "").strip()
        featured_image_alt = request.form.get("featured_image_alt", "").strip()
        source_url = request.form.get("source_url", "").strip()
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
                    source_url=source_url if source_url else None,
                )
                flash(f"Post '{post.title}' criado com sucesso!", "success")
                return redirect(url_for("admin_blog.edit", post_id=post.id))
            except Exception as e:
                error = f"Erro ao criar post: {str(e)}"

        flash(error, "danger")

    return render_template("blog/admin/new.html")

@bp.route("/admin/blog/<int:post_id>/edit", methods=("GET", "POST"))
@login_required
def edit(post_id):
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
        source_url = request.form.get("source_url", "").strip()

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
                    source_url=source_url if source_url else None,
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
                    return redirect(url_for("admin_blog.edit", post_id=post_id))
                else:
                    error = "Post não encontrado."
            except Exception as e:
                error = f"Erro ao atualizar post: {str(e)}"

        flash(error, "danger")

    return render_template("blog/admin/edit.html", post=post)

@bp.route("/admin/blog/<int:post_id>/delete", methods=("POST",))
@login_required
def delete(post_id):
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

    return redirect(url_for("admin_blog.index"))

@bp.route("/admin/blog/<int:post_id>/toggle-publish", methods=("POST",))
@login_required
def toggle_publish(post_id):
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

    return redirect(url_for("admin_blog.index"))