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

bp = Blueprint("blog", __name__)


@bp.route("/blog")
def index():
    """Public blog listing page"""
    user_logged_in = g.user is not None
    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 10))
    except ValueError:
        abort(400)

    posts, pages, qtt_posts = blog_posts.get_all_paginated(
        page, limit, include_unpublished=user_logged_in
    )

    prev_page = page - 1 if page > 1 else None
    next_page = page + 1 if page < pages else None

    return render_template(
        "blog/index.html",
        posts=posts,
        curr_page=page,
        prev_page=prev_page,
        next_page=next_page,
        pages=pages,
        limit=limit,
        qtt_posts=qtt_posts,
        show_unpublished=user_logged_in,
    )


@bp.route("/blog/<slug>")
def show(slug):
    """Public individual post view"""
    user_logged_in = g.user is not None
    post = blog_posts.get_by_slug(slug)

    if not post:
        abort(404)

    # If post is not published and user is not logged in, show 404
    if not post.published and not user_logged_in:
        abort(404)

    return render_template("blog/show.html", post=post, show_unpublished=user_logged_in)