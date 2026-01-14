from datetime import datetime

from google.genai.errors import ClientError as GoogleGenAIClientError
from llama_index.core import Settings
from llama_index.core.bridge.pydantic import BaseModel
from llama_index.core.llms import ChatMessage

from flask_backend.env_config import DEEPSEEK_API_KEY, GEMINI_API_KEY


class Movie(BaseModel):
    title: str
    image_url: str
    general_info: str
    director: str
    classification: str
    excerpt: str
    screening_dates: list[str]


class Movies(BaseModel):
    movies: list[Movie]


class CineBancariosExtractorLLM:
    def __init__(self, model_name):
        self.model_name = model_name
        self.llm = self._get_llm()
        Settings.llm = self.llm

    def _get_curr_year(self):
        current_datetime = datetime.now()
        return current_datetime.year

    def _get_llm(self):
        if self.model_name == "gemini-2.5-flash":
            if GEMINI_API_KEY is None:
                raise ValueError("GEMINI_API_KEY is not set")
            from llama_index.llms.google_genai import GoogleGenAI

            return GoogleGenAI(model=self.model_name, api_key=GEMINI_API_KEY)
        if self.model_name == "deepseek-chat":
            if DEEPSEEK_API_KEY is None:
                raise ValueError("DEEPSEEK_API_KEY is not set")
            from llama_index.llms.deepseek import DeepSeek

            return DeepSeek(model=self.model_name, api_key=DEEPSEEK_API_KEY)
        raise ValueError(
            "Invalid model name. Supported models: gemini-2.0-flash, deepseek-chat"
        )

    def extract_screenings_from_text(self, strPubDate, text):
        # pubDate is in the format 2010-03-09T18:48:00+00:00
        pubDate = datetime.strptime(strPubDate, "%a, %d %b %Y %H:%M:%S %z")
        year = pubDate.year
        try:
            response = self.llm.as_structured_llm(Movies).chat(
                self._get_prompt(year, text)
            )
        except Exception as e:
            print(f"Error: {e}")
            if isinstance(e, GoogleGenAIClientError) and e.code == 429:
                print("LLM rate limit exceeded. Exiting...")
            return
        return response.raw.model_dump_json()

    def _get_system_prompt(self, year):
        return f"""You are a cinema programming auditor. You need to collect screening information from the following text.
For each movie, extract the following information:
1. Title: The name of the movie
2. Image URL: If available, the URL of the movie's poster image
3. General Info: Information in the format "Country/Genre/Year/Duration" (e.g. "Brasil/Drama/2023/97min")
4. Director: The director's name, usually found after "Direção:"
5. Classification: The age rating, usually found after "Classificação indicativa:"
6. Excerpt: The movie's synopsis, usually found after "Sinopse:"
7. Screening Dates: All dates and times when the movie is shown
The text may contain multiple movies. Each movie's information is usually separated by blank lines or section headers like "ESTREIA" or "EM CARTAZ".
Make sure to:
- Extract all available information for each movie
- Handle cases where some information might be missing
- Keep the original formatting of the text where appropriate
- Include all screening times for each movie. The year is {year}. The format of the dates is YYYY-MM-DD HH:MM.
- Return the data in JSON format that matches the following structure:

If no movies are found, return an empty list."""

    def _get_prompt(self, year, text_content):
        messages = [
            ChatMessage(role="system", content=self._get_system_prompt(year)),
            ChatMessage(role="user", content=text_content),
        ]
        return messages
