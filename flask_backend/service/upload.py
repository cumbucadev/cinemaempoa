import base64
import os
from typing import Optional, Tuple

import requests
from PIL import Image
from werkzeug.utils import secure_filename

from flask_backend.env_config import IMGBB_API_KEY


def upload_image_to_api(app, image) -> Tuple[str, int, int]:
    url = "https://api.imgbb.com/1/upload"
    payload = {
        "key": IMGBB_API_KEY,
        "image": base64.b64encode(image.read()),
    }
    res = requests.post(url, payload)
    res.raise_for_status()
    image_url = res.json()["data"]["url"]
    width = res.json()["data"]["width"]
    height = res.json()["data"]["height"]

    return image_url, width, height


def upload_image_to_local_disk(
    file, app, filename: Optional[str] = None
) -> Tuple[str, int, int]:
    if filename:
        filename = secure_filename(filename)
    else:
        filename = secure_filename(file.filename)
    img_savepath = os.path.join(app.config.get("UPLOAD_FOLDER"), filename)

    try:
        file.save(img_savepath)
    except AttributeError:
        with open(img_savepath, "wb") as f:
            f.write(file.read())

    with open(img_savepath, "rb") as f:
        loaded_image = Image.open(f)

    local_file_url = os.path.join("/screening/assets/", filename)

    return local_file_url, loaded_image.width, loaded_image.height
