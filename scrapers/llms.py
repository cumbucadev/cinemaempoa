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


class PauloAmorimEmailExtractorLLM:
    def __init__(self, model_name):
        self.model_name = model_name
        self.llm = self._get_llm()
        Settings.llm = self.llm

    def _get_llm(self):
        return _build_llm(self.model_name)

    def extract_screenings_from_text(self, str_received_date, text):
        # str_received_date is the email's Date header,
        # e.g. "Wed, 22 Jul 2026 10:15:00 +0000"
        received_date = datetime.strptime(str_received_date, "%a, %d %b %Y %H:%M:%S %z")
        year = received_date.year
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
        return f"""You are a cinema programming auditor for "Cinemateca Paulo Amorim", a cinema in Porto Alegre, Brazil with three screening rooms: Sala Paulo Amorim, Sala Eduardo Hirtz and Sala Norberto Lubisco. You need to collect screening information from the following text, which is the cinema's weekly newsletter email.
The email begins with a title in the format "PROGRAMAÇÃO DE <day> A <day> DE <month> DE <year>", stating the date range covered that week, sometimes followed by a global note such as "SEGUNDA-FEIRA NÃO HÁ SESSÕES" (meaning NO film has any session at all on that weekday, for the whole week), and then a few paragraphs of prose highlighting some of the films - these intro paragraphs are NOT movies, ignore them. The rest of the text is organized into sections per screening room (headings like "SALA PAULO AMORIM", "SALA EDUARDO HIRTZ", "SALA NORBERTO LUBISCO"), each containing one block of text per movie. The email ends with ticket pricing information and a signature - these are NOT movies, ignore them too.
For each movie, extract the following information:
1. Title: The movie's name, given in caps at the start of its block. It may be prefixed by a label like "ESTREIA:", "REESTREIA:", "SESSÃO NOSTALGIA:", "SESSÃO VITRINE:" or "ESPECIAL:" - do not include these labels in the title.
2. Image URL: these emails never include per-movie poster images - always return an empty string.
3. General Info: Information in the format "Country/Genre/Year/Duration" (e.g. "Brasil/Drama/2025/86min"), using the country/year/duration found in parentheses right after the title (e.g. "(Itália/França, 2025, 110min)") and the genre found at the end of the line right after that (e.g. "Legendado. Drama."). Append " | " followed by the room name(s) the movie plays in (e.g. "Brasil/Drama/2025/86min | Sala Paulo Amorim").
4. Director: The director's name, found after "Direção de" or "Direção:".
5. Classification: The age rating, found right after the distributor name (e.g. "14 anos", "16 anos", or "Livre").
6. Excerpt: The movie's synopsis, found after "Sinopse:".
7. Screening Dates: One or more sessions. Each movie has a "Sessões:" or "Sessão:" line giving a time (e.g. "14h45min", "19h"). By default, that time applies to every day of the newsletter's date range EXCEPT any weekday excluded by the global note (e.g. "SEGUNDA-FEIRA NÃO HÁ SESSÕES" excludes every Monday in the range). Watch for exceptions written in parentheses (or after a comma) next to the time:
   - "não haverá exibição no dia N" / "não haverá exibições nos dias N e M" excludes those specific dates from the default range.
   - "exibições nos dias N e M" / "exibições apenas no dia N" restricts the movie to ONLY those specific dates (ignore the default range entirely for this movie).
   A session may also be scoped to a single day directly (e.g. "Sessão: dia 28 (terça), às 19h" means only that one date).
   Convert every resulting screening into "YYYY-MM-DD HH:MM" format. Use {year} as the year unless the "PROGRAMAÇÃO DE ... A ... DE <year>" header states a different year explicitly, and take care with month rollovers when the date range spans two months.
Make sure to:
- Extract all available information for each movie
- If the exact same movie title appears in more than one room section, merge all its occurrences into a SINGLE entry: combine every screening date/time from every room into one screening_dates list, use the general_info/director/classification/excerpt from its first occurrence, and list every distinct room it plays in in the general_info room list.
- Handle cases where some information might be missing - use an empty string, never fabricate data
- Return the data in JSON format that matches the following structure:

If no movies are found, return an empty list."""

    def _get_prompt(self, year, text_content):
        messages = [
            ChatMessage(role="system", content=self._get_system_prompt(year)),
            ChatMessage(role="user", content=text_content),
        ]
        return messages
