from google import genai
from google.genai import types

from flask_backend.env_config import GEMINI_API_KEY
from flask_backend.service.gemini_models import call_with_fallback
from flask_backend.service.gemini_quota import classify_gemini_rate_limit


class Gemini:
    """Interacts with Google's Gemini API via the google-genai SDK
    https://ai.google.dev/gemini-api/docs"""

    def __init__(self):
        if GEMINI_API_KEY is None:
            raise ValueError("Invalid Gemini API key")
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def prompt_image(self, image, text):
        image_part = types.Part.from_bytes(
            data=image.read(),
            mime_type=image.mimetype or "image/jpeg",
        )

        def call(model_id):
            return self.client.models.generate_content(
                model=model_id,
                contents=[text, image_part],
            )

        response = call_with_fallback(call, classify_gemini_rate_limit)
        return response.text
