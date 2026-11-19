import sys
from datetime import datetime

from llama_index.core import Settings
from llama_index.core.bridge.pydantic import BaseModel
from llama_index.core.llms import ChatMessage

from flask_backend.env_config import GEMINI_API_KEY
from flask_backend.service.gemini_models import (
    AllGeminiModelsExhausted,
    call_with_fallback,
)
from flask_backend.service.gemini_quota import classify_gemini_rate_limit


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


def _build_llm(model_id):
    from llama_index.llms.google_genai import GoogleGenAI

    return GoogleGenAI(model=model_id, api_key=GEMINI_API_KEY)


class CineBancariosExtractorLLM:
    def __init__(self):
        if GEMINI_API_KEY is None:
            raise ValueError("GEMINI_API_KEY is not set")

    def _get_curr_year(self):
        current_datetime = datetime.now()
        return current_datetime.year

    def extract_screenings_from_text(self, strPubDate, text):
        # pubDate is in the format 2010-03-09T18:48:00+00:00
        pubDate = datetime.strptime(strPubDate, "%a, %d %b %Y %H:%M:%S %z")
        year = pubDate.year
        messages = self._get_prompt(year, text)

        def call(model_id):
            llm = _build_llm(model_id)
            Settings.llm = llm
            return llm.as_structured_llm(Movies).chat(messages)

        try:
            response = call_with_fallback(call, classify_gemini_rate_limit)
        except AllGeminiModelsExhausted:
            print("All Gemini models rate-limited. Exiting...", file=sys.stderr)
            return
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
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
    def __init__(self):
        if GEMINI_API_KEY is None:
            raise ValueError("GEMINI_API_KEY is not set")

    def extract_screenings_from_text(self, year, text):
        messages = self._get_prompt(year, text)

        def call(model_id):
            llm = _build_llm(model_id)
            Settings.llm = llm
            return llm.as_structured_llm(Movies).chat(messages)

        try:
            response = call_with_fallback(call, classify_gemini_rate_limit)
        except AllGeminiModelsExhausted:
            print("All Gemini models rate-limited. Exiting...", file=sys.stderr)
            return
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return
        return response.raw.model_dump_json()

    def _get_system_prompt(self, year):
        return f"""You are a cinema programming auditor for "Cine Cinco", a free university cinema run by PUCRS in Porto Alegre, Brazil. You need to collect screening information from the following text, which was extracted from one event page of the PUCRS cultural agenda.
The text begins with an "Informações do evento:" block giving the event's date or date range WITH the year (e.g. "04/11/2026 até 27/11/2026") and its venue - this is NOT a movie. Then comes the event's title (e.g. "Cine Cinco | Programação de Novembro") and a line with the category and the post's publication timestamp (e.g. "Cinema 28/10/2026 - 19h38") - these are NOT movies and the publication timestamp is NOT a screening, ignore them. An event is either a single film or a whole programme: a programme has intro paragraphs and themed batch headings (e.g. "Mostra de Cinema Negro") - these are NOT movies either. One block of text follows per movie.
For each movie, extract the following information:
1. Title: The name of the movie, usually the first line of its block
2. Image URL: If available, the URL of the movie's poster image
3. General Info: Information in the format "Country/Genre/Year/Duration" (e.g. "Brasil/Drama/2023/97min")
4. Director: The director's name, usually found after "Direção de". This is sometimes ABSENT entirely (e.g. "Sessão Surpresa" entries usually have no director mentioned) - if there is no director for a movie, return an empty string, never guess or invent one.
5. Classification: The age rating, usually found after "Classificação" (e.g. "Classificação 18 anos", or "Classificação Livre" for a free/unrestricted rating).
6. Excerpt: The movie's synopsis. Unlike other cinema listings, there is no "Sinopse:" label here - it is simply the unlabeled paragraph of prose that follows the general info/director/classification lines.
7. Screening Dates: One or more sessions, usually introduced by "Sessão:", in the format "D/M • weekday — HHhMM" (e.g. "1/7 • quarta — 17h"). The day and month are given but the session has NO YEAR - take it from the event's date range in "Informações do evento" (a range can cross the new year, e.g. "15/12/2026 até 20/01/2027": a session on 10/1 is then in 2027). Only if the text has no date range, use {year}. A session may be followed by remarks (e.g. "Sessão comentada com ...") - these are not part of the date. Convert each session into the format YYYY-MM-DD HH:MM. A movie may have more than one session listed - return one string per session.
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
