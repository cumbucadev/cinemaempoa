"""The movie inspector agent: checks whether a movie's linked TMDB entry
is consistent with what cinemas actually published about it (director,
year, country), fixing confidently-wrong matches and flagging uncertain
ones for manual review. See docs/superpowers/specs/2026-08-04-cinema-inspector-agent-design.md.
"""

import json
import logging
from dataclasses import dataclass
from typing import List, Literal, Optional

import instructor
import requests
from atomic_agents import AgentConfig, AtomicAgent, BaseIOSchema
from atomic_agents.context import ChatHistory, SystemPromptGenerator
from bs4 import BeautifulSoup
from pydantic import Field

from flask_backend.db import db_session
from flask_backend.env_config import GEMINI_API_KEY
from flask_backend.models import Movie
from flask_backend.repository.screenings import get_screening_by_id
from flask_backend.repository import movie_inspections
from flask_backend.repository.movies import get_by_id as get_movie_by_id
from flask_backend.service.gemini_api import Gemini
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


MAX_TOOL_CALLS = 4


class ScreeningContext(BaseIOSchema):
    """One screening's cinema name and scraped description text, given to
    the inspector as evidence about the film actually being shown."""

    cinema_name: str = Field(
        ..., description="Name of the cinema showing this screening."
    )
    description: str = Field(
        ..., description="The scraped, free-text description of the screening."
    )


class OrchestratorInput(BaseIOSchema):
    """Everything the movie inspector knows so far about one movie: its
    current TMDB match, what the cinemas showing it actually published,
    and any tool results gathered in earlier steps of this inspection."""

    movie_title: str = Field(..., description="The movie's title in our database.")
    tmdb_original_title: Optional[str] = Field(
        None, description="Original title from the current TMDB match."
    )
    tmdb_release_year: Optional[int] = Field(
        None, description="Release year from the current TMDB match."
    )
    tmdb_original_language: Optional[str] = Field(
        None, description="ISO 639-1 original language from the current TMDB match."
    )
    tmdb_directors: List[str] = Field(
        default_factory=list, description="Director names from the current TMDB match."
    )
    tmdb_countries: List[str] = Field(
        default_factory=list,
        description="Production countries from the current TMDB match.",
    )
    tmdb_genres: List[str] = Field(
        default_factory=list, description="Genres from the current TMDB match."
    )
    screenings: List[ScreeningContext] = Field(
        default_factory=list,
        description="Cinema-published descriptions for this movie.",
    )
    observations: List[str] = Field(
        default_factory=list,
        description="Results of tools called in earlier steps of this same inspection, oldest first.",
    )


class InspectionVerdict(BaseIOSchema):
    """The inspector's final answer once it is done gathering evidence."""

    status: Literal["consistent", "fixed", "needs_review"] = Field(
        ...,
        description="'consistent' if the TMDB match agrees with the cinema descriptions, 'fixed' if a better match was positively identified, 'needs_review' if uncertain.",
    )
    reasoning: str = Field(
        ..., description="Explanation citing the specific evidence found."
    )
    new_tmdb_id: Optional[int] = Field(
        None,
        description="Required when status is 'fixed': the TMDB id positively identified via the search/details tools.",
    )


class OrchestratorDecision(BaseIOSchema):
    """The inspector's next move: either call exactly one tool, or
    conclude the inspection with a final verdict."""

    action: Literal[
        "search_tmdb_candidates",
        "get_tmdb_details",
        "fetch_screening_source",
        "conclude",
    ] = Field(..., description="Which tool to call next, or 'conclude' to finish.")
    search_title: Optional[str] = Field(
        None,
        description="Title to search for. Required when action is 'search_tmdb_candidates'.",
    )
    tmdb_id: Optional[int] = Field(
        None,
        description="TMDB id to fetch details for. Required when action is 'get_tmdb_details'.",
    )
    screening_id: Optional[int] = Field(
        None,
        description="Screening id to re-fetch. Required when action is 'fetch_screening_source'.",
    )
    verdict: Optional[InspectionVerdict] = Field(
        None, description="Final verdict. Required when action is 'conclude'."
    )


@dataclass
class InspectionOutcome:
    status: str
    reasoning: str
    before_snapshot: Optional[dict] = None
    after_snapshot: Optional[dict] = None


def _build_agent() -> AtomicAgent[OrchestratorInput, OrchestratorDecision]:
    client = instructor.from_provider(f"google/{Gemini.MODEL}", api_key=GEMINI_API_KEY)
    system_prompt_generator = SystemPromptGenerator(
        background=[
            "Você é um inspetor de dados de um portal de cinema.",
            "Sua tarefa é verificar se o filme vinculado no TMDB corresponde ao "
            "filme descrito pelos cinemas que o exibem - filmes com o mesmo "
            "título em português são frequentemente vinculado errado.",
        ],
        steps=[
            "Compare diretor, ano, país e gênero do TMDB com o texto das sessões.",
            "Se algo não bate, use as ferramentas disponíveis para investigar antes de concluir.",
            "Só conclua 'fixed' depois de identificar um tmdb_id correto usando "
            "search_tmdb_candidates/get_tmdb_details - nunca invente um id.",
            "Se não tiver certeza, conclua 'needs_review' em vez de arriscar um palpite.",
        ],
        output_instructions=[
            "Responda apenas com a próxima ação: um dos tools disponíveis, ou "
            "'conclude' acompanhado do veredito final.",
        ],
    )
    return AtomicAgent[OrchestratorInput, OrchestratorDecision](
        config=AgentConfig(
            client=client,
            model=Gemini.MODEL,
            system_prompt_generator=system_prompt_generator,
            history=ChatHistory(),
        )
    )


