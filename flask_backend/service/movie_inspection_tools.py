"""The movie inspector's tools and verdict rules, independent of whichever
agent loop drives them: a movie's TMDB snapshot, the rematch, the three
observation tools (TMDB candidate search, TMDB details, screening source) and
applying a verdict given the tmdb ids the agent actually observed.

Observation tools never raise on TMDB/network failures: the error comes back
as observation text, so the agent can keep reasoning or conclude
`needs_review`.

The per-request layer (`get_movie_context`, ..., `apply_verdict`) is what the MCP server in
flask_backend/mcp_server.py exposes: each function takes a `request_id` and
raises InspectionRequestError, with a pt-BR message, when that request
cannot be worked on.
"""

import json
import logging
from dataclasses import dataclass
from typing import Callable, Iterable, Literal, Optional, get_args

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel

from flask_backend.db import db_session
from flask_backend.models import Movie, MovieInspectionRequest
from flask_backend.repository import movie_inspection_requests, movie_inspections
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


def _with_original_reasoning(message: str, reasoning: str) -> str:
    """`message`, explaining why the agent's verdict was not recorded as
    given, followed by the agent's own reasoning."""
    return f"{message} Raciocínio original: {reasoning}"


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
    rematch: Callable[[Movie, int], None] = apply_rematch,
) -> InspectionOutcome:
    """Applies a verdict, refusing to write a `fixed` tmdb_id the agent
    never actually observed through one of its own tool calls - the agent's
    context includes untrusted scraped text, so "never invent an id" is
    enforced here rather than only asked for in the prompt. A valid `fixed`
    rematches the movie through `rematch` (by default `apply_rematch`,
    which commits) and captures before/after snapshots."""
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
                reasoning=_with_original_reasoning(
                    "Veredito 'fixed' com um tmdb_id que não foi observado por "
                    "nenhuma ferramenta nesta inspeção; tratado como revisão "
                    "manual.",
                    reasoning,
                ),
            )
        before = snapshot(movie)
        rematch(movie, new_tmdb_id)
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
    it published - the in-process agent's input fields, plus the match's
    `tmdb_id` so a remote agent never mistakes the request or movie id for
    it."""

    movie_title: str
    tmdb_id: Optional[int]
    tmdb_original_title: Optional[str]
    tmdb_release_year: Optional[int]
    tmdb_original_language: Optional[str]
    tmdb_directors: list[str]
    tmdb_countries: list[str]
    tmdb_genres: list[str]
    screenings: list[ScreeningContextData]


def _check_dispatched(
    request: Optional[MovieInspectionRequest], request_id: int
) -> MovieInspectionRequest:
    if request is None:
        raise InspectionRequestError(f"Pedido de inspeção #{request_id} não existe.")
    if request.status != "dispatched":
        raise InspectionRequestError(
            f"Pedido de inspeção #{request_id} não está mais ativo "
            f"(status: {request.status})."
        )
    return request


def _get_dispatched_request(request_id: int) -> MovieInspectionRequest:
    return _check_dispatched(
        movie_inspection_requests.get_by_id(request_id), request_id
    )


def build_movie_context(movie: Movie) -> MovieContext:
    return MovieContext(
        movie_title=movie.title,
        tmdb_id=movie.tmdb_id,
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


def get_movie_context(request_id: int) -> MovieContext:
    return build_movie_context(_get_dispatched_request(request_id).movie)


def search_tmdb_candidates(request_id: int, title: str) -> str:
    """Searches TMDB for `title` and records every id the result exposed as
    observed by the request."""
    request = _get_dispatched_request(request_id)
    observation, ids = run_search_tmdb_candidates(title)
    movie_inspection_requests.add_observed_tmdb_ids(request.id, ids)
    return observation


def get_tmdb_details(request_id: int, tmdb_id: int) -> str:
    """Looks up `tmdb_id` on TMDB and, when it was found, records it as
    observed by the request."""
    request = _get_dispatched_request(request_id)
    observation, ids = run_get_tmdb_details(tmdb_id)
    movie_inspection_requests.add_observed_tmdb_ids(request.id, ids)
    return observation


def fetch_screening_source(request_id: int, screening_id: int) -> str:
    """Fetches the source page of one of the request's movie's screenings.
    Refuses a screening of any other movie, so another movie's page cannot
    pass as evidence."""
    request = _get_dispatched_request(request_id)
    screening = get_screening_by_id(screening_id)
    if screening is None or screening.movie_id != request.movie_id:
        raise InspectionRequestError(
            f"Sessão #{screening_id} não pertence ao filme do pedido de "
            f"inspeção #{request_id}."
        )
    return run_fetch_screening_source(screening_id)


VERDICT_STATUSES = get_args(VerdictStatus)


class VerdictResult(BaseModel):
    """What apply_verdict recorded: the MovieInspection row it wrote, whose
    status may differ from the one asked for (`fixed` downgraded to
    `needs_review`, or `error`)."""

    inspection_id: int
    status: str
    reasoning: str


def _verdict_result(request: MovieInspectionRequest) -> VerdictResult:
    inspection = request.inspection
    if inspection is None:
        raise InspectionRequestError(
            f"Pedido de inspeção #{request.id} já foi encerrado sem veredito "
            "registrado."
        )
    return VerdictResult(
        inspection_id=inspection.id,
        status=inspection.status,
        reasoning=inspection.reasoning,
    )


def _prefetched_rematch(
    request: MovieInspectionRequest, status: str, new_tmdb_id: Optional[int]
) -> Callable[[Movie, int], None]:
    """A rematch that links the movie to TMDB details fetched now, before
    apply_verdict takes the request's write lock, so no HTTP call runs while
    other writers wait on SQLite. Does not commit, and raises the TMDB
    failure, if there was one, when applied. Fetches only for a `fixed`
    that looks applicable; if the locked re-read makes it applicable after
    all (a race with an observation tool), it fetches then."""
    details, failure = None, None
    if (
        status == "fixed"
        and new_tmdb_id in request.observed_tmdb_id_list
        and not request.movie_link_changed
    ):
        try:
            details = TMDBClient().get_movie_details(new_tmdb_id)
        except requests.RequestException as exc:
            failure = exc

    def rematch(movie: Movie, tmdb_id: int) -> None:
        if failure is not None:
            raise failure
        tmdb_details = (
            details if details is not None else TMDBClient().get_movie_details(tmdb_id)
        )
        apply_tmdb_details(movie, tmdb_id, tmdb_details)
        db_session.add(movie)

    return rematch


def _decide_outcome(
    request: MovieInspectionRequest,
    status: VerdictStatus,
    reasoning: str,
    new_tmdb_id: Optional[int],
    rematch: Callable[[Movie, int], None],
) -> InspectionOutcome:
    """Applies the verdict to the request's movie without committing, or
    turns it into an `error` outcome when a `fixed` cannot be applied: the
    movie's link changed since the request was created, or TMDB failed
    during the rematch."""
    movie = request.movie
    if status == "fixed" and request.movie_link_changed:
        logger.warning(
            "Pedido de inspeção #%d – vínculo do filme %d mudou de %s para %s; "
            "veredito 'fixed' não aplicado",
            request.id,
            movie.id,
            request.checked_tmdb_id,
            movie.tmdb_id,
        )
        return InspectionOutcome(
            status="error",
            reasoning=_with_original_reasoning(
                f"O vínculo TMDB do filme mudou desde a criação do pedido (de "
                f"{request.checked_tmdb_id} para {movie.tmdb_id}); veredito "
                "'fixed' não aplicado.",
                reasoning,
            ),
        )
    try:
        return resolve_verdict(
            movie,
            status,
            reasoning,
            new_tmdb_id,
            request.observed_tmdb_id_list,
            rematch=rematch,
        )
    except requests.RequestException as exc:
        return InspectionOutcome(
            status="error",
            reasoning=_with_original_reasoning(
                f"Erro do TMDB ao aplicar o tmdb_id={new_tmdb_id}: {exc}.", reasoning
            ),
        )


def _snapshot_json(snapshot_data: Optional[dict]) -> Optional[str]:
    return json.dumps(snapshot_data) if snapshot_data else None


def _close_with_verdict(
    request: MovieInspectionRequest,
    status: VerdictStatus,
    reasoning: str,
    new_tmdb_id: Optional[int],
    rematch: Callable[[Movie, int], None],
) -> VerdictResult:
    outcome = _decide_outcome(request, status, reasoning, new_tmdb_id, rematch)
    inspection = movie_inspections.build(
        request.movie_id,
        outcome.status,
        outcome.reasoning,
        checked_tmdb_id=request.checked_tmdb_id,
        previous_snapshot=_snapshot_json(outcome.before_snapshot),
        new_snapshot=_snapshot_json(outcome.after_snapshot),
        pipeline_run_id=request.pipeline_run_id,
    )
    return _verdict_result(movie_inspection_requests.close_as_done(request, inspection))


def apply_verdict(
    request_id: int,
    status: str,
    reasoning: str,
    new_tmdb_id: Optional[int],
) -> VerdictResult:
    """Closes the request with the agent's verdict: applies it (see
    `resolve_verdict`), records exactly one MovieInspection with the
    request's checked_tmdb_id and pipeline_run_id, and marks the request
    `done`, all in one commit under the request's write lock. A request
    already `done` answers with the row it recorded and writes nothing, so a
    retried call cannot double-apply."""
    if status not in VERDICT_STATUSES:
        raise InspectionRequestError(
            f"Status '{status}' inválido: use {', '.join(VERDICT_STATUSES)}."
        )
    request = movie_inspection_requests.get_by_id(request_id)
    if request is not None and request.status == "done":
        return _verdict_result(request)
    rematch = _prefetched_rematch(
        _check_dispatched(request, request_id), status, new_tmdb_id
    )
    request = movie_inspection_requests.get_for_update(request_id)
    try:
        # Re-checked under the lock: a concurrent call may have closed it.
        if request is not None and request.status == "done":
            result = _verdict_result(request)
            db_session.commit()
            return result
        _check_dispatched(request, request_id)
        return _close_with_verdict(request, status, reasoning, new_tmdb_id, rematch)
    except Exception:
        db_session.rollback()
        raise
