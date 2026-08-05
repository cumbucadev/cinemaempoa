"""The movie inspector agent: checks whether a movie's linked TMDB entry
is consistent with what cinemas actually published about it (director,
year, country), fixing confidently-wrong matches and flagging uncertain
ones for manual review. See design spec at
https://github.com/cumbucadev/cinemaempoa/pull/301#issuecomment-5182749958.
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
from google.genai.errors import ClientError
from instructor.core import InstructorRetryException
from pydantic import Field

from flask_backend.db import db_session
from flask_backend.env_config import GEMINI_API_KEY
from flask_backend.models import Movie
from flask_backend.repository import movie_inspections
from flask_backend.repository.movies import get_by_id as get_movie_by_id
from flask_backend.repository.screenings import get_screening_by_id
from flask_backend.service.gemini_models import (
    AllGeminiModelsExhausted,
    call_with_fallback,
)
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


def _run_search_tmdb_candidates(title: str) -> tuple[str, list[int]]:
    """Returns the observation text plus every tmdb id it exposed, so the
    loop can record which ids the agent actually saw (see `inspect_movie`)."""
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


def _run_get_tmdb_details(tmdb_id: int) -> tuple[str, list[int]]:
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
    """One screening's id, cinema name, and scraped description text, given
    to the inspector as evidence about the film actually being shown."""

    screening_id: int = Field(
        ...,
        description="This screening's id, to pass to fetch_screening_source if needed.",
    )
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


def _is_rate_limited(exc: Exception) -> bool:
    if isinstance(exc, InstructorRetryException) and exc.args:
        exc = exc.args[0]
    return isinstance(exc, ClientError) and exc.code == 429


def _build_agent(model_id: str) -> AtomicAgent[OrchestratorInput, OrchestratorDecision]:
    client = instructor.from_provider(f"google/{model_id}", api_key=GEMINI_API_KEY)
    system_prompt_generator = SystemPromptGenerator(
        background=[
            "Você é um inspetor de dados de um portal de cinema.",
            "Sua tarefa é verificar se o filme vinculado no TMDB corresponde ao "
            "filme descrito pelos cinemas que o exibem - filmes com o mesmo "
            "título em português são frequentemente vinculados errado.",
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
            model=model_id,
            system_prompt_generator=system_prompt_generator,
            history=ChatHistory(),
            assistant_role="model",
        )
    )


def _attach_debug_hooks(agent: AtomicAgent, movie: Movie) -> None:
    """Registers atomic-agents' Instructor hooks so every LLM call this
    agent makes is logged: request kwargs, response/token usage, and
    errors. INFO carries short summaries; DEBUG carries raw prompt/response
    content, which may include untrusted scraped text (see
    `_run_fetch_screening_source`) and so is gated behind --verbose."""

    def on_completion_kwargs(**kwargs):
        messages = kwargs.get("messages") or []
        logger.info(
            "Filme %d ('%s') – chamada LLM: model=%s, mensagens=%d",
            movie.id,
            movie.title,
            kwargs.get("model"),
            len(messages),
        )
        logger.debug(
            "Filme %d ('%s') – mensagens enviadas: %s",
            movie.id,
            movie.title,
            [
                {
                    "role": m.get("role"),
                    "content": str(m.get("content"))[:2000],
                }
                for m in messages
            ],
        )

    def on_completion_response(response):
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            logger.info(
                "Filme %d ('%s') – resposta LLM recebida (sem dados de uso de tokens)",
                movie.id,
                movie.title,
            )
        else:
            logger.info(
                "Filme %d ('%s') – resposta LLM: tokens(prompt=%s, resposta=%s, total=%s)",
                movie.id,
                movie.title,
                getattr(usage, "prompt_token_count", None),
                getattr(usage, "candidates_token_count", None),
                getattr(usage, "total_token_count", None),
            )
        logger.debug(
            "Filme %d ('%s') – resposta LLM bruta: %s",
            movie.id,
            movie.title,
            repr(response)[:2000],
        )

    def on_completion_error(error):
        logger.warning(
            "Filme %d ('%s') – erro na chamada LLM: %s: %s",
            movie.id,
            movie.title,
            type(error).__name__,
            error,
        )

    def on_completion_last_attempt(error):
        logger.warning(
            "Filme %d ('%s') – última tentativa de chamada LLM falhou: %s: %s",
            movie.id,
            movie.title,
            type(error).__name__,
            error,
        )

    def on_parse_error(error):
        logger.warning(
            "Filme %d ('%s') – erro ao validar resposta do LLM: %s: %s",
            movie.id,
            movie.title,
            type(error).__name__,
            error,
        )

    agent.register_hook("completion:kwargs", on_completion_kwargs)
    agent.register_hook("completion:response", on_completion_response)
    agent.register_hook("completion:error", on_completion_error)
    agent.register_hook("completion:last_attempt", on_completion_last_attempt)
    agent.register_hook("parse:error", on_parse_error)


def _dispatch_tool(
    decision: OrchestratorDecision, allowed_screening_ids: set
) -> tuple[str, list[int]]:
    if decision.action == "search_tmdb_candidates":
        if not decision.search_title:
            return "Ação 'search_tmdb_candidates' sem 'search_title'.", []
        return _run_search_tmdb_candidates(decision.search_title)
    if decision.action == "get_tmdb_details":
        if decision.tmdb_id is None:
            return "Ação 'get_tmdb_details' sem 'tmdb_id'.", []
        return _run_get_tmdb_details(decision.tmdb_id)
    if decision.action == "fetch_screening_source":
        if decision.screening_id is None:
            return "Ação 'fetch_screening_source' sem 'screening_id'.", []
        if decision.screening_id not in allowed_screening_ids:
            return (
                f"Sessão #{decision.screening_id} não pertence ao filme em inspeção.",
                [],
            )
        return _run_fetch_screening_source(decision.screening_id), []
    return f"Ação desconhecida: {decision.action}", []


def _apply_verdict(
    movie: Movie, verdict: InspectionVerdict, observed_tmdb_ids: set
) -> InspectionOutcome:
    """Applies a verdict, refusing to write a `fixed` tmdb_id the agent
    never actually observed through one of its own tool calls - the agent's
    context includes untrusted scraped text, so "never invent an id" is
    enforced here rather than only asked for in the prompt."""
    if verdict.status == "fixed":
        if verdict.new_tmdb_id is None or verdict.new_tmdb_id not in observed_tmdb_ids:
            logger.warning(
                "Filme %d ('%s') – veredito 'fixed' com tmdb_id=%s que não foi "
                "observado por nenhuma ferramenta desta inspeção; rebaixado para "
                "needs_review",
                movie.id,
                movie.title,
                verdict.new_tmdb_id,
            )
            return InspectionOutcome(
                status="needs_review",
                reasoning=(
                    "Veredito 'fixed' com um tmdb_id que não foi observado por "
                    "nenhuma ferramenta nesta inspeção; tratado como revisão "
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
    movie's TMDB link has already been updated and committed. If the
    current model is rate-limited, retries the whole inspection with the
    next model in GEMINI_MODEL_PRIORITY, starting from a clean slate rather
    than resuming a partial tool-calling loop."""
    allowed_screening_ids = {s.id for s in movie.screenings}

    def call(model_id):
        return _run_inspection_loop(model_id, movie, allowed_screening_ids)

    return call_with_fallback(call, _is_rate_limited)


