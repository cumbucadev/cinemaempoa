# Edição manual de vínculo TMDB do filme (#284)

## Problema

A pipeline `fetch-movie-metadata` casa filmes com o TMDB automaticamente por
busca de título, sem nunca persistir qual entrada do TMDB foi usada. Quando o
casamento é ambíguo (filmes antigos/obscuros/homônimos), diretor, gêneros e
demais metadados ficam errados — e hoje a única forma de corrigir é editando
o banco de dados diretamente, o que não é viável para um administrador não
técnico.

## Objetivo

Permitir que um admin logado, a partir da interface web, busque o filme
correto no TMDB e vincule manualmente o `Movie` a esse `tmdb_id`, corrigindo
de uma vez diretor, gêneros, título original, ano, idioma e coleção.

### Fora de escopo

- Poster e sinopse: hoje vivem em `Screening`, não em `Movie`, e continuam
  tratados pelo fluxo existente (`fetch-posters` / `poster-review`). A tela
  de edição não mostra nem edita poster.
- Edição manual de campos individuais sem vínculo a um `tmdb_id` (ex.: digitar
  o nome de um diretor à mão). Toda correção passa por escolher a entrada
  certa do TMDB.

## Data model

Adicionar uma coluna nullable e indexada em `Movie`
(`flask_backend/models.py`), via migration (`db-revision --autogenerate`):

- `tmdb_id: Optional[int]` — a entrada específica do TMDB à qual este filme
  está vinculado. `NULL` significa "nunca vinculado explicitamente" (a busca
  automática por título continua valendo na próxima execução da pipeline).
  Sem constraint `UNIQUE`: nada impede duas linhas de `Movie` referenciarem
  o mesmo `tmdb_id` legitimamente (ex. título importado duplicado antes da
  deduplicação), e não há necessidade de reforçar unicidade para esta
  feature.

## Service layer

- **`TMDBClient`** (`flask_backend/service/tmdb.py`): novo método
  `search_movies(title, language="pt-BR", limit=5) -> list[dict]`, com o
  mesmo fallback pt-BR → en-US de `search_movie`, retornando até `limit`
  resultados brutos (`id`, `title`, `original_title`, `release_date`,
  `poster_path`) em vez de só o primeiro. `search_movie` continua existindo
  (usado pela pipeline automática e por `get_poster_url`).
- **Lógica de upsert compartilhada**: extrair o trecho de
  `movie_metadata_pipeline.run_pipeline` que faz upsert de
  diretores/gêneros/países/coleção e atribui `original_title`,
  `release_year`, `original_language` para uma função
  `apply_tmdb_details(movie: Movie, tmdb_id: int, details: dict) -> None` no
  mesmo módulo. Essa função também grava `movie.tmdb_id = tmdb_id`. Tanto
  `run_pipeline()` quanto a nova rota de vínculo manual chamam essa função —
  um único caminho de código, então "vincular" significa sempre a mesma
  coisa, automático ou manual.
- **`run_pipeline()`**: ao processar um filme que já tem `movie.tmdb_id`
  definido, usar `client.get_movie_details(movie.tmdb_id)` diretamente em vez
  de buscar por título (`_try_tmdb`). Isso cobre o caso raro de um filme
  vinculado que ainda não tem diretor (ex. documentário sem diretor creditado
  no TMDB) e que, por isso, continuaria elegível para reprocessamento por
  `get_movies_without_metadata()`.
- `get_manual_review_summary()`: sem mudanças.

## Routes

Novo blueprint `flask_backend/routes/admin/movies.py`, registrado sob
`/admin/movies`, todas as views atrás de `login_required` (mesmo padrão de
`admin/blog.py`):

| Rota | Método | Propósito |
|---|---|---|
| `/admin/movies/<id>` | GET | Página de edição/vínculo de um filme. |
| `/admin/movies/<id>/tmdb-search` | GET (JSON) | `?q=<título>` → chama `TMDBClient.search_movies`, retorna candidatos (id, title, original_title, ano, url do poster miniatura). |
| `/admin/movies/<id>/tmdb-link` | POST | Body `{tmdb_id}` → `get_movie_details` + `apply_tmdb_details`, commit, retorna JSON com os metadados atualizados. |
| `/admin/movies/<id>/tmdb-unlink` | POST | `movie.tmdb_id = None`, commit. Não apaga diretores/gêneros já associados — só desvincula, permitindo re-vínculo ou reprocessamento automático futuro. |

