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


DIRECTOR_FOCUS_THRESHOLD = 2
COUNTRY_FOCUS_THRESHOLD = 2
GENRE_FOCUS_THRESHOLD = 2


class DirectorFocusMotif(Motif):
    name = "director_focus"
    description = "Detects directors with 2+ movies currently screening."
    version = "1.0"

    def detect(self, graph) -> list[Observation]:
        today = date.today().isoformat()
        query = (
            "MATCH (d:Director)<-[:DIRECTED_BY]-(m:Movie)-[:HAS_SCREENING]->"
            "(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate) "
            "WHERE sd.date >= $today AND s.draft = false "
            "WITH d, count(DISTINCT m) AS movie_count, collect(m.id) AS movie_ids, "
            "collect(m.title) AS titles, collect(sd.date) AS dates "
            "WHERE movie_count >= $threshold "
            "RETURN d.id AS director_id, d.name AS director_name, movie_count, "
            "movie_ids, titles, dates "
            "ORDER BY director_name"
        )
        rows = graph.query(
            query, {"today": today, "threshold": DIRECTOR_FOCUS_THRESHOLD}
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
                        query=query,
                    ),
                    metadata={
                        "director": row["director_name"],
                        "movies": titles,
                        "next_screening_date": min(row["dates"]),
                    },
                )
            )
        return observations


class CountryFocusMotif(Motif):
    name = "country_focus"
    description = (
        f"Detects production countries with {COUNTRY_FOCUS_THRESHOLD}+ "
        "movies currently screening."
    )
    version = "1.0"

    def detect(self, graph) -> list[Observation]:
        today = date.today().isoformat()
        query = (
            "MATCH (m:Movie)-[:PRODUCED_IN]->(c:Country), "
            "(m)-[:HAS_SCREENING]->(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate) "
            "WHERE sd.date >= $today AND s.draft = false "
            "WITH c, count(DISTINCT m) AS movie_count, collect(m.id) AS movie_ids, "
            "collect(m.title) AS titles, collect(sd.date) AS dates "
            "WHERE movie_count >= $threshold "
            "RETURN c.id AS country_id, c.name AS country_name, movie_count, "
            "movie_ids, titles, dates "
            "ORDER BY country_name"
        )
        rows = graph.query(
            query, {"today": today, "threshold": COUNTRY_FOCUS_THRESHOLD}
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
                    headline=f"Cinema de {row['country_name']} em destaque",
                    summary=(
                        f"{len(movie_ids)} filmes de {row['country_name']} "
                        "estão em cartaz atualmente."
                    ),
                    evidence=GraphEvidence(
                        nodes=[row["country_id"], *movie_ids],
                        edges=[
                            (mid, row["country_id"], "PRODUCED_IN") for mid in movie_ids
                        ],
                        query=query,
                    ),
                    metadata={
                        "country": row["country_name"],
                        "movies": titles,
                        "next_screening_date": min(row["dates"]),
                    },
                )
            )
        return observations


class GenreFocusMotif(Motif):
    name = "genre_focus"
    description = (
        f"Detects genres with {GENRE_FOCUS_THRESHOLD}+ movies currently "
        "screening, across all cinemas."
    )
    version = "2.0"

    def detect(self, graph) -> list[Observation]:
        today = date.today().isoformat()
        query = (
            "MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre), "
            "(m)-[:HAS_SCREENING]->(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate) "
            "WHERE sd.date >= $today AND s.draft = false "
            "WITH g, count(DISTINCT m) AS movie_count, collect(m.id) AS movie_ids, "
            "collect(m.title) AS titles, collect(sd.date) AS dates "
            "WHERE movie_count >= $threshold "
            "RETURN g.id AS genre_id, g.name AS genre_name, movie_count, "
            "movie_ids, titles, dates "
            "ORDER BY genre_name"
        )
        rows = graph.query(query, {"today": today, "threshold": GENRE_FOCUS_THRESHOLD})

        observations = []
        for row in rows:
            movie_ids = _dedupe_preserve_order(row["movie_ids"])
            titles = _dedupe_preserve_order(row["titles"])
            observations.append(
                Observation(
                    motif_name=self.name,
                    confidence=1.0,
                    score=0.0,
                    headline=f"{row['genre_name']} em destaque nos cinemas",
                    summary=(
                        f"{len(movie_ids)} filmes de {row['genre_name']} "
                        "estão em cartaz atualmente."
                    ),
                    evidence=GraphEvidence(
                        nodes=[row["genre_id"], *movie_ids],
                        edges=[
                            (mid, row["genre_id"], "HAS_GENRE") for mid in movie_ids
                        ],
                        query=query,
                    ),
                    metadata={
                        "genre": row["genre_name"],
                        "movies": titles,
                        "next_screening_date": min(row["dates"]),
                    },
                )
            )
        return observations


DIRECTOR_RETURN_GAP_DAYS = 180


