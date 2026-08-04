"""The movie inspector agent: checks whether a movie's linked TMDB entry
is consistent with what cinemas actually published about it (director,
year, country), fixing confidently-wrong matches and flagging uncertain
ones for manual review. See docs/superpowers/specs/2026-08-04-cinema-inspector-agent-design.md.
"""

import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

from flask_backend.db import db_session
from flask_backend.models import Movie
from flask_backend.repository.screenings import get_screening_by_id
from flask_backend.service.movie_metadata_pipeline import (
    apply_tmdb_details,
    clear_tmdb_metadata,
)
from flask_backend.service.tmdb import TMDBClient

logger = logging.getLogger(__name__)


def _snapshot(movie: Movie) -> dict:
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


def _apply_rematch(movie: Movie, tmdb_id: Optional[int]) -> None:
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


def _run_search_tmdb_candidates(title: str) -> str:
    try:
        results = TMDBClient().search_movies(title)
    except requests.RequestException as exc:
        return f"Erro ao buscar '{title}' no TMDB: {exc}"
    if not results:
        return f"Nenhum resultado no TMDB para '{title}'."
    lines = [
        "- tmdb_id={} título='{}' ano={}".format(
            r["id"], r.get("title"), (r.get("release_date") or "????")[:4]
        )
        for r in results
    ]
    return "Candidatos no TMDB para '{}':\n{}".format(title, "\n".join(lines))


def _run_get_tmdb_details(tmdb_id: int) -> str:
    try:
        details = TMDBClient().get_movie_details(tmdb_id)
    except requests.RequestException as exc:
        return f"Erro ao buscar detalhes do TMDB id={tmdb_id}: {exc}"
    directors = ", ".join(d["name"] for d in details["directors"]) or "desconhecido"
    countries = ", ".join(c["name"] for c in details["countries"]) or "desconhecido"
    return (
        f"Detalhes do TMDB id={tmdb_id}: título original="
        f"'{details['original_title']}', ano={details['release_year']}, "
        f"diretor(es)={directors}, país(es)={countries}"
    )


def _run_fetch_screening_source(screening_id: int) -> str:
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
    return f"Conteúdo de {screening.url}:\n{text[:4000]}"
