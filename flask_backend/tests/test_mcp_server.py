import asyncio
from unittest.mock import patch

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from starlette.responses import PlainTextResponse

from flask_backend import mcp_server
from flask_backend.db import db_session
from flask_backend.models import Cinema, Movie, Screening
from flask_backend.repository import movie_inspection_requests

TOKEN = "segredo-de-teste"


def _create_request_with_screening():
    movie = Movie(title="Filme de Teste", slug="filme-de-teste", tmdb_id=42)
    cinema = Cinema(slug="cine-teste", name="Cine Teste", url="https://example.com")
    db_session.add_all([movie, cinema])
    db_session.commit()
    screening = Screening(
        movie_id=movie.id, cinema_id=cinema.id, description="Drama de 1979."
    )
    db_session.add(screening)
    db_session.commit()
    return movie_inspection_requests.create_for_movie(movie), screening


def _argument_types(schema):
    return {name: prop.get("type") for name, prop in schema["properties"].items()}


async def _with_client(app, fn):
    async with Client(mcp_server.create_mcp_server(app)) as client:
        return await fn(client)


class TestTools:
    def test_lists_the_tools_with_typed_schemas(self, app):
        tools = asyncio.run(_with_client(app, lambda c: c.list_tools()))

        schemas = {t.name: t.inputSchema for t in tools}
        assert schemas.keys() == {
            "get_movie_context",
            "search_tmdb_candidates",
            "get_tmdb_details",
            "fetch_screening_source",
            "apply_verdict",
        }
        assert _argument_types(schemas["get_movie_context"]) == {
            "request_id": "integer"
        }
        assert _argument_types(schemas["search_tmdb_candidates"]) == {
            "request_id": "integer",
            "title": "string",
        }
        assert _argument_types(schemas["get_tmdb_details"]) == {
            "request_id": "integer",
            "tmdb_id": "integer",
        }
        assert _argument_types(schemas["fetch_screening_source"]) == {
            "request_id": "integer",
            "screening_id": "integer",
        }
        apply_verdict = schemas["apply_verdict"]["properties"]
        assert apply_verdict["request_id"]["type"] == "integer"
        assert apply_verdict["status"]["enum"] == [
            "consistent",
            "fixed",
            "needs_review",
        ]
        assert apply_verdict["reasoning"]["type"] == "string"
        assert apply_verdict["new_tmdb_id"] == {"type": "integer"}
        for tool in tools:
            optional = {"new_tmdb_id"} if tool.name == "apply_verdict" else set()
            assert set(tool.inputSchema["required"]) == (
                set(tool.inputSchema["properties"]) - optional
            )
            assert "`request_id` é obrigatório" in " ".join(tool.description.split())

    def test_an_observation_tool_end_to_end(self, app):
        with app.app_context():
            request, _ = _create_request_with_screening()
            request_id = request.id

        results = [{"id": 573412, "title": "A Capela", "release_date": "1979-01-01"}]
        with patch.object(
            mcp_server.tools.TMDBClient, "search_movies", return_value=results
        ), patch("flask_backend.service.tmdb.TMDB_API_TOKEN", "fake-token"):
            result = asyncio.run(
                _with_client(
                    app,
                    lambda c: c.call_tool(
                        "search_tmdb_candidates",
                        {"request_id": request_id, "title": "A Capela"},
                    ),
                )
            )

        assert result.data == (
            "Candidatos no TMDB para 'A Capela':\n"
            "- tmdb_id=573412 título='A Capela' ano=1979"
        )
        with app.app_context():
            observed = movie_inspection_requests.get_by_id(request_id)
            assert observed.observed_tmdb_ids == "[573412]"

    def test_get_movie_context_end_to_end(self, app):
        with app.app_context():
            request, screening = _create_request_with_screening()
            request_id, screening_id = request.id, screening.id

        result = asyncio.run(
            _with_client(
                app,
                lambda c: c.call_tool("get_movie_context", {"request_id": request_id}),
            )
        )

        assert result.structured_content["movie_title"] == "Filme de Teste"
        assert result.structured_content["tmdb_id"] == 42
        assert result.structured_content["screenings"] == [
            {
                "screening_id": screening_id,
                "cinema_name": "Cine Teste",
                "description": "Drama de 1979.",
            }
        ]

    @pytest.mark.parametrize(
        "extra", [{}, {"new_tmdb_id": None}], ids=["absent", "null"]
    )
    def test_apply_verdict_without_new_tmdb_id(self, app, extra):
        """Orbit omits `new_tmdb_id` outside `fixed`; an explicit null is
        read the same way."""
        with app.app_context():
            request, _ = _create_request_with_screening()
            request_id = request.id

        result = asyncio.run(
            _with_client(
                app,
                lambda c: c.call_tool(
                    "apply_verdict",
                    {
                        "request_id": request_id,
                        "status": "consistent",
                        "reasoning": "Ok.",
                        **extra,
                    },
                ),
            )
        )

        assert result.structured_content["status"] == "consistent"
        with app.app_context():
            movie = movie_inspection_requests.get_by_id(request_id).movie
            assert movie.tmdb_id == 42

    def test_ignores_arguments_the_tool_does_not_declare(self, app):
        """Orbit's `tool` node sends every input of the node (the execution
        input, the previous node's output), not just the tool's own
        arguments."""
        with app.app_context():
            request, _ = _create_request_with_screening()
            request_id = request.id

        result = asyncio.run(
            _with_client(
                app,
                lambda c: c.call_tool(
                    "get_movie_context",
                    {
                        "request_id": request_id,
                        "movie_id": 1,
                        "answer_json": {"status": "consistent"},
                        "selected_edge_id": "e-cond-ok",
                    },
                ),
            )
        )

        assert result.structured_content["movie_title"] == "Filme de Teste"

    @pytest.mark.parametrize(
        "name, arguments",
        [
            ("get_movie_context", {}),
            ("search_tmdb_candidates", {"title": "A Capela"}),
            ("get_tmdb_details", {"tmdb_id": 1}),
            ("fetch_screening_source", {"screening_id": 1}),
            (
                "apply_verdict",
                {"status": "consistent", "reasoning": "Ok."},
            ),
        ],
    )
    def test_an_invalid_request_comes_back_as_a_tool_error(self, app, name, arguments):
        with pytest.raises(ToolError, match="Pedido de inspeção #999 não existe"):
            asyncio.run(
                _with_client(
                    app,
                    lambda c: c.call_tool(name, {"request_id": 999, **arguments}),
                )
            )


