"""The MCP server Orbit's agents call, served over streamable HTTP and
guarded by a static bearer token (ORBIT_MCP_TOKEN). A thin shell over two
families of tools:

- the inspection tools in flask_backend/service/movie_inspection_tools.py,
  each bound to the `request_id` of an inspection request; `apply_verdict`
  writes to the database;
- the read-only catalog tools in flask_backend/service/catalog_tools.py, for
  the conversational agent: what is showing, where and when, and what each
  cinema has shown.

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

    @mcp.tool
    def get_schedule(
        date_from: OptionalText,
        date_to: OptionalText,
        cinema: OptionalText,
    ) -> catalog_tools.Schedule:
        """Devolve a programação: o que cada cinema exibe, dia a dia e com
        horários, num período de até 14 dias. Use para "o que está passando
        hoje?", "o que tem no fim de semana na Sala Redenção?", "que horas
        passa X amanhã?". Para o histórico (o que já passou, quando foi a
        última vez), para períodos maiores ou para filtrar por diretor,
        gênero ou país, prefira search_movies.

        Todos os parâmetros são opcionais e se combinam com E:
        - `date_from`: primeiro dia, AAAA-MM-DD; sem ele, vale hoje;
        - `date_to`: último dia, AAAA-MM-DD, inclusivo; sem ele, vale o mesmo
          dia de `date_from`. O período não pode passar de 14 dias;
        - `cinema`: slug ou nome do cinema (veja list_cinemas), sem
          diferenciar acentos nem maiúsculas; sem ele, vêm todos os cinemas.

        `today` é a data de hoje em Porto Alegre: use-a para calcular
        "amanhã" ou "sábado" antes de chamar de novo. `cinemas` vem em ordem
        de nome e traz só os cinemas com sessão no período; os filmes de cada
        cinema vêm pela ordem da primeira sessão. Em `sessions`, `times` são
        os horários do dia; uma lista vazia significa que o cinema não
        informou o horário, não que não há sessão. `url` é a página do filme
        no site. `total` é o número de pares cinema × filme no período e
        `truncated` diz se a lista foi cortada (o corte é em 60 pares):
        nesse caso, reduza o período ou informe `cinema`.

        Uma lista vazia significa que não há sessão cadastrada nesses dias:
        a programação futura só existe até onde os cinemas já a divulgaram,
        e nem todo filme tem diretor ou gênero cadastrado."""
        return run_in_app_context(
            catalog_tools.get_schedule,
            date_from=date_from,
            date_to=date_to,
            cinema=cinema,
        )

    @mcp.tool
    def list_cinemas() -> catalog_tools.CinemaList:
        """Lista os cinemas acompanhados pelo site, com endereço, horário de
        funcionamento e links, e diz a data de hoje e o que o catálogo cobre.
        Comece por aqui sempre que precisar da data de hoje ("hoje",
        "amanhã", "no fim de semana") ou transformar o nome de um cinema no
        `slug` que as outras ferramentas aceitam ("Capitólio" →
        `capitolio`). Também responde "onde fica a Sala Redenção?" e "quais
        cinemas vocês acompanham?". Não recebe parâmetros.

        `today` é a data de hoje em Porto Alegre, no formato AAAA-MM-DD,
        como todas as datas. `catalog_since` e `catalog_until` são a
        primeira e a última data com sessão cadastrada: o catálogo não sabe
        de nada antes de `catalog_since`, e depois de hoje só conhece o que
        os cinemas já divulgaram. `metadata_coverage` diz, entre os
        `movies_total` filmes do catálogo, quantos têm vínculo com o TMDB
        (`with_tmdb`), diretor (`with_directors`), gênero (`with_genres`) e
        país (`with_countries`) cadastrados: os demais não aparecem em
        buscas por esses campos.

        Em cada cinema, `website` é o site do próprio cinema, `page_url` é a
        página dele no cinemaempoa e `short_name` é o nome usado no dia a
        dia. Endereço, horário e Instagram podem vir nulos."""
        return run_in_app_context(catalog_tools.list_cinemas)

    @mcp.tool
    def get_movie(movie_id: int) -> catalog_tools.MovieDetails:
        """Devolve os detalhes de um filme do catálogo e todas as sessões
        dele, cinema por cinema. Use depois de search_movies ou get_schedule,
        que informam o `movie_id`, para responder "quando passa de novo?",
        "onde passou?", "que horas é a sessão?" ou para ler a sinopse
        publicada pelo cinema. Para procurar um filme pelo nome, use
        search_movies. `movie_id` é obrigatório.

        `today` é a data de hoje em Porto Alegre; as datas são AAAA-MM-DD.
        `screenings` tem uma entrada por cinema que exibiu ou vai exibir o
        filme, em ordem de nome do cinema (um cinema pode aparecer mais de
        uma vez, se cadastrou o filme em mais de uma ocasião):
        - `cinema` é o slug e `cinema_name` o nome;
        - `description` é o texto do cinema sobre a sessão, cortado em 1500
          caracteres, e `source_url` é a página de origem;
        - `upcoming` são as datas de hoje em diante, com os horários (lista
          vazia de `times` significa horário não informado), até 30 datas;
          `upcoming_total` é o total delas;
        - `past_first`, `past_last` e `past_count` resumem as datas
          anteriores a hoje: a primeira, a última e quantas foram.

        Se `upcoming` vier vazio em todos os cinemas, o filme não tem nova
        sessão divulgada. O histórico vale só para o período coberto pelo
        catálogo (veja `catalog_since` em list_cinemas), e nem todo filme
        tem diretor, gênero ou país cadastrado. Um `movie_id` inexistente
        devolve erro."""
        return run_in_app_context(catalog_tools.get_movie, movie_id)

    @mcp.tool
    def search_directors(
        query: str, limit: int = 10
    ) -> catalog_tools.DirectorSearchResult:
        """Procura diretores pelo nome entre os que têm filme no catálogo.
        Use para desfazer ambiguidades antes de search_movies: "Coppola" pode
        ser Francis Ford, Sofia ou Gia. Para listar os filmes de um diretor,
        use search_movies com `director`.

        `query` é obrigatório: um trecho do nome, sem diferenciar acentos nem
        maiúsculas ("agnes" encontra "Agnès Varda"). `limit` é opcional
        (padrão 10, até 30).

        Cada diretor vem com `name`, `movie_count` (quantos filmes dele têm
        sessão no catálogo) e `sample_titles` (até 3 títulos, os de exibição
        mais recente). A ordem é do diretor com mais filmes para o com
        menos. `total` é o número de diretores encontrados e `truncated` diz
        se a lista foi cortada.

        Uma lista vazia significa só que nenhum filme do catálogo tem um
        diretor com esse nome cadastrado: o catálogo cobre o período
        informado por list_cinemas (`catalog_since`), e nem todo filme tem
        diretor cadastrado."""
        return run_in_app_context(catalog_tools.search_directors, query, limit)

    @mcp.tool
    def get_catalog_stats(
        group_by: catalog_tools.StatsGroupBy,
        cinema: OptionalText,
        date_from: OptionalText,
        date_to: OptionalText,
        limit: int = 10,
    ) -> catalog_tools.CatalogStats:
        """Conta filmes e sessões do catálogo por grupo. Use para perguntas
        de quantidade e de ranking: "que gênero mais passa na Sala
        Redenção?", "quais diretores mais passaram em 2025?", "quantos
        filmes o Capitólio exibiu em 2025?". Para saber quais são os filmes,
        use search_movies.

        `group_by` é obrigatório: `genre`, `director`, `country`, `cinema`
        ou `month`. Os outros parâmetros são opcionais, se combinam com E e
        definem quais sessões contam:
        - `cinema`: slug ou nome do cinema (veja list_cinemas), sem
          diferenciar acentos nem maiúsculas;
        - `date_from` / `date_to`: período AAAA-MM-DD, inclusivo; sem eles,
          vale o catálogo inteiro, sessões futuras incluídas (use `today`,
          de list_cinemas, em `date_to` para contar só o que já passou);
        - `limit`: quantos grupos devolver (padrão 10, até 50).

        Cada grupo traz `key` (nome do gênero, do diretor ou do país, slug
        do cinema ou mês `AAAA-MM`), `movies` (filmes distintos) e
        `sessions` (quantidade de datas de sessão). Um filme com dois
        gêneros conta nos dois grupos, então a soma de `movies` pode passar
        de `movies_in_scope`, que é o total de filmes distintos no recorte.
        A ordem é de `movies` decrescente; com `month`, é cronológica.
        `total_groups` é o número de grupos antes do corte e `truncated`
        diz se houve corte.

        Exemplo: quantos filmes o Capitólio exibiu em 2025 →
        `group_by="cinema", cinema="capitolio", date_from="2025-01-01",
        date_to="2025-12-31"` e leia `movies`.

        Com `genre`, `director` ou `country`, `movies_without_value` diz
        quantos filmes do recorte não têm esse dado cadastrado e por isso
        ficaram fora de todos os grupos. Os números valem só para o período
        coberto pelo catálogo (veja `catalog_since` em list_cinemas)."""
        return run_in_app_context(
            catalog_tools.get_catalog_stats,
            group_by,
            cinema=cinema,
            date_from=date_from,
            date_to=date_to,
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
