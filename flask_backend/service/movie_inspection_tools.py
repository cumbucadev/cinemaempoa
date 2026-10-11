"""The movie inspector's tools and verdict rules, independent of whichever
agent loop drives them: a movie's TMDB snapshot, the rematch, the three
observation tools (TMDB candidate search, TMDB details, screening source) and
applying a verdict given the tmdb ids the agent actually observed.

Observation tools never raise on TMDB/network failures: the error comes back
as observation text, so the agent can keep reasoning or conclude
`needs_review`.

The per-request layer (`get_movie_context`, ...) is what the MCP server in
flask_backend/mcp_server.py exposes: each function takes a `request_id` and
raises InspectionRequestError, with a pt-BR message, when that request
cannot be worked on.
"""

import logging
from dataclasses import dataclass
from typing import Iterable, Literal, Optional

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel

from flask_backend.db import db_session
from flask_backend.models import Movie, MovieInspectionRequest
from flask_backend.repository import movie_inspection_requests
from flask_backend.repository.screenings import get_screening_by_id
from flask_backend.service.movie_metadata_pipeline import (
    apply_tmdb_details,
    clear_tmdb_metadata,
)
from flask_backend.service.tmdb import TMDBClient

logger = logging.getLogger(__name__)

SCREENING_SOURCE_MAX_CHARS = 4000

VerdictStatus = Literal["consistent", "fixed", "needs_review"]


@dataclass
class InspectionOutcome:
    status: str
    reasoning: str
    before_snapshot: Optional[dict] = None
    after_snapshot: Optional[dict] = None


def snapshot(movie: Movie) -> dict:
    """Captures the movie's current TMDB-derived identity, for the
    before/after audit trail on MovieInspection rows."""
    return {
        "tmdb_id": movie.tmdb_id,
        "title": movie.title,
        "original_title": movie.original_title,
        "release_year": movie.release_year,
        "directors": [d.name for d in movie.directors],
        "countries": [c.name for c in movie.countries],
    }


def apply_rematch(movie: Movie, tmdb_id: Optional[int]) -> None:
    """Re-links `movie` to `tmdb_id`, or clears its TMDB link entirely if
    `tmdb_id` is None (used when reverting a fix back to "unmatched").
    Commits."""
    if tmdb_id is None:
        clear_tmdb_metadata(movie)
        movie.tmdb_id = None
        movie.tmdb_excluded = False
    else:
        details = TMDBClient().get_movie_details(tmdb_id)
        apply_tmdb_details(movie, tmdb_id, details)
    db_session.add(movie)
    db_session.commit()


def run_search_tmdb_candidates(title: str) -> tuple[str, list[int]]:
    """Returns the observation text plus every tmdb id it exposed, so the
    caller can record which ids the agent actually saw (see
    `resolve_verdict`)."""
    try:
        results = TMDBClient().search_movies(title)
    except requests.RequestException as exc:
        return f"Erro ao buscar '{title}' no TMDB: {exc}", []
    if not results:
        return f"Nenhum resultado no TMDB para '{title}'.", []
    ids = [r["id"] for r in results]
    lines = [
        "- tmdb_id={} título='{}' ano={}".format(
            r["id"], r.get("title"), (r.get("release_date") or "????")[:4]
        )
        for r in results
    ]
    return "Candidatos no TMDB para '{}':\n{}".format(title, "\n".join(lines)), ids


def run_get_tmdb_details(tmdb_id: int) -> tuple[str, list[int]]:
    """Returns the observation text plus the tmdb id it exposed (none when
    the lookup failed)."""
    try:
        details = TMDBClient().get_movie_details(tmdb_id)
    except requests.RequestException as exc:
        return f"Erro ao buscar detalhes do TMDB id={tmdb_id}: {exc}", []
    directors = ", ".join(d["name"] for d in details["directors"]) or "desconhecido"
    countries = ", ".join(c["name"] for c in details["countries"]) or "desconhecido"
    observation = (
        f"Detalhes do TMDB id={tmdb_id}: título original="
        f"'{details['original_title']}', ano={details['release_year']}, "
        f"diretor(es)={directors}, país(es)={countries}"
    )
    return observation, [tmdb_id]


