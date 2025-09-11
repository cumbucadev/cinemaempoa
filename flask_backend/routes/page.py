from flask import Blueprint, render_template

bp = Blueprint("page", __name__)


@bp.route("/about")
def about():
    return render_template("about.html")
