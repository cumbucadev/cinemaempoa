from google import genai
from google.genai import types

from flask_backend.env_config import GEMINI_API_KEY


class Gemini:
    """Interacts with Google's Gemini API via the google-genai SDK
    https://ai.google.dev/gemini-api/docs"""

    MODEL = "gemini-2.5-flash"

    def __init__(self):
        if GEMINI_API_KEY is None:
            raise ValueError("Invalid Gemini API key")
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def prompt_image(self, image, text):
        response = self.client.models.generate_content(
            model=self.MODEL,
            contents=[
                text,
                types.Part.from_bytes(
                    data=image.read(),
                    mime_type=image.mimetype or "image/jpeg",
                ),
            ],
        )
        return response.text
