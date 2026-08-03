import calendar
from datetime import date

from graphqlite import Graph

from flask_backend.env_config import GRAPH_DB_PATH


def _open(db_path: str | None = None) -> Graph:
    return Graph(db_path or GRAPH_DB_PATH)


def movies_by_director(name: str, db_path: str | None = None) -> list[dict]:
    """Movies directed by the given director name."""
    graph = _open(db_path)
    return graph.query(
        "MATCH (m:Movie)-[:DIRECTED_BY]->(d:Director) "
        "WHERE d.name = $name "
        "RETURN m.title AS title, m.slug AS slug "
        "ORDER BY m.title",
        {"name": name},
    )


def directors_currently_showing(db_path: str | None = None) -> list[dict]:
    """Directors with at least one movie that has a screening today or later."""
    graph = _open(db_path)
    return graph.query(
        "MATCH (d:Director)<-[:DIRECTED_BY]-(:Movie)"
        "-[:HAS_SCREENING]->(:Screening)-[:HAS_DATE]->(sd:ScreeningDate) "
        "WHERE sd.date >= $today "
        "RETURN DISTINCT d.name AS name "
        "ORDER BY d.name",
        {"today": date.today().isoformat()},
    )


def countries_this_month(db_path: str | None = None) -> list[dict]:
    """Production countries with at least one screening date this month."""
    today = date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    start = today.replace(day=1).isoformat()
    end = today.replace(day=last_day).isoformat()

    graph = _open(db_path)
    return graph.query(
        "MATCH (c:Country)<-[:PRODUCED_IN]-(m:Movie)-[:HAS_SCREENING]->"
        "(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate) "
        "WHERE sd.date >= $start AND sd.date <= $end "
        "RETURN DISTINCT c.name AS name "
        "ORDER BY c.name",
        {"start": start, "end": end},
    )


def genres_at_cinema(
    cinema_slug: str, year: int, db_path: str | None = None
) -> list[dict]:
    """Genres shown at a given cinema during a given calendar year."""
    start = f"{year}-01-01"
    end = f"{year}-12-31"

    graph = _open(db_path)
    return graph.query(
        "MATCH (ci:Cinema)<-[:AT_CINEMA]-(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate), "
        "(s)<-[:HAS_SCREENING]-(m:Movie)-[:HAS_GENRE]->(g:Genre) "
        "WHERE ci.slug = $cinema_slug AND sd.date >= $start AND sd.date <= $end "
        "RETURN DISTINCT g.name AS name "
        "ORDER BY g.name",
        {"cinema_slug": cinema_slug, "start": start, "end": end},
    )


def screenings_since_release(movie_slug: str, db_path: str | None = None) -> list[dict]:
    """Every recorded screening date for a movie, across all cinemas,
    ordered chronologically. ("Since its release" simplifies to "all
    screening dates on record" - Phase 1's Movie node has no exact release
    date, only release_year.)"""
    graph = _open(db_path)
    return graph.query(
        "MATCH (m:Movie)-[:HAS_SCREENING]->(s:Screening)-[:HAS_DATE]->(sd:ScreeningDate), "
        "(s)-[:AT_CINEMA]->(ci:Cinema) "
        "WHERE m.slug = $movie_slug "
        "RETURN sd.date AS date, sd.time AS time, ci.name AS cinema_name "
        "ORDER BY sd.date, sd.time",
        {"movie_slug": movie_slug},
    )