def _dispatch_tool(decision: OrchestratorDecision) -> str:
    if decision.action == "search_tmdb_candidates":
        if not decision.search_title:
            return "Ação 'search_tmdb_candidates' sem 'search_title'."
        return _run_search_tmdb_candidates(decision.search_title)
    if decision.action == "get_tmdb_details":
        if decision.tmdb_id is None:
            return "Ação 'get_tmdb_details' sem 'tmdb_id'."
        return _run_get_tmdb_details(decision.tmdb_id)
    if decision.action == "fetch_screening_source":
        if decision.screening_id is None:
            return "Ação 'fetch_screening_source' sem 'screening_id'."
        return _run_fetch_screening_source(decision.screening_id)
    return f"Ação desconhecida: {decision.action}"


def _apply_verdict(movie: Movie, verdict: InspectionVerdict) -> InspectionOutcome:
    if verdict.status == "fixed":
        if verdict.new_tmdb_id is None:
            return InspectionOutcome(
                status="needs_review",
                reasoning=(
                    "Veredito 'fixed' sem new_tmdb_id; tratado como revisão "
                    f"manual. Raciocínio original: {verdict.reasoning}"
                ),
            )
        before = _snapshot(movie)
        _apply_rematch(movie, verdict.new_tmdb_id)
        after = _snapshot(movie)
        return InspectionOutcome(
            status="fixed",
            reasoning=verdict.reasoning,
            before_snapshot=before,
            after_snapshot=after,
        )
    return InspectionOutcome(status=verdict.status, reasoning=verdict.reasoning)


def inspect_movie(movie: Movie) -> InspectionOutcome:
    """Runs the orchestrator's bounded tool-calling loop for one movie and
    returns the resulting outcome. If `verdict.status == "fixed"`, the
    movie's TMDB link has already been updated and committed."""
    agent_input = OrchestratorInput(
        movie_title=movie.title,
        tmdb_original_title=movie.original_title,
        tmdb_release_year=movie.release_year,
        tmdb_original_language=movie.original_language,
        tmdb_directors=[d.name for d in movie.directors],
        tmdb_countries=[c.name for c in movie.countries],
        tmdb_genres=[g.name for g in movie.genres],
        screenings=[
            ScreeningContext(cinema_name=s.cinema.name, description=s.description)
            for s in movie.screenings
        ],
    )
    agent = _build_agent()

    for _ in range(MAX_TOOL_CALLS):
        decision = agent.run(agent_input)

        if decision.action == "conclude":
            if decision.verdict is None:
                agent_input.observations.append(
                    "Ação 'conclude' enviada sem veredito; forneça o veredito."
                )
                continue
            return _apply_verdict(movie, decision.verdict)

        agent_input.observations.append(_dispatch_tool(decision))

    logger.info(
        "Filme %d ('%s') – inspeção inconclusiva após %d chamadas de ferramenta",
        movie.id,
        movie.title,
        MAX_TOOL_CALLS,
    )
    return InspectionOutcome(
        status="needs_review",
        reasoning=f"Inspeção inconclusiva após {MAX_TOOL_CALLS} chamadas de ferramenta.",
    )


@dataclass
class PipelineResult:
    processed: int = 0
    consistent: int = 0
    fixed: int = 0
    needs_review: int = 0
    errors: int = 0


def run_pipeline(
    limit: Optional[int] = None, pipeline_run_id: Optional[int] = None
) -> PipelineResult:
    result = PipelineResult()
    movies = movie_inspections.get_movies_needing_inspection()
    if limit is not None:
        movies = movies[:limit]

    for movie in movies:
        try:
            outcome = inspect_movie(movie)
        except Exception as exc:
            logger.warning(
                "Filme %d ('%s') – erro na inspeção: %s", movie.id, movie.title, exc
            )
            movie_inspections.create(
                movie_id=movie.id,
                status="error",
                reasoning=str(exc)[:500],
                checked_tmdb_id=movie.tmdb_id,
                pipeline_run_id=pipeline_run_id,
            )
            result.errors += 1
            result.processed += 1
            continue

        movie_inspections.create(
            movie_id=movie.id,
            status=outcome.status,
            reasoning=outcome.reasoning,
            checked_tmdb_id=movie.tmdb_id,
            previous_snapshot=json.dumps(outcome.before_snapshot)
            if outcome.before_snapshot
            else None,
            new_snapshot=json.dumps(outcome.after_snapshot)
            if outcome.after_snapshot
            else None,
            pipeline_run_id=pipeline_run_id,
        )
        if outcome.status == "consistent":
            result.consistent += 1
        elif outcome.status == "fixed":
            result.fixed += 1
        elif outcome.status == "needs_review":
            result.needs_review += 1
        result.processed += 1

    return result


def revert_inspection(inspection_id: int):
    inspection = movie_inspections.get_by_id(inspection_id)
    if inspection is None or inspection.status != "fixed":
        raise ValueError(f"Inspeção #{inspection_id} não pode ser revertida.")

    previous = json.loads(inspection.previous_snapshot)
    movie = get_movie_by_id(inspection.movie_id)
    before = _snapshot(movie)
    _apply_rematch(movie, previous.get("tmdb_id"))
    after = _snapshot(movie)

    return movie_inspections.create(
        movie_id=movie.id,
        status="reverted",
        reasoning=f"Revertido manualmente para o estado anterior à inspeção #{inspection_id}.",
        checked_tmdb_id=movie.tmdb_id,
        previous_snapshot=json.dumps(before),
        new_snapshot=json.dumps(after),
    )
