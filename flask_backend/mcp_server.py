"""The MCP server the Orbit inspection agent calls: a thin shell over the
per-request tools in flask_backend/service/movie_inspection_tools.py,
served over streamable HTTP and guarded by a static bearer token
(ORBIT_MCP_TOKEN).

Run it locally with `uv run python -m flask_backend.mcp_server`.
"""

import hmac
from typing import Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from flask import Flask
from starlette.middleware import Middleware
from starlette.responses import JSONResponse

from flask_backend.env_config import MCP_HOST, MCP_PORT, ORBIT_MCP_TOKEN
from flask_backend.service import movie_inspection_tools as tools

MCP_PATH = "/mcp"


class BearerTokenMiddleware:
    """Rejects, with 401 and before any tool runs, every HTTP request whose
    `Authorization: Bearer <token>` does not match `token`. Compared in
    constant time."""

    def __init__(self, app, token: str):
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not self._is_authorized(scope):
            response = JSONResponse({"error": "unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _is_authorized(self, scope) -> bool:
        provided = dict(scope["headers"]).get(b"authorization", b"")
        return hmac.compare_digest(provided, self.expected)


def create_mcp_server(flask_app: Flask) -> FastMCP:
    """Builds the MCP server. Each tool call runs inside `flask_app`'s app
    context, whose teardown removes the thread's db_session."""
    mcp = FastMCP("cinemaempoa")

    def run_in_app_context(tool, *args):
        with flask_app.app_context():
            try:
                return tool(*args)
            except tools.InspectionRequestError as exc:
                raise ToolError(str(exc)) from exc

    @mcp.tool
    def get_movie_context(request_id: int) -> tools.MovieContext:
        """Devolve o título do filme do pedido de inspeção, o vínculo TMDB
        atual (título original, ano, idioma original, diretores, países,
        gêneros) e as sessões publicadas pelos cinemas (screening_id, cinema,
        descrição). `request_id` é obrigatório: é o id do pedido de inspeção
        recebido no disparo."""
        return run_in_app_context(tools.get_movie_context, request_id)

    @mcp.tool
    def search_tmdb_candidates(request_id: int, title: str) -> str:
        """Busca `title` no TMDB e devolve os candidatos encontrados
        (tmdb_id, título e ano). `request_id` é obrigatório: é o id do pedido
        de inspeção recebido no disparo. Os tmdb_ids devolvidos ficam
        registrados como observados neste pedido."""
        return run_in_app_context(tools.search_tmdb_candidates, request_id, title)

    @mcp.tool
    def get_tmdb_details(request_id: int, tmdb_id: int) -> str:
        """Devolve os detalhes de um filme no TMDB: título original, ano,
        diretores e países. `request_id` é obrigatório: é o id do pedido de
        inspeção recebido no disparo. O tmdb_id consultado fica registrado
        como observado neste pedido."""
        return run_in_app_context(tools.get_tmdb_details, request_id, tmdb_id)

    @mcp.tool
    def fetch_screening_source(request_id: int, screening_id: int) -> str:
        """Devolve o texto da página de origem de uma sessão do filme do
        pedido, sem HTML e cortado em 4000 caracteres. `request_id` é
        obrigatório: é o id do pedido de inspeção recebido no disparo. Só
        aceita sessões do filme do pedido (veja get_movie_context)."""
        return run_in_app_context(
            tools.fetch_screening_source, request_id, screening_id
        )

    @mcp.tool
    def apply_verdict(
        request_id: int,
        status: tools.VerdictStatus,
        reasoning: str,
        new_tmdb_id: Optional[int],
    ) -> tools.VerdictResult:
        """Encerra o pedido de inspeção com o veredito: `consistent`, `fixed`
        (troca o vínculo pelo `new_tmdb_id`) ou `needs_review`. `request_id`
        é obrigatório: é o id do pedido de inspeção recebido no disparo.
        Em `fixed`, `new_tmdb_id` precisa ter sido observado por
        search_tmdb_candidates ou get_tmdb_details neste pedido; senão o
        veredito vira `needs_review`. Nos outros casos, passe `new_tmdb_id`
        nulo. Devolve a inspeção gravada; chamar de novo num pedido já
        encerrado devolve o mesmo resultado sem gravar nada."""
        return run_in_app_context(
            tools.apply_verdict, request_id, status, reasoning, new_tmdb_id
        )

    return mcp


def create_http_app(flask_app: Flask, token: str):
    """The streamable-HTTP ASGI app, served at MCP_PATH. Refuses to build
    without a token, so a forgotten ORBIT_MCP_TOKEN never exposes the
    endpoint unauthenticated."""
    if not token:
        raise RuntimeError(
            "ORBIT_MCP_TOKEN está vazio: o servidor MCP não sobe sem token."
        )
    return create_mcp_server(flask_app).http_app(
        path=MCP_PATH,
        middleware=[Middleware(BearerTokenMiddleware, token=token)],
    )


def main():  # pragma: no cover - starts a long-running server
    import uvicorn

    from flask_backend import create_app

    http_app = create_http_app(create_app(), ORBIT_MCP_TOKEN)
    uvicorn.run(http_app, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