def _run_inspection_loop(
    model_id: str, movie: Movie, allowed_screening_ids: set
) -> InspectionOutcome:
    agent_input = OrchestratorInput(
        movie_title=movie.title,
        tmdb_original_title=movie.original_title,
        tmdb_release_year=movie.release_year,
        tmdb_original_language=movie.original_language,
        tmdb_directors=[d.name for d in movie.directors],
        tmdb_countries=[c.name for c in movie.countries],
        tmdb_genres=[g.name for g in movie.genres],
        screenings=[
            ScreeningContext(
                screening_id=s.id, cinema_name=s.cinema.name, description=s.description
            )
            for s in movie.screenings
        ],
    )
    observed_tmdb_ids: set = set()
    agent = _build_agent(model_id)
    _attach_debug_hooks(agent, movie)

    for turn in range(1, MAX_TOOL_CALLS + 1):
        decision = agent.run(agent_input)
        logger.debug(
            "Filme %d ('%s') – turno %d/%d: ação=%s",
            movie.id,
            movie.title,
            turn,
            MAX_TOOL_CALLS,
            decision.action,
        )

        if decision.action == "conclude":
            if decision.verdict is None:
                agent_input.observations.append(
                    "Ação 'conclude' enviada sem veredito; forneça o veredito."
                )
                continue
            return _apply_verdict(movie, decision.verdict, observed_tmdb_ids)

        observation, ids = _dispatch_tool(decision, allowed_screening_ids)
        logger.debug(
            "Filme %d ('%s') – turno %d: tool=%s observação=%s",
            movie.id,
            movie.title,
            turn,
            decision.action,
            observation[:200],
        )
        observed_tmdb_ids.update(ids)
        agent_input.observations.append(observation)

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
    if GEMINI_API_KEY is None:
        raise ValueError(
            "GEMINI_API_KEY não configurado; não é possível executar inspect-movies."
        )

    result = PipelineResult()
    movies = movie_inspections.get_movies_needing_inspection()
    if limit is not None:
        movies = movies[:limit]

    for movie in movies:
        # Captured before inspecting: a "fixed" outcome mutates and commits
        # movie.tmdb_id in place, and the audit row must record the id that
        # was actually checked, not the replacement.
        checked_tmdb_id = movie.tmdb_id
        try:
            outcome = inspect_movie(movie)
        except AllGeminiModelsExhausted as exc:
            logger.warning(
                "Filme %d ('%s') – todos os modelos Gemini esgotados; "
                "interrompendo o restante do lote",
                movie.id,
                movie.title,
            )
            movie_inspections.create(
                movie_id=movie.id,
                status="error",
                reasoning=str(exc)[:500],
                checked_tmdb_id=checked_tmdb_id,
                pipeline_run_id=pipeline_run_id,
            )
            result.errors += 1
            result.processed += 1
            break
        except Exception as exc:
            logger.warning(
                "Filme %d ('%s') – erro na inspeção: %s", movie.id, movie.title, exc
            )
            movie_inspections.create(
                movie_id=movie.id,
                status="error",
                reasoning=str(exc)[:500],
                checked_tmdb_id=checked_tmdb_id,
                pipeline_run_id=pipeline_run_id,
            )
            result.errors += 1
            result.processed += 1
            continue

        movie_inspections.create(
            movie_id=movie.id,
            status=outcome.status,
            reasoning=outcome.reasoning,
            checked_tmdb_id=checked_tmdb_id,
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
    """Undoes one `fixed` inspection by re-applying its `previous_snapshot`,
    appending a `reverted` row rather than editing history. Refuses stale
    rows: if a newer fix has since moved the movie on, reverting this one
    would silently clobber that newer fix."""
    inspection = movie_inspections.get_by_id(inspection_id)
    if inspection is None or inspection.status != "fixed":
        raise ValueError(f"Inspeção #{inspection_id} não pode ser revertida.")

    movie = get_movie_by_id(inspection.movie_id)
    new_snapshot = (
        json.loads(inspection.new_snapshot) if inspection.new_snapshot else None
    )
    if new_snapshot is None or movie.tmdb_id != new_snapshot.get("tmdb_id"):
        logger.warning(
            "Inspeção #%d – revert recusado: filme %d não reflete mais o "
            "snapshot desta inspeção (uma correção mais recente já foi aplicada)",
            inspection_id,
            movie.id,
        )
        raise ValueError(
            f"Inspeção #{inspection_id} não reflete mais o estado atual do "
            "filme (uma correção mais recente já foi aplicada); não pode ser "
            "revertida."
        )

    previous = json.loads(inspection.previous_snapshot)
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
