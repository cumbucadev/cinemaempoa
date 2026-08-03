"""Deterministic editorial motif detection: inspects the knowledge graph
(GraphQLite, synced via graph_sync.py) and produces structured Observation
objects for predefined editorial patterns. See
docs/superpowers/specs/2026-08-03-motif-detection-design.md for the full
design rationale, including the GraphQLite quirks this module works around
(min()/max() on date strings, collect(DISTINCT ...) not deduplicating).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


@dataclass
class GraphEvidence:
    nodes: list[str]
    edges: list[tuple[str, str, str]]
    query: str | None = None


@dataclass
class Observation:
    motif_name: str
    confidence: float
    score: float
    headline: str
    summary: str
    evidence: GraphEvidence
    metadata: dict = field(default_factory=dict)


class Motif(ABC):
    name: str
    description: str
    version: str

    @abstractmethod
    def detect(self, graph) -> list[Observation]: ...


def _dedupe_preserve_order(items: list) -> list:
    """GraphQLite's collect(DISTINCT x.prop) does not deduplicate (see
    module docstring / design doc), so every motif that collects a property
    list must dedupe it here instead."""
    return list(dict.fromkeys(items))


class MultipleMoviesSameDirectorMotif(Motif):
    name = "multiple_movies_same_director"
    description = "Detects directors with 2+ movies currently screening."
    version = "1.0"

    def detect(self, graph) -> list[Observation]:
        today = date.today().isoformat()
        rows = graph.query(
            "MATCH (d:Director)<-[:DIRECTED_BY]-(m:Movie)-[:HAS_SCREENING]->"
            "(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate) "
            "WHERE sd.date >= $today AND s.draft = false "
            "WITH d, count(DISTINCT m) AS movie_count, collect(m.id) AS movie_ids, "
            "collect(m.title) AS titles, collect(sd.date) AS dates "
            "WHERE movie_count >= 2 "
            "RETURN d.id AS director_id, d.name AS director_name, movie_count, "
            "movie_ids, titles, dates "
            "ORDER BY director_name",
            {"today": today},
        )

        observations = []
        for row in rows:
            movie_ids = _dedupe_preserve_order(row["movie_ids"])
            titles = _dedupe_preserve_order(row["titles"])
            observations.append(
                Observation(
                    motif_name=self.name,
                    confidence=1.0,
                    score=0.0,
                    headline=f"Múltiplos filmes de {row['director_name']} em cartaz",
                    summary=(
                        f"{len(movie_ids)} filmes dirigidos por "
                        f"{row['director_name']} estão em cartaz atualmente."
                    ),
                    evidence=GraphEvidence(
                        nodes=[row["director_id"], *movie_ids],
                        edges=[
                            (mid, row["director_id"], "DIRECTED_BY")
                            for mid in movie_ids
                        ],
                    ),
                    metadata={
                        "director": row["director_name"],
                        "movies": titles,
                        "next_screening_date": min(row["dates"]),
                    },
                )
            )
        return observations
