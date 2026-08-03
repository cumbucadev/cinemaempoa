from dataclasses import dataclass
from typing import List, Tuple

from graphqlite import Graph

from flask_backend.db import db_session
from flask_backend.env_config import GRAPH_DB_PATH
from flask_backend.models import Country, Director, Genre, Movie, Screening
from flask_backend.repository import (
    cinemas as cinemas_repo,
    countries as countries_repo,
    directors as directors_repo,
    genres as genres_repo,
)

NodeTuple = Tuple[str, dict, str]
EdgeTuple = Tuple[str, str, dict, str]


def _movie_node(movie: Movie) -> NodeTuple:
    return (
        f"movie:{movie.id}",
        {
            "sqlite_id": movie.id,
            "title": movie.title,
            "slug": movie.slug,
            "original_title": movie.original_title,
            "release_year": movie.release_year,
            "original_language": movie.original_language,
            "tmdb_id": movie.tmdb_id,
        },
        "Movie",
    )


def _cinema_node(cinema) -> NodeTuple:
    return (
        f"cinema:{cinema.id}",
        {"sqlite_id": cinema.id, "slug": cinema.slug, "name": cinema.name},
        "Cinema",
    )


def _screening_node(screening: Screening) -> NodeTuple:
    return (
        f"screening:{screening.id}",
        {"sqlite_id": screening.id, "url": screening.url, "draft": screening.draft},
        "Screening",
    )


def _screening_date_node(screening_date) -> NodeTuple:
    return (
        f"screeningdate:{screening_date.id}",
        {
            "sqlite_id": screening_date.id,
            "date": screening_date.date.isoformat(),
            "time": screening_date.time,
        },
        "ScreeningDate",
    )


def _genre_node(genre: Genre) -> NodeTuple:
    return (
        f"genre:{genre.id}",
        {"sqlite_id": genre.id, "tmdb_id": genre.tmdb_id, "name": genre.name},
        "Genre",
    )


def _director_node(director: Director) -> NodeTuple:
    return (
        f"director:{director.id}",
        {"sqlite_id": director.id, "tmdb_id": director.tmdb_id, "name": director.name},
        "Director",
    )


def _country_node(country: Country) -> NodeTuple:
    return (
        f"country:{country.id}",
        {
            "sqlite_id": country.id,
            "iso_3166_1": country.iso_3166_1,
            "name": country.name,
        },
        "Country",
    )


def build_graph_data() -> Tuple[List[NodeTuple], List[EdgeTuple]]:
    """Reads every row Phase 1's knowledge graph cares about from SQLite and
    returns the full set of graph nodes/edges for a from-scratch rebuild.

    Unfiltered by design: the graph is meant to be a faithful mirror of
    SQLite's explicit facts, not a business-logic view (see graph_sync.py's
    module docstring reasoning in the implementation plan for why Movie and
    Screening are queried directly instead of through the repository
    layer's `get_all()` functions, which apply publish-state filtering).
    """
    nodes: List[NodeTuple] = []
    edges: List[EdgeTuple] = []

    movies = db_session.query(Movie).all()
    for movie in movies:
        nodes.append(_movie_node(movie))
        for genre in movie.genres:
            edges.append((f"movie:{movie.id}", f"genre:{genre.id}", {}, "HAS_GENRE"))
        for director in movie.directors:
            edges.append(
                (f"movie:{movie.id}", f"director:{director.id}", {}, "DIRECTED_BY")
            )
        for country in movie.countries:
            edges.append(
                (f"movie:{movie.id}", f"country:{country.id}", {}, "PRODUCED_IN")
            )

    for cinema in cinemas_repo.get_all():
        nodes.append(_cinema_node(cinema))

    for genre in genres_repo.get_all():
        nodes.append(_genre_node(genre))

    for director in directors_repo.get_all():
        nodes.append(_director_node(director))

    for country in countries_repo.get_all():
        nodes.append(_country_node(country))

    screenings = db_session.query(Screening).all()
    for screening in screenings:
        nodes.append(_screening_node(screening))
        edges.append(
            (
                f"movie:{screening.movie_id}",
                f"screening:{screening.id}",
                {},
                "HAS_SCREENING",
            )
        )
        edges.append(
            (
                f"screening:{screening.id}",
                f"cinema:{screening.cinema_id}",
                {},
                "AT_CINEMA",
            )
        )
        for screening_date in screening.dates:
            nodes.append(_screening_date_node(screening_date))
            edges.append(
                (
                    f"screening:{screening.id}",
                    f"screeningdate:{screening_date.id}",
                    {},
                    "HAS_DATE",
                )
            )

    return nodes, edges


@dataclass
class SyncResult:
    nodes_created: int
    edges_created: int


def sync_graph(db_path: str | None = None) -> SyncResult:
    """Rebuilds the knowledge graph from scratch: wipes every node/edge in
    the GraphQLite file at db_path (or GRAPH_DB_PATH) and re-inserts a
    fresh graph from the current SQLite state. Idempotent - safe to run
    repeatedly, always converges to the same graph for the same SQLite
    state."""
    path = db_path or GRAPH_DB_PATH
    graph = Graph(path)
    graph.query("MATCH (n) DETACH DELETE n")

    nodes, edges = build_graph_data()
    result = graph.insert_graph_bulk(nodes, edges)

    return SyncResult(
        nodes_created=result.nodes_inserted, edges_created=result.edges_inserted
    )