Não há rota de listagem dedicada: `/movies` (`movie.index`,
`flask_backend/routes/movie.py:18`) já pagina e filtra por título via
`?movie=` e já sabe se o usuário está logado (`show_drafts`). Os pontos de
entrada são:

- **`/movie/<slug>`**: link "Editar metadados", visível só quando logado,
  apontando para `/admin/movies/<movie.id>`.
- **`/movies`**: mesmo link em cada linha da listagem, visível só quando
  logado.

## UI / templates

- **`templates/admin/movies/edit.html`** (novo): mostra o estado atual do
  vínculo (título, título original, ano, idioma, diretores, gêneros,
  coleção, e "Vinculado ao TMDB #`<id>`" ou "Não vinculado" — sem poster,
  já que ele pertence à `Screening`, não ao `Movie`), uma caixa de busca
  pré-preenchida com o título atual do filme, e uma área de resultados.
- Busca via `fetch` para `tmdb-search`, renderizando cards de resultado com
  poster miniatura (tamanho `w92`/`w154`), título, título original e ano —
  segue o mesmo padrão leve de fetch+render já usado pelo autocomplete de
  `/movies/search`.
- Clicar num card faz POST para `tmdb-link` com aquele `tmdb_id`; a resposta
  JSON é usada pelo JS para atualizar in-place o bloco de metadados exibido
  na página (sem recarregar), sem passo de confirmação/preview extra.
- Botão "Remover vínculo" (visível só quando `tmdb_id` está definido) faz
  POST para `tmdb-unlink`.
- `movie/index.html` e `movie/show.html`: adicionar o link condicional
  "Editar metadados" (só quando logado).

## Error handling

- **Busca sem resultados**: `tmdb-search` retorna lista vazia; UI mostra
  "Nenhum resultado encontrado" em vez de área vazia.
- **Erro de rede/API do TMDB**: os métodos de `TMDBClient` já levantam
  `requests.RequestException` em falha. As rotas capturam e retornam erro
  JSON (`tmdb-search`) ou flash de erro (`tmdb-link`) — sem escrita parcial,
  já que `apply_tmdb_details` só roda depois que `get_movie_details` tem
  sucesso.
- **`tmdb_id` inválido em `tmdb-link`** (ex.: TMDB retorna 404): mesmo
  tratamento — `get_movie_details` levanta exceção, nada é commitado, admin
  vê o erro e pode buscar de novo.
- **Edições concorrentes**: sem tratamento especial — last write wins,
  consistente com o comportamento atual de `admin/blog.py`.

## Testing

- **Migration**: autogenerate padrão, verificada com `db-upgrade`/
  `db-downgrade`.
- **`flask_backend/tests/test_service/test_movie_metadata_pipeline.py`**:
  estender para cobrir `apply_tmdb_details` diretamente, e o comportamento
  da pipeline de preferir `get_movie_details(tmdb_id)` a busca por título
  quando `movie.tmdb_id` já está definido.
- **Testes de `TMDBClient.search_movies`**: retorna múltiplos candidatos,
  respeita `limit`, faz fallback pt-BR → en-US.
- **Novo `flask_backend/tests/test_routes/test_admin_movies.py`** (seguindo
  o padrão dos testes de `admin/blog.py`): `login_required` aplicado nas 4
  rotas; `tmdb-search` retorna candidatos como JSON; `tmdb-link` persiste
  `tmdb_id` + relações e retorna o estado atualizado; `tmdb-unlink` limpa
  `tmdb_id` sem tocar em diretores/gêneros; caminhos de erro (sem
  resultados, falha do TMDB) retornam respostas sensatas sem escrita
  parcial.
- Verificação manual: rodar o servidor de dev, logar, usar o fluxo
  ponta-a-ponta num filme real contra a API real do TMDB (checagem de
  sanidade, não faz parte da suíte automatizada).
