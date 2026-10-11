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


async def _with_client(app, fn):
    async with Client(mcp_server.create_mcp_server(app)) as client:
        return await fn(client)


class TestTools:
    def test_lists_get_movie_context_with_a_typed_request_id(self, app):
        tools = asyncio.run(_with_client(app, lambda c: c.list_tools()))

        assert [t.name for t in tools] == ["get_movie_context"]
        tool = tools[0]
        assert tool.inputSchema["properties"]["request_id"]["type"] == "integer"
        assert tool.inputSchema["required"] == ["request_id"]
        assert "request_id` é obrigatório" in tool.description

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
        assert result.structured_content["screenings"] == [
            {
                "screening_id": screening_id,
                "cinema_name": "Cine Teste",
                "description": "Drama de 1979.",
            }
        ]

    def test_an_invalid_request_comes_back_as_a_tool_error(self, app):
        with pytest.raises(ToolError, match="Pedido de inspeção #999 não existe"):
            asyncio.run(
                _with_client(
                    app,
                    lambda c: c.call_tool("get_movie_context", {"request_id": 999}),
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
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
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
