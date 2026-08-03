"""
Tests flask_backend/service/motif_ranking.py.
"""

from datetime import date, timedelta

from flask_backend.db import db_session
from flask_backend.models import Movie, Screening, ScreeningDate
from flask_backend.repository.cinemas import get_by_slug as get_cinema_by_slug
from flask_backend.repository.directors import (
    get_or_create_by_tmdb_id as get_or_create_director,
)
from flask_backend.service.graph_sync import sync_graph
from flask_backend.service.motif_ranking import rank_observations, run_motifs
from flask_backend.service.motifs import GraphEvidence, Observation


def _observation(motif_name, nodes, next_screening_date, confidence=1.0):
    return Observation(
        motif_name=motif_name,
        confidence=confidence,
        score=0.0,
        headline="h",
        summary="s",
        evidence=GraphEvidence(nodes=nodes, edges=[]),
        metadata={"next_screening_date": next_screening_date},
    )


class TestRankObservations:
    def test_returns_empty_list_for_empty_input(self):
        assert rank_observations([]) == []

    def test_sorts_by_score_descending(self):
        today = date.today().isoformat()
        far_future = (date.today() + timedelta(days=90)).isoformat()

        # Same motif (so rarity ties), but one is timely and one is not,
        # and the timely one has more evidence nodes (graph_complexity) -
        # both push its score above the other's.
        near = _observation("m", ["a", "b", "c"], today)
        far = _observation("m", ["d"], far_future)

        ranked = rank_observations([far, near])

        assert ranked[0] is near
        assert ranked[1] is far
        assert ranked[0].score > ranked[1].score

    def test_rarity_penalizes_motifs_with_many_siblings(self):
        today = date.today().isoformat()
        solo = _observation("solo_motif", ["a"], today)
        crowded = [_observation("crowded_motif", [f"n{i}"], today) for i in range(5)]

        ranked = rank_observations([solo, *crowded])

        solo_score = next(o.score for o in ranked if o.motif_name == "solo_motif")
        crowded_score = next(o.score for o in ranked if o.motif_name == "crowded_motif")
        assert solo_score > crowded_score

    def test_merges_observations_with_overlapping_evidence(self):
        today = date.today().isoformat()
        low = _observation("anniversary", ["movie:1"], today)
        high = _observation("director_return", ["movie:1", "director:1"], today)

        ranked = rank_observations([low, high])

        assert len(ranked) == 1
        survivor = ranked[0]
        assert survivor.motif_name == "director_return"
        assert survivor.metadata["merged_from"] == ["anniversary"]

    def test_does_not_merge_observations_with_disjoint_evidence(self):
        today = date.today().isoformat()
        a = _observation("motif_a", ["movie:1"], today)
        b = _observation("motif_b", ["movie:2"], today)

        ranked = rank_observations([a, b])

        assert len(ranked) == 2


class TestRunMotifs:
    def test_returns_ranked_observations_from_a_real_graph(
        self, app, setup_cinemas, tmp_path
    ):
        with app.app_context():
            director = get_or_create_director(1, "Wim Wenders")
            movie_a = Movie(title="Paris, Texas", slug="paris-texas")
            movie_a.directors = [director]
            movie_a.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[
                        ScreeningDate(
                            date=date.today() + timedelta(days=1), time="19:00"
                        )
                    ],
                )
            ]
            movie_b = Movie(title="Perfect Days", slug="perfect-days")
            movie_b.directors = [director]
            movie_b.screenings = [
                Screening(
                    cinema_id=get_cinema_by_slug("capitolio").id,
                    description="d",
                    draft=False,
                    dates=[
                        ScreeningDate(
                            date=date.today() + timedelta(days=2), time="19:00"
                        )
                    ],
                )
            ]
            db_session.add_all([movie_a, movie_b])
            db_session.commit()

            db_path = str(tmp_path / "graph.db")
            sync_graph(db_path=db_path)

            observations = run_motifs(db_path=db_path)

            assert len(observations) == 1
            assert observations[0].motif_name == "multiple_movies_same_director"
            assert observations[0].score > 0
