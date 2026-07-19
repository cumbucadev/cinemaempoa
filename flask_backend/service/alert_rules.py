"""Deterministic rules the alert pipeline (flask_backend/service/alert_pipeline.py)
evaluates to detect "interesting movies" worth a social media post (issue #209):
new movies, single-screening runs, "sessão comentada", "mostra" strands,
director debuts/returns, new genre combinations, and sequels/franchises.

Each rule is a pure function: it queries the repository layer but never
writes anything - orchestration and persistence live in alert_pipeline.py.

To add a new rule: write an `evaluate_*(subject) -> Optional[AlertCandidate]`
function and append it to CORE_SCREENING_RULES (screening-scoped) or
METADATA_MOVIE_RULES (movie-scoped, run once TMDB metadata has arrived).
"""

from dataclasses import dataclass, field
from typing import List, Optional

from flask_backend.models import Movie, Screening
from flask_backend.repository.movies import (
    get_earlier_genre_id_sets,
    get_earlier_movies_with_collection,
    get_earlier_movies_with_director,
)
from flask_backend.service.title_cleaning import RULE_CATEGORIES

# title_cleaning.TitleCleaningRule names that indicate a curated
# strand/festival ("Mostra") rather than plain scraping noise.
MOSTRA_RULE_NAMES = {
    "fantaspoa",
    "sessao_strand",
    "projeto_raros",
    "cinelimite",
    "semana_cinema_gaucho",
    "mostra_classicos_franceses",
    "cine_esquema_novo",
    "cen_abbrev",
    "malkovich_3x",
}

# title_cleaning.TitleCleaningRule names that indicate a post-screening
# discussion ("Sessão comentada").
SESSAO_COMENTADA_RULE_NAMES = {"sessao_comentada_suffix"}


@dataclass(frozen=True)
class AlertCandidate:
    rule_name: str
    movie_id: int
    screening_id: Optional[int]
    dedup_key: str
    drafted_text: str
    context: dict = field(default_factory=dict)


def _matched_rule_names(screening: Screening) -> set:
    return set((screening.title_cleaning_rules or "").split(",")) - {""}


# --- Core (screening-scoped) rules ---------------------------------------


def evaluate_new_movie(screening: Screening) -> Optional[AlertCandidate]:
    """Fires once, for the movie's first-ever screening entry (earliest
    created_at among screening.movie.screenings)."""
    movie = screening.movie
    earliest = min(movie.screenings, key=lambda s: (s.created_at, s.id))
    if earliest.id != screening.id:
        return None
    return AlertCandidate(
        rule_name="new_movie",
        movie_id=movie.id,
        screening_id=screening.id,
        dedup_key=f"new_movie:{movie.id}",
        drafted_text=f'🎬 Filme novo na programação: "{movie.title}"!',
        context={"movie_title": movie.title},
    )


def evaluate_single_screening(screening: Screening) -> Optional[AlertCandidate]:
    """Fires when a screening has exactly one scheduled date. Evaluated
    once, at first pickup - not retracted if more dates are appended
    later."""
    if len(screening.dates) != 1:
        return None
    movie = screening.movie
    screening_date = screening.dates[0]
    return AlertCandidate(
        rule_name="single_screening",
        movie_id=movie.id,
        screening_id=screening.id,
        dedup_key=f"single_screening:{screening.id}",
        drafted_text=(
            f'⏳ Sessão única: "{movie.title}" tem apenas uma exibição marcada '
            f"({screening_date.date})."
        ),
        context={"movie_title": movie.title, "date": str(screening_date.date)},
    )


def evaluate_sessao_comentada(screening: Screening) -> Optional[AlertCandidate]:
    matched = _matched_rule_names(screening) & SESSAO_COMENTADA_RULE_NAMES
    if not matched:
        return None
    movie = screening.movie
    return AlertCandidate(
        rule_name="sessao_comentada",
        movie_id=movie.id,
        screening_id=screening.id,
        dedup_key=f"sessao_comentada:{screening.id}",
        drafted_text=f'💬 Sessão comentada: "{movie.title}" terá um bate-papo após a exibição.',
        context={"movie_title": movie.title, "matched_rules": sorted(matched)},
    )