class DirectorReturnMotif(Motif):
    name = "director_return"
    description = (
        f"Detects directors whose currently-screening movie follows a gap "
        f"of {DIRECTOR_RETURN_GAP_DAYS}+ days since their last recorded "
        "screening. Threshold is deliberately short: the DB only has "
        "screening history back to Jan 2025, so this cannot yet detect a "
        "true multi-year gap."
    )
    version = "1.0"

    def detect(self, graph) -> list[Observation]:
        query = (
            "MATCH (d:Director)<-[:DIRECTED_BY]-(m:Movie)-[:HAS_SCREENING]->"
            "(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate) "
            "WHERE s.draft = false "
            "RETURN d.id AS director_id, d.name AS director_name, "
            "m.id AS movie_id, m.title AS title, sd.date AS date "
            "ORDER BY director_name"
        )
        rows = graph.query(query)

        today_iso = date.today().isoformat()
        by_director: dict[str, dict] = {}
        for row in rows:
            entry = by_director.setdefault(
                row["director_id"],
                {"name": row["director_name"], "past": [], "current": []},
            )
            bucket = "current" if row["date"] >= today_iso else "past"
            entry[bucket].append((row["movie_id"], row["title"], row["date"]))

        observations = []
        for director_id, entry in by_director.items():
            if not entry["past"] or not entry["current"]:
                continue

            last_past_date = max(d for _, _, d in entry["past"])
            first_current_date = min(d for _, _, d in entry["current"])
            gap_days = (
                date.fromisoformat(first_current_date)
                - date.fromisoformat(last_past_date)
            ).days
            if gap_days <= DIRECTOR_RETURN_GAP_DAYS:
                continue

            current_movie_ids = _dedupe_preserve_order(
                [mid for mid, _, _ in entry["current"]]
            )
            current_titles = _dedupe_preserve_order(
                [title for _, title, _ in entry["current"]]
            )
            observations.append(
                Observation(
                    motif_name=self.name,
                    confidence=0.7,
                    score=0.0,
                    headline=f"{entry['name']} retorna após {gap_days} dias",
                    summary=(
                        f"Um filme de {entry['name']} volta a ser exibido "
                        f"após {gap_days} dias sem sessões registradas."
                    ),
                    evidence=GraphEvidence(
                        nodes=[director_id, *current_movie_ids],
                        edges=[
                            (mid, director_id, "DIRECTED_BY")
                            for mid in current_movie_ids
                        ],
                        query=query,
                    ),
                    metadata={
                        "director": entry["name"],
                        "movies": current_titles,
                        "gap_days": gap_days,
                        "next_screening_date": first_current_date,
                    },
                )
            )
        return observations


ANNIVERSARY_YEARS = {10, 20, 25, 30, 40, 50, 75, 100}


class AnniversaryMotif(Motif):
    name = "anniversary"
    description = (
        "Detects currently-screening movies whose age since release "
        f"matches a recognized anniversary year: {sorted(ANNIVERSARY_YEARS)}."
    )
    version = "1.0"

    def detect(self, graph) -> list[Observation]:
        today = date.today().isoformat()
        query = (
            "MATCH (m:Movie)-[:HAS_SCREENING]->(s:Screening)-[:HAS_DATE]->"
            "(sd:ScreeningDate) "
            "WHERE sd.date >= $today AND s.draft = false "
            "RETURN m.id AS movie_id, m.title AS title, m.release_year AS "
            "release_year, sd.date AS date "
            "ORDER BY m.title, sd.date"
        )
        rows = graph.query(query, {"today": today})

        by_movie: dict[str, dict] = {}
        for row in rows:
            entry = by_movie.setdefault(
                row["movie_id"],
                {
                    "title": row["title"],
                    "release_year": row["release_year"],
                    "dates": [],
                },
            )
            entry["dates"].append(row["date"])

        current_year = date.today().year
        observations = []
        for movie_id, entry in by_movie.items():
            if entry["release_year"] is None:
                continue
            years = current_year - entry["release_year"]
            if years not in ANNIVERSARY_YEARS:
                continue

            observations.append(
                Observation(
                    motif_name=self.name,
                    confidence=1.0,
                    score=0.0,
                    headline=f"{entry['title']} completa {years} anos em cartaz",
                    summary=(
                        f"{entry['title']}, lançado há {years} anos, está "
                        "de volta aos cinemas."
                    ),
                    evidence=GraphEvidence(nodes=[movie_id], edges=[], query=query),
                    metadata={
                        "movie": entry["title"],
                        "years": years,
                        "next_screening_date": min(entry["dates"]),
                    },
                )
            )
        return observations


MOTIF_REGISTRY: list[Motif] = [
    DirectorFocusMotif(),
    CountryFocusMotif(),
    GenreFocusMotif(),
    DirectorReturnMotif(),
    AnniversaryMotif(),
]
