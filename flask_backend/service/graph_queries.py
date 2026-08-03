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
