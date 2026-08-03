"""
Tests the sync-graph and graph-query CLI commands in flask_backend/commands.py.
"""


class TestSyncGraphCommand:
    def test_reports_node_and_edge_counts(
        self, app, runner, setup_cinemas, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "flask_backend.service.graph_sync.GRAPH_DB_PATH", str(tmp_path / "graph.db")
        )

        result = runner.invoke(args=["sync-graph"])

        assert result.exit_code == 0
        assert "nós" in result.output
        assert "arestas" in result.output