def evaluate_mostra(screening: Screening) -> Optional[AlertCandidate]:
    matched = _matched_rule_names(screening) & MOSTRA_RULE_NAMES
    if not matched:
        return None
    movie = screening.movie
    strand_label = RULE_CATEGORIES.get(sorted(matched)[0], "")
    return AlertCandidate(
        rule_name="mostra",
        movie_id=movie.id,
        screening_id=screening.id,
        dedup_key=f"mostra:{screening.id}",
        drafted_text=(
            f'🎪 Mostra: "{movie.title}" faz parte de uma mostra/festival ({strand_label}).'
        ),
        context={"movie_title": movie.title, "matched_rules": sorted(matched)},
    )


CORE_SCREENING_RULES = [
    evaluate_new_movie,
    evaluate_single_screening,
    evaluate_sessao_comentada,
    evaluate_mostra,
]


# --- Metadata-dependent (movie-scoped) rules ------------------------------


def evaluate_director_debut(movie: Movie) -> Optional[AlertCandidate]:
    debuting = [
        director
        for director in movie.directors
        if not get_earlier_movies_with_director(
            director.id, before=movie.created_at, exclude_movie_id=movie.id
        )
    ]
    if not debuting:
        return None
    names = ", ".join(d.name for d in debuting)
    return AlertCandidate(
        rule_name="director_debut",
        movie_id=movie.id,
        screening_id=None,
        dedup_key=f"director_debut:{movie.id}",
        drafted_text=(
            f'🌟 Estreia na nossa programação: {names}, diretor(a) de "{movie.title}".'
        ),
        context={"movie_title": movie.title, "directors": names},
    )


def evaluate_returning_director(movie: Movie) -> Optional[AlertCandidate]:
    returning: List[str] = []
    earlier_titles: List[str] = []
    for director in movie.directors:
        earlier_movies = get_earlier_movies_with_director(
            director.id, before=movie.created_at, exclude_movie_id=movie.id
        )
        if earlier_movies:
            returning.append(director.name)
            earlier_titles.extend(m.title for m in earlier_movies[:3])
    if not returning:
        return None
    names = ", ".join(returning)
    titles = ", ".join(dict.fromkeys(earlier_titles))
    return AlertCandidate(
        rule_name="returning_director",
        movie_id=movie.id,
        screening_id=None,
        dedup_key=f"returning_director:{movie.id}",
        drafted_text=(
            f'🔁 {names} está de volta com "{movie.title}" - já exibimos: {titles}.'
        ),
        context={
            "movie_title": movie.title,
            "directors": names,
            "earlier_titles": titles,
        },
    )


def evaluate_new_genre_combination(movie: Movie) -> Optional[AlertCandidate]:
    genre_ids = frozenset(g.id for g in movie.genres)
    if not genre_ids:
        return None
    earlier_combinations = get_earlier_genre_id_sets(before=movie.created_at)
    if genre_ids in earlier_combinations:
        return None
    genre_names = ", ".join(g.name for g in movie.genres)
    return AlertCandidate(
        rule_name="new_genre_combination",
        movie_id=movie.id,
        screening_id=None,
        dedup_key=f"new_genre_combination:{movie.id}",
        drafted_text=(
            f"🎭 Combinação de gêneros inédita na programação: {genre_names} "
            f'em "{movie.title}".'
        ),
        context={"movie_title": movie.title, "genres": genre_names},
    )


def evaluate_sequel_or_franchise(movie: Movie) -> Optional[AlertCandidate]:
    if movie.collection_id is None:
        return None
    earlier_movies = get_earlier_movies_with_collection(
        movie.collection_id, before=movie.created_at, exclude_movie_id=movie.id
    )
    if not earlier_movies:
        return None
    earlier_titles = ", ".join(m.title for m in earlier_movies[:3])
    collection_name = movie.collection.name if movie.collection else ""
    return AlertCandidate(
        rule_name="sequel_or_franchise",
        movie_id=movie.id,
        screening_id=None,
        dedup_key=f"sequel_or_franchise:{movie.id}",
        drafted_text=(
            f'🎞️ "{movie.title}" faz parte da franquia {collection_name} - '
            f"já exibimos: {earlier_titles}."
        ),
        context={
            "movie_title": movie.title,
            "collection": collection_name,
            "earlier_titles": earlier_titles,
        },
    )


METADATA_MOVIE_RULES = [
    evaluate_director_debut,
    evaluate_returning_director,
    evaluate_new_genre_combination,
    evaluate_sequel_or_franchise,
]