async def _post_mcp(http_app, headers):
    transport = httpx.ASGITransport(app=http_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost"
    ) as client:
        return await client.post(
            mcp_server.MCP_PATH,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_movie_context", "arguments": {"request_id": 1}},
            },
        )


class TestAuth:
    @pytest.mark.parametrize(
        "headers",
        [
            {},
            {"Authorization": "Bearer token-errado"},
            {"Authorization": TOKEN},
        ],
        ids=["no-token", "wrong-token", "not-bearer"],
    )
    def test_rejects_without_a_valid_token_before_any_tool_runs(self, app, headers):
        http_app = mcp_server.create_http_app(app, TOKEN)

        with patch.object(mcp_server.tools, "get_movie_context") as get_movie_context:
            response = asyncio.run(_post_mcp(http_app, headers))

        assert response.status_code == 401
        get_movie_context.assert_not_called()

    def test_lets_the_right_token_through(self):
        inner = PlainTextResponse("ok")
        guarded = mcp_server.BearerTokenMiddleware(inner, token=TOKEN)

        response = asyncio.run(_post_mcp(guarded, {"Authorization": f"Bearer {TOKEN}"}))

        assert response.status_code == 200
        assert response.text == "ok"

    def test_refuses_to_start_with_an_empty_token(self, app):
        with pytest.raises(RuntimeError, match="ORBIT_MCP_TOKEN está vazio"):
            mcp_server.create_http_app(app, "")
