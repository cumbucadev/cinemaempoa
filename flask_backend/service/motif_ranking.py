"""Scores, deduplicates, and ranks the Observations produced by every motif
in MOTIF_REGISTRY. See flask_backend/service/motifs.py for the motifs
themselves and docs/superpowers/specs/2026-08-03-motif-detection-design.md
for the ranking formula's rationale (the PRD's historical_significance
signal is dropped - no honest data to back it with yet)."""

from datetime import date

from graphqlite import Graph

from flask_backend.env_config import GRAPH_DB_PATH
from flask_backend.service.motifs import MOTIF_REGISTRY, Observation

RARITY_WEIGHT = 0.45
TIMELINESS_WEIGHT = 0.30
GRAPH_COMPLEXITY_WEIGHT = 0.25

TIMELINESS_FULL_SCORE_DAYS = 7
TIMELINESS_ZERO_SCORE_DAYS = 60
GRAPH_COMPLEXITY_NODE_CAP = 10


def _open(db_path: str | None = None) -> Graph:
    return Graph(db_path or GRAPH_DB_PATH)


def _timeliness(observation: Observation) -> float:
    next_date_str = observation.metadata.get("next_screening_date")
    if not next_date_str:
        return 0.0

    days_until = (date.fromisoformat(next_date_str) - date.today()).days
    if days_until <= TIMELINESS_FULL_SCORE_DAYS:
        return 1.0
    if days_until >= TIMELINESS_ZERO_SCORE_DAYS:
        return 0.0

    span = TIMELINESS_ZERO_SCORE_DAYS - TIMELINESS_FULL_SCORE_DAYS
    return 1.0 - (days_until - TIMELINESS_FULL_SCORE_DAYS) / span


def _score(observation: Observation, sibling_count: int) -> float:
    rarity = 1 / sibling_count
    timeliness = _timeliness(observation)
    graph_complexity = min(
        len(observation.evidence.nodes) / GRAPH_COMPLEXITY_NODE_CAP, 1.0
    )
    return (
        RARITY_WEIGHT * rarity
        + TIMELINESS_WEIGHT * timeliness
        + GRAPH_COMPLEXITY_WEIGHT * graph_complexity
    )


def _deduplicate(observations: list[Observation]) -> list[Observation]:
    """Merges observations whose evidence node sets overlap: the
    higher-scored observation survives, the lower-scored one's motif_name
    is recorded in the survivor's metadata['merged_from'] and it is
    dropped."""
    kept: list[Observation] = []
    for obs in observations:
        obs_nodes = set(obs.evidence.nodes)
        match_index = next(
            (
                i
                for i, existing in enumerate(kept)
                if obs_nodes & set(existing.evidence.nodes)
            ),
            None,
        )
        if match_index is None:
            kept.append(obs)
            continue

        existing = kept[match_index]
        if obs.score > existing.score:
            obs.metadata.setdefault("merged_from", []).append(existing.motif_name)
            kept[match_index] = obs
        else:
            existing.metadata.setdefault("merged_from", []).append(obs.motif_name)
    return kept


def rank_observations(observations: list[Observation]) -> list[Observation]:
    if not observations:
        return []

    motif_counts: dict[str, int] = {}
    for obs in observations:
        motif_counts[obs.motif_name] = motif_counts.get(obs.motif_name, 0) + 1

    for obs in observations:
        obs.score = _score(obs, motif_counts[obs.motif_name])

    deduped = _deduplicate(observations)
    return sorted(deduped, key=lambda o: o.score, reverse=True)


def run_motifs(db_path: str | None = None) -> list[Observation]:
    graph = _open(db_path)
    observations: list[Observation] = []
    for motif in MOTIF_REGISTRY:
        observations.extend(motif.detect(graph))
    return rank_observations(observations)
