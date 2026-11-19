"""The MCP server the Orbit inspection agent calls: a thin shell over the
per-request tools in flask_backend/service/movie_inspection_tools.py,
served over streamable HTTP and guarded by a static bearer token
(ORBIT_MCP_TOKEN).

Run it locally with `uv run python -m flask_backend.mcp_server`.
"""

import hmac
from typing import Annotated, Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware as MCPMiddleware
from flask import Flask
from pydantic import Field, WithJsonSchema
from starlette.middleware import Middleware
from starlette.responses import JSONResponse

from flask_backend.env_config import MCP_HOST, MCP_PORT, ORBIT_MCP_TOKEN
from flask_backend.service import catalog_tools, movie_inspection_tools as tools

MCP_PATH = "/mcp"


def _optional(py_type, json_schema: dict):
    """An optional tool argument advertised with `json_schema` alone: Orbit
    does not accept the `anyOf: [x, null]` an `Optional[x]` would produce.
    Absent means "not given"; an explicit null is still accepted and read the
    same way. The default_factory keeps `"default": null` out of the schema."""
    return Annotated[
        Optional[py_type],
        WithJsonSchema(json_schema),
        Field(default_factory=lambda: None),
    ]


OptionalTmdbId = _optional(int, {"type": "integer"})
OptionalInt = _optional(int, {"type": "integer"})
OptionalText = _optional(str, {"type": "string"})  # dates too


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


class DropUndeclaredArgumentsMiddleware(MCPMiddleware):
    """Drops the arguments a tool does not declare before FastMCP validates
    them. Orbit's `tool` node sends every input of the node (the execution
    input, the previous node's output), and FastMCP would otherwise refuse
    the whole call with `unexpected_keyword_argument`."""

    async def on_call_tool(self, context, call_next):
        params = context.message
        tool = await context.fastmcp_context.fastmcp.get_tool(params.name)
        if tool is not None and params.arguments:
            declared = tool.parameters.get("properties", {})
            arguments = {k: v for k, v in params.arguments.items() if k in declared}
            context = context.copy(
                message=params.model_copy(update={"arguments": arguments})
            )
        return await call_next(context)


def create_mcp_server(flask_app: Flask) -> FastMCP:
    """Builds the MCP server. Each tool call runs inside `flask_app`'s app
    context, whose teardown removes the thread's db_session."""
    mcp = FastMCP("cinemaempoa", middleware=[DropUndeclaredArgumentsMiddleware()])

    def run_in_app_context(tool, *args, **kwargs):
        with flask_app.app_context():
            try:
                return tool(*args, **kwargs)
            except (
                tools.InspectionRequestError,
                catalog_tools.CatalogToolError,
            ) as exc:
                raise ToolError(str(exc)) from exc

    @mcp.tool
    def get_movie_context(request_id: int) -> tools.MovieContext:
        """Devolve o título do filme do pedido de inspeção, o vínculo TMDB
        atual (`tmdb_id`, título original, ano, idioma original, diretores,
        países, gêneros) e as sessões publicadas pelos cinemas (screening_id,
        cinema, descrição). `tmdb_id` é o id do vínculo no TMDB, nulo quando
        o filme não tem vínculo; é o id a passar para get_tmdb_details ao
        conferir o vínculo atual, nunca o id do filme ou do pedido.
        `request_id` é obrigatório: é o id do pedido de inspeção recebido no
        disparo."""
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
        new_tmdb_id: OptionalTmdbId,
    ) -> tools.VerdictResult:
        """Encerra o pedido de inspeção com o veredito: `consistent`, `fixed`
        (troca o vínculo pelo `new_tmdb_id`) ou `needs_review`. `request_id`
        é obrigatório: é o id do pedido de inspeção recebido no disparo.
        Em `fixed`, `new_tmdb_id` precisa ter sido observado por
        search_tmdb_candidates ou get_tmdb_details neste pedido; senão o
        veredito vira `needs_review`. Nos outros casos, omita `new_tmdb_id`.
        Devolve a inspeção gravada; chamar de novo num pedido já
        encerrado devolve o mesmo resultado sem gravar nada."""
        return run_in_app_context(
            tools.apply_verdict, request_id, status, reasoning, new_tmdb_id
        )

    _register_catalog_tools(mcp, run_in_app_context)
    return mcp


def _register_catalog_tools(mcp: FastMCP, run_in_app_context) -> None:
    """The read-only catalog tools of the conversational agent."""

    @mcp.tool
    def search_movies(
        title: OptionalText,
        director: OptionalText,
        genre: OptionalText,
        country: OptionalText,
        year_from: OptionalInt,
        year_to: OptionalInt,
        cinema: OptionalText,
        shown_from: OptionalText,
        shown_to: OptionalText,
        sort: catalog_tools.MovieSort = "last_shown_desc",
        limit: int = 10,
    ) -> catalog_tools.MovieSearchResult:
        """Busca filmes no catálogo de sessões dos cinemas e diz quando cada
        um passou ou vai passar. Use para perguntas sobre o histórico e sobre
        filmes específicos: "já passou algum filme do Tarantino?", "qual foi
        o último filme de ação no Capitólio?", "que filmes franceses passaram
        em 2025?". Para a programação de um dia ou de alguns dias, com
        horários, prefira get_schedule; para os detalhes e horários de um
        filme já encontrado, get_movie.

        Todos os filtros são opcionais e se combinam com E. Os filtros de
        texto casam por trecho, sem diferenciar acentos nem maiúsculas:
        - `title`: trecho do título em português ou do título original;
        - `director`: trecho do nome de um dos diretores (use
          search_directors se o nome for ambíguo);
        - `genre`: trecho do gênero em português ("ação", "drama",
          "documentário");
        - `country`: trecho do país de produção em português ("França");
        - `year_from` / `year_to`: ano de lançamento, inclusivo; com esse
          filtro, filmes sem ano cadastrado ficam de fora.

        `cinema` (slug ou nome, veja list_cinemas), `shown_from` e `shown_to`
        (datas AAAA-MM-DD, inclusivas) definem quais sessões contam. O filme
        só aparece se tiver sessão nesse recorte, e `first_shown`,
        `last_shown`, `next_showing`, `cinemas` e `sessions` são calculados
        só sobre ele: com `cinema="capitolio"`, `last_shown` é a última vez
        no Capitólio e `cinemas` traz só o Capitólio.

        `today` é a data de hoje em Porto Alegre. `last_shown` é a exibição
        mais recente até hoje (nulo se o filme só tem sessões futuras) e
        `next_showing` é a próxima, de hoje em diante (nulo se não há).
        `sort`: `last_shown_desc` (padrão, exibição mais recente primeiro),
        `first_shown_asc` ou `title`. `limit` vai até 50; `total` é o número
        de filmes encontrados e `truncated` diz se a lista foi cortada.

        Exemplos: última vez que passou ação no Capitólio →
        `genre="ação", cinema="capitolio", sort="last_shown_desc", limit=1`;
        já passou Tarantino? → `director="tarantino"`.

        Uma lista vazia vale só para o período coberto pelo catálogo, que
        começa em `catalog_since`, e nem todo filme tem diretor, gênero ou
        país cadastrado."""
        return run_in_app_context(
            catalog_tools.search_movies,
            title=title,
            director=director,
            genre=genre,
            country=country,
            year_from=year_from,
            year_to=year_to,
            cinema=cinema,
            shown_from=shown_from,
            shown_to=shown_to,
            sort=sort,
            limit=limit,
        )


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
