"""Deterministic editorial motif detection: inspects the knowledge graph
(GraphQLite, synced via graph_sync.py) and produces structured Observation
objects for predefined editorial patterns. See
docs/superpowers/specs/2026-08-03-motif-detection-design.md for the full
design rationale, including the GraphQLite quirks this module works around
(min()/max() on date strings, collect(DISTINCT ...) not deduplicating).
"""

import calendar
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


COUNTRY_CLUSTER_THRESHOLD = 2
MULTIPLE_MOVIES_THRESHOLD = 2


class MultipleMoviesSameDirectorMotif(Motif):
    name = "multiple_movies_same_director"
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
            query, {"today": today, "threshold": MULTIPLE_MOVIES_THRESHOLD}
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


class CountryClusterMotif(Motif):
    name = "country_cluster"
    description = (
        f"Detects production countries with {COUNTRY_CLUSTER_THRESHOLD}+ "
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
            query, {"today": today, "threshold": COUNTRY_CLUSTER_THRESHOLD}
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


CINEMA_GENRE_FOCUS_MULTIPLIER = 1.5
CINEMA_GENRE_FOCUS_MIN_COUNT = 3

ANNIVERSARY_YEARS = {10, 20, 25, 30, 40, 50, 75, 100}


class CinemaGenreFocusMotif(Motif):
    name = "cinema_genre_focus"
    description = (
        "Detects cinemas whose current-month genre distribution is "
        f"unusually skewed toward one genre (>= {CINEMA_GENRE_FOCUS_MULTIPLIER}x "
        "its historical share at that cinema, with at least "
        f"{CINEMA_GENRE_FOCUS_MIN_COUNT} screenings this month). The "
        "historical baseline is everything strictly before the current "
        "month - it must exclude the current period, otherwise a cinema "
        "with no prior history in a genre would show current == historical "
        "(both 100%) and never trip the multiplier check."
    )
    version = "1.0"

    def detect(self, graph) -> list[Observation]:
        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        start = today.replace(day=1).isoformat()
        end = today.replace(day=last_day).isoformat()

        current_query = (
            "MATCH (ci:Cinema)<-[:AT_CINEMA]-(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate), "
            "(s)<-[:HAS_SCREENING]-(m:Movie)-[:HAS_GENRE]->(g:Genre) "
            "WHERE sd.date >= $start AND sd.date <= $end AND s.draft = false "
            "WITH ci, g, count(sd) AS screening_count, collect(m.id) AS movie_ids, "
            "collect(sd.date) AS dates "
            "RETURN ci.id AS cinema_id, ci.name AS cinema_name, g.id AS genre_id, "
            "g.name AS genre_name, screening_count, movie_ids, dates"
        )
        current_rows = graph.query(current_query, {"start": start, "end": end})
        historical_query = (
            "MATCH (ci:Cinema)<-[:AT_CINEMA]-(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate), "
            "(s)<-[:HAS_SCREENING]-(m:Movie)-[:HAS_GENRE]->(g:Genre) "
            "WHERE sd.date < $start AND s.draft = false "
            "WITH ci, g, count(sd) AS screening_count "
            "RETURN ci.id AS cinema_id, g.id AS genre_id, screening_count"
        )
        historical_rows = graph.query(historical_query, {"start": start})

        historical_by_pair: dict[tuple[str, str], int] = {}
        historical_totals: dict[str, int] = {}
        for row in historical_rows:
            key = (row["cinema_id"], row["genre_id"])
            historical_by_pair[key] = (
                historical_by_pair.get(key, 0) + row["screening_count"]
            )
            historical_totals[row["cinema_id"]] = (
                historical_totals.get(row["cinema_id"], 0) + row["screening_count"]
            )

        current_totals: dict[str, int] = {}
        for row in current_rows:
            current_totals[row["cinema_id"]] = (
                current_totals.get(row["cinema_id"], 0) + row["screening_count"]
            )

        observations = []
        for row in current_rows:
            if row["screening_count"] < CINEMA_GENRE_FOCUS_MIN_COUNT:
                continue

            cinema_total = current_totals[row["cinema_id"]]
            current_share = row["screening_count"] / cinema_total

            hist_key = (row["cinema_id"], row["genre_id"])
            hist_count = historical_by_pair.get(hist_key, 0)
            hist_total = historical_totals.get(row["cinema_id"], 0)

            if hist_count == 0:
                qualifies = True
            else:
                historical_share = hist_count / hist_total
                qualifies = (
                    current_share >= CINEMA_GENRE_FOCUS_MULTIPLIER * historical_share
                )

            if not qualifies:
                continue

            movie_ids = _dedupe_preserve_order(row["movie_ids"])
            # This motif's query window is the whole calendar month (not
            # "today onward" like the other motifs), so row["dates"] often
            # contains dates earlier than today - prefer the earliest
            # future date, falling back to the earliest date overall only
            # if every date is in the past.
            today_iso = date.today().isoformat()
            future_dates = [d for d in row["dates"] if d >= today_iso]
            next_screening_date = (
                min(future_dates) if future_dates else min(row["dates"])
            )
            observations.append(
                Observation(
                    motif_name=self.name,
                    confidence=0.7,
                    score=0.0,
                    headline=(f"{row['cinema_name']} em foco: {row['genre_name']}"),
                    summary=(
                        f"{row['cinema_name']} está com programação "
                        f"incomumente voltada a {row['genre_name']} este mês."
                    ),
                    evidence=GraphEvidence(
                        nodes=[row["cinema_id"], row["genre_id"], *movie_ids],
                        edges=[
                            (mid, row["genre_id"], "HAS_GENRE") for mid in movie_ids
                        ],
                        query=current_query,
                    ),
                    metadata={
                        "cinema": row["cinema_name"],
                        "genre": row["genre_name"],
                        "screening_count": row["screening_count"],
                        "next_screening_date": next_screening_date,
                    },
                )
            )
        return observations


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
    MultipleMoviesSameDirectorMotif(),
    CountryClusterMotif(),
    DirectorReturnMotif(),
    CinemaGenreFocusMotif(),
    AnniversaryMotif(),
]
