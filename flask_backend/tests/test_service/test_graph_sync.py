"""
Tests flask_backend/service/graph_sync.py.
"""


class TestGraphqliteSmokeTest:
    def test_extension_loads_and_supports_basic_cypher(self, tmp_path):
        from graphqlite import Graph

        db_path = str(tmp_path / "smoke.db")
        graph = Graph(db_path)
        graph.upsert_node("a", {"name": "A"}, label="Thing")
        graph.upsert_node("b", {"name": "B"}, label="Thing")
        graph.upsert_edge("a", "b", {}, rel_type="RELATED")

        results = graph.query(
            "MATCH (x:Thing)-[:RELATED]->(y:Thing) "
            "RETURN x.name AS x_name, y.name AS y_name"
        )

        assert results == [{"x_name": "A", "y_name": "B"}]
