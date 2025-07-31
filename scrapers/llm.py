# -*- coding: utf-8 -*-

# Exemplo de uso de LLMs (através da lib llama index <https://docs.llamaindex.ai>)
# pra exportação de programação nas postagens do <https://cinebancarios.blogspot.com>.
#
# Adaptado de <https://docs.llamaindex.ai/en/stable/use_cases/extraction/>
# e <https://docs.llamaindex.ai/en/stable/examples/llm/gemini/>.
#
# O LLamaIndex permite o uso da maioria dos provedores de LLMs (OpenAI, Anthropic, etc)
# optei pelo Gemini pois o plano free tem uma quantidade de acessos pela API que supre
# o necessário pro projeto.
#
# A postagem do cinebancários utilizada foi <https://cinebancarios.blogspot.com/2024/10/animacao-infantil-placa-mae-e-longa-de.html>.
#
# Instalar bibliotecas necessárias com `pip3 install llama-index google-generativeai`.
# 
# Criar uma chave para uso do Google Gemini em <https://ai.google.dev/>.

import os
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from bs4 import BeautifulSoup

from llama_index.llms.gemini import Gemini
from llama_index.core import Settings
from llama_index.core.llms import ChatMessage

class ScreeningDate(BaseModel):
    """Data model for a screening date."""
    date: str  # ISO format date string (YYYY-MM-DD)
    time: str

class Movie(BaseModel):
    """Data model for a movie."""
    title: str
    image_url: str | None
    general_info: str | None  # Format: "Country/Genre/Year/Duration"
    director: str | None
    classification: str | None
    excerpt: str | None
    screening_dates: List[ScreeningDate]

class WeeklyProgram(BaseModel):
    movies: List[Movie]

class CineBancariosLLM:
    def __init__(self, api_key: str):
        """Initialize the LLM processor with the Google API key."""
        self.api_key = api_key
        os.environ["GOOGLE_API_KEY"] = api_key
        
        self.llm = Gemini()
        Settings.llm = self.llm

    def _extract_text_from_html(self, html_content: str) -> str:
        """Extract clean text from HTML content."""
        soup = BeautifulSoup(html_content, 'html.parser')
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        return soup.get_text(separator='\n', strip=True)

    def process_html(self, html_content: str) -> WeeklyProgram:
        """Process HTML content from CineBancarios and return structured program data."""
        # Extract clean text from HTML
        text_content = self._extract_text_from_html(html_content)
        
        # Create messages for LLM
        messages = [
            {
                "role": "system",
                "content": f"""You are a cinema programming auditor. You need to collect screening information from the following text. If the text includes a time interval, include one ScreeningDate for each day in the interval. Assume the year is {str(datetime.now().year)}.

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
- Include all screening times for each movie
- Return the data in JSON format that matches the WeeklyProgram model structure"""
            },
            {
                "role": "user",
                "content": text_content
            }
        ]
        
        # Get response from Gemini
        response = self.llm.chat(messages)
        
        # Parse the response into our model
        try:
            import json
            data = json.loads(response.text)
            return WeeklyProgram.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing response: {e}")
            print(f"Raw response: {response.text}")
            raise