def run_fetch_screening_source(screening_id: int) -> str:
    """Fetches the screening's source page and returns its text, stripped of
    HTML and cut to SCREENING_SOURCE_MAX_CHARS. Does not check which movie
    the screening belongs to: that is the caller's job."""
    screening = get_screening_by_id(screening_id)
    if screening is None:
        return f"Sessão #{screening_id} não encontrada."
    if not screening.url:
        return f"Sessão #{screening_id} não tem URL de origem cadastrada."
    try:
        response = requests.get(screening.url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        return f"Erro ao buscar {screening.url}: {exc}"
    text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    return f"Conteúdo de {screening.url}:\n{text[:SCREENING_SOURCE_MAX_CHARS]}"


def resolve_verdict(
    movie: Movie,
    status: VerdictStatus,
    reasoning: str,
    new_tmdb_id: Optional[int],
    observed_tmdb_ids: Iterable[int],
) -> InspectionOutcome:
    """Applies a verdict, refusing to write a `fixed` tmdb_id the agent
    never actually observed through one of its own tool calls - the agent's
    context includes untrusted scraped text, so "never invent an id" is
    enforced here rather than only asked for in the prompt. A valid `fixed`
    rematches the movie (committing) and captures before/after snapshots."""
    if status == "fixed":
        if new_tmdb_id is None or new_tmdb_id not in set(observed_tmdb_ids):
            logger.warning(
                "Filme %d ('%s') – veredito 'fixed' com tmdb_id=%s que não foi "
                "observado por nenhuma ferramenta desta inspeção; rebaixado para "
                "needs_review",
                movie.id,
                movie.title,
                new_tmdb_id,
            )
            return InspectionOutcome(
                status="needs_review",
                reasoning=(
                    "Veredito 'fixed' com um tmdb_id que não foi observado por "
                    "nenhuma ferramenta nesta inspeção; tratado como revisão "
                    f"manual. Raciocínio original: {reasoning}"
                ),
            )
        before = snapshot(movie)
        apply_rematch(movie, new_tmdb_id)
        after = snapshot(movie)
        return InspectionOutcome(
            status="fixed",
            reasoning=reasoning,
            before_snapshot=before,
            after_snapshot=after,
        )
    return InspectionOutcome(status=status, reasoning=reasoning)


class InspectionRequestError(Exception):
    """A tool was called for a request that cannot be worked on. The message
    is pt-BR and meant for the agent: it should stop, not retry."""


class ScreeningContextData(BaseModel):
    screening_id: int
    cinema_name: str
    description: str


class MovieContext(BaseModel):
    """The movie's title, its current TMDB match and what the cinemas showing
    it published - the same fields as the in-process agent's input."""

    movie_title: str
    tmdb_original_title: Optional[str]
    tmdb_release_year: Optional[int]
    tmdb_original_language: Optional[str]
    tmdb_directors: list[str]
    tmdb_countries: list[str]
    tmdb_genres: list[str]
    screenings: list[ScreeningContextData]


def _get_dispatched_request(request_id: int) -> MovieInspectionRequest:
    request = movie_inspection_requests.get_by_id(request_id)
    if request is None:
        raise InspectionRequestError(f"Pedido de inspeção #{request_id} não existe.")
    if request.status != "dispatched":
        raise InspectionRequestError(
            f"Pedido de inspeção #{request_id} não está mais ativo "
            f"(status: {request.status})."
        )
    return request


def get_movie_context(request_id: int) -> MovieContext:
    movie = _get_dispatched_request(request_id).movie
    return MovieContext(
        movie_title=movie.title,
        tmdb_original_title=movie.original_title,
        tmdb_release_year=movie.release_year,
        tmdb_original_language=movie.original_language,
        tmdb_directors=[d.name for d in movie.directors],
        tmdb_countries=[c.name for c in movie.countries],
        tmdb_genres=[g.name for g in movie.genres],
        screenings=[
            ScreeningContextData(
                screening_id=s.id, cinema_name=s.cinema.name, description=s.description
            )
            for s in movie.screenings
        ],
    )
