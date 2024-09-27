import base64

import requests

from flask_backend.env_config import GEMINI_API_KEY


class Gemini:
    """Interacts with google's Gemini API
    https://ai.google.dev/gemini-api/docs"""

    def __init__(self):
        if GEMINI_API_KEY is None:
            raise ValueError("Invalid Gemini API key")
        self.headers = {"Content-Type": "application/json"}
        self.api_key = GEMINI_API_KEY
        self.models = {
            "gemini-pro-vision": "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-vision",  # this one seems to be discontinued
            "gemini-1.5-flash-latest": "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest",
        }

    def _get_url(self, model, resource):
        return f"{self.models[model]}:{resource}?key={self.api_key}"

    def prompt_image(self, image, text):
        """Based on https://ai.google.dev/gemini-api/docs/get-started/rest#text-and-image_input"""
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": text},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": base64.b64encode(image.read()).decode("utf-8"),
                            }
                        },
                    ]
                }
            ]
        }
        r = requests.post(
            self._get_url("gemini-1.5-flash-latest", "generateContent"),
            json=payload,
            headers=self.headers,
        )
        r.raise_for_status()
        return r.json()
