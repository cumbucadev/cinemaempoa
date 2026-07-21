from datetime import datetime

from google.genai.errors import ClientError as GoogleGenAIClientError
from llama_index.core import Settings
from llama_index.core.bridge.pydantic import BaseModel
from llama_index.core.llms import ChatMessage

from flask_backend.env_config import GEMINI_API_KEY


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


def _build_llm(model_name):
    if model_name == "gemini-2.5-flash":
        if GEMINI_API_KEY is None:
            raise ValueError("GEMINI_API_KEY is not set")
        from llama_index.llms.google_genai import GoogleGenAI

        return GoogleGenAI(model=model_name, api_key=GEMINI_API_KEY)
    raise ValueError("Invalid model name. Supported models: gemini-2.5-flash")


class CineBancariosExtractorLLM:
    def __init__(self, model_name):
        self.model_name = model_name
        self.llm = self._get_llm()
        Settings.llm = self.llm

    def _get_curr_year(self):
        current_datetime = datetime.now()
        return current_datetime.year

    def _get_llm(self):
        return _build_llm(self.model_name)

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


class CineCincoExtractorLLM:
    def __init__(self, model_name):
        self.model_name = model_name
        self.llm = self._get_llm()
        Settings.llm = self.llm

    def _get_llm(self):
        return _build_llm(self.model_name)

    def extract_screenings_from_text(self, year, text):
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
        return f"""You are a cinema programming auditor for "Cine Cinco", a free university cinema run by PUCRS in Porto Alegre, Brazil. You need to collect screening information from the following text, which was extracted from the cinema's programming page.
The text begins with a page title, a "Programação" heading, and sometimes a themed batch heading (e.g. "COPA DO CINEMA") followed by an intro paragraph - these are NOT movies, ignore them. After that, one block of text follows per movie. The text also ends with a few paragraphs of general information about the Cine Cinco venue (its location, capacity, regular schedule) - these are NOT movies either, ignore them too.
For each movie, extract the following information:
1. Title: The name of the movie, usually the first line of its block
2. Image URL: If available, the URL of the movie's poster image
3. General Info: Information in the format "Country/Genre/Year/Duration" (e.g. "Brasil/Drama/2023/97min")
4. Director: The director's name, usually found after "Direção de". This is sometimes ABSENT entirely (e.g. "Sessão Surpresa" entries usually have no director mentioned) - if there is no director for a movie, return an empty string, never guess or invent one.
5. Classification: The age rating, usually found after "Classificação" (e.g. "Classificação 18 anos", or "Classificação Livre" for a free/unrestricted rating).
6. Excerpt: The movie's synopsis. Unlike other cinema listings, there is no "Sinopse:" label here - it is simply the unlabeled paragraph of prose that follows the general info/director/classification lines.
7. Screening Dates: One or more sessions, usually introduced by "Sessão:", in the format "D/M • weekday — HHhMM" (e.g. "1/7 • quarta — 17h"). The day and month are given but the YEAR IS NOT PRESENT IN THE TEXT - always use {year} as the year. Convert each session into the format YYYY-MM-DD HH:MM. A movie may have more than one session listed - return one string per session.
Each movie's block is usually followed by a blank line, and sometimes a trailing "Apoio: ..." sponsor line - ignore the sponsor line, it is not part of the film's info.
Make sure to:
- Extract all available information for each movie
- Handle cases where some information (especially Director) might be missing - use an empty string, never fabricate data
- Include all screening times for each movie
- Return the data in JSON format that matches the following structure:

If no movies are found, return an empty list."""

    def _get_prompt(self, year, text_content):
        messages = [
            ChatMessage(role="system", content=self._get_system_prompt(year)),
            ChatMessage(role="user", content=text_content),
        ]
        return messages
