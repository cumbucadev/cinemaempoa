import imghdr
import os

from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}


def _check_if_actually_image(file):
    header = file.read(512)
    file.seek(0)
    format = imghdr.what(None, header)
    return format in ALLOWED_EXTENSIONS


def _allowed_extension(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_image(file) -> tuple[bool, str]:
    """Receives an uploaded file and returns whether it is valid
    based on the application rules"""
    filename = secure_filename(file.filename)
    if not _allowed_extension(filename):
        return (
            False,
            f"Extensão do arquivo inválida. Aceitamos {', '.join(ALLOWED_EXTENSIONS)}.",
        )
    if not _check_if_actually_image(file.stream):
        return (False, f"Arquivo corrompido ou inválido.")
    return True, None


def save_image(file, app) -> str:
    filename = secure_filename(file.filename)
    img_savepath = os.path.join(app.config.get("UPLOAD_FOLDER"), filename)
    file.save(img_savepath)
    return filename
