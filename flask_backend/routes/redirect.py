from flask import Blueprint, redirect

redirect_bp = Blueprint("redirect", __name__)

@redirect_bp.route('/cumbuca')
def redirecionar():
    return redirect("https://cumbuca.dev", code=302)
