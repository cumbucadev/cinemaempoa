# Tela unificada de edição de sessão e filme

## Problema

Um admin não técnico, ao notar um erro num card do índice mobile (título
errado, metadados de TMDB errados, imagem errada, descrição errada, datas
erradas), hoje precisa primeiro classificar mentalmente o erro como
pertencente a `Movie` ou a `Screening` antes de conseguir corrigi-lo:

- Datas, imagem, descrição e o campo "Title" ficam em
  `/screening/<id>/update` (acessível via "Edite!" no card).
- Diretor, gêneros, ano, título original e vínculo com TMDB ficam em
  `/admin/movies/<id>`, alcançável só filtrando manualmente em `/movies` até
  achar o filme certo.

Isso é um problema de usabilidade sério por dois motivos:

1. **O campo "Title" em `/screening/<id>/update` tem um efeito colateral
   silencioso e potencialmente destrutivo**: `get_movie_by_title_or_create`
   (`flask_backend/repository/movies.py:103`) faz slug do texto digitado e,
   se bater com o slug de outro `Movie` existente, **reassocia** a sessão a
   ele; se não bater com nada, **cria um `Movie` novo**. Não há confirmação,
   preview ou indicação de qual das duas coisas aconteceu — um admin pode
   fragmentar ou fundir o histórico de sessões de um filme sem perceber.
2. **Não existe um salto único** do lugar onde o erro é percebido (índice
   mobile, `/admin/alerts`) até uma tela que cubra sessão + filme + TMDB.
   Corrigir metadados de TMDB hoje exige abandonar a tela de edição, ir para
   `/movies`, filtrar por título (que ele precisa lembrar de cor), abrir a
   página do filme e só então clicar em "Editar metadados". `/admin/alerts`
   — a outra tela que o admin usa com frequência, exatamente no momento em
   que vai postar o texto nas redes sociais — não tem nenhum link de edição.

## Objetivo

Uma única tela, alcançável em um toque a partir do índice mobile e de
`/admin/alerts`, onde o admin corrige sessão, filme e metadados de TMDB sem
precisar saber que são três entidades diferentes — e onde trocar o filme de
uma sessão é uma ação explícita e confirmada, nunca um efeito colateral de
editar texto.

### Fora de escopo

- Mudança de schema: nenhuma coluna nova é necessária.
- A página `/admin/movies/<id>` (edição de metadados isolada) continua
  existindo como está, para o caso de um filme sem sessão "atual" à mão
  (limpeza em lote, filme com múltiplas sessões). `/movies` e
  `/movies/<slug>` continuam apontando para ela.
- Edição de poster/sinopse fora do que já existe hoje em `Screening`.
- Autenticação/autorização: usa `login_required` como todo o resto do admin,
  sem mudanças.

## Data model

Sem mudanças. A feature reusa `Movie`, `Screening` e as tabelas de relação
já existentes (`flask_backend/models.py:109-209`).

## Repository layer

- **`flask_backend/repository/movies.py`**: `get_movies_with_similar_titles`
  (linha 114) passa a retornar `id` e `release_year` além de `title` (a
  função em si já busca o `Movie` inteiro, só o dict de serialização na rota
  muda — ver Routes). Ganha um parâmetro opcional
  `exclude_movie_id: Optional[int] = None` para a rota poder omitir o filme
  atual da lista de resultados ao buscar substituto.
- **`flask_backend/repository/screenings.py`**: nova função
  `reattach_movie(screening: Screening, movie_id: int) -> None` — só define
  `screening.movie_id = movie_id` e commita, sem tocar em descrição, imagem,
  datas ou status. Fica ao lado da `update()` existente (linha 249), que
  continua sendo usada pelo POST principal do formulário (datas, imagem,
  descrição, status).
- `get_by_title_or_create` (linha 103) é reusado sem alteração pelo branch
  "criar novo filme" da nova rota de troca de filme.

## Routes

**`flask_backend/routes/movie.py`** — `search_movies` (linha 129) estendida:

| Rota | Método | Mudança |
|---|---|---|
| `/movies/search?title=<q>&exclude_movie_id=<id>` | GET | Resposta passa de `[{title}]` para `[{id, title, release_year}]`. `exclude_movie_id` é opcional; quando presente, omite esse filme dos resultados. Consumida hoje por `create.html` (sem `exclude_movie_id`, response shape antiga ignorada pelo JS atual que só lê `.title` — compatível) e pela nova busca de "Trocar filme". |

**`flask_backend/routes/screening.py`** — nova rota:

| Rota | Método | Propósito |
|---|---|---|
| `/screening/<id>/movie` | POST | Body `{"movie_id": int}` **ou** `{"new_title": str}` (exatamente um dos dois). Com `movie_id`: valida que o filme existe (404 se não), no-op se já for o filme atual, senão chama `reattach_movie`. Com `new_title`: chama `get_by_title_or_create` (mesma semântica de hoje — se o slug bater com um filme existente nesse meio-tempo, reassocia a ele em vez de duplicar) e `reattach_movie` com o resultado. Retorna `{"movie": {"id", "title", "slug"}}`. `login_required`. |

**`/screening/<id>/update`** (mesma rota, `screening.py:373`): o POST de
sucesso passa a redirecionar para `url_for("screening.update", id=id)` em
vez de `screening.index` — o admin permanece na mesma tela após salvar, vendo
a mensagem de sucesso (`flash`) como hoje. O campo `movie_title` sai do form:
a seção "Sessão" deixa de tocar em `Movie` inteiramente; troca de filme passa
exclusivamente pela nova rota acima.

`/admin/movies/<id>/tmdb-search`, `tmdb-link`, `tmdb-unlink`
(`flask_backend/routes/admin/movies.py`): sem mudanças de rota — a tela
unificada os chama diretamente usando `screening.movie_id`.

## UI / templates

- **`flask_backend/templates/screening/update.html`**: ganha duas seções
  novas abaixo do form existente (que continua intacto: datas, imagem, alt
  text, descrição, status, "Salvar"):
  - **Filme**: mostra o título atual do filme (texto, não mais input) e um
    botão "Trocar filme". Se o filme tiver mais de uma sessão associada,
    mostra uma nota: *"Este filme tem N sessão(ões) em: `<cinemas>` —
    alterações no filme afetam todas."*
  - **Metadados TMDB**: inclui o mesmo bloco de exibição/busca de
    `movie/admin/edit.html`, parametrizado por `movie` — ver extração de
    partial abaixo.
- **Extração de partial compartilhado**: o bloco de metadados TMDB (display
  + busca + grid de candidatos) de `movie/admin/edit.html` vira um include
  `templates/movie/admin/_metadata_panel.html`, parametrizado por `movie`.
  `movie/admin/edit.html` passa a usar esse include (comportamento idêntico
  ao atual) e `screening/update.html` o inclui também, passando
  `movie=screening.movie`.
- **Extração de JS compartilhado**: o `<script>` inline de
  `movie/admin/edit.html` (busca TMDB, `linkMovie`, unlink — atualmente
  linhas 68-229) vira `flask_backend/static/js/movie-tmdb-metadata.js`,
  lido a partir de uma variável global `movieId` já setada por cada página
  hospedeira (mesmo padrão que o arquivo já usa hoje). Ambas as páginas
  passam a incluir esse arquivo em vez de duplicar o script.
- **"Trocar filme"**: painel/modal pequeno, não editado inline. Ao abrir:
  campo de busca (debounce ~300ms, mínimo 2 caracteres) chamando
  `/movies/search?title=<q>&exclude_movie_id=<movie_id_atual>`, listando
  resultados existentes mais uma linha final "Criar novo filme '`<X>`'"
  quando não há correspondência exata. Selecionar um resultado mostra um
  passo de confirmação inline (sem navegação):
  *"Esta sessão será desvinculada de '`<atual>`' e associada a
  '`<destino>`'. Outras sessões de '`<atual>`' não são afetadas."* / para
  filme novo: *"Nenhum filme encontrado — será criado um novo filme
  '`<X>`'."* Confirmar dispara `POST /screening/<id>/movie`; a resposta
  repinta o título na seção "Filme" e reinicializa a seção "Metadados TMDB"
  (novo `movieId`, novos campos exibidos) — mesmo padrão de repintura que
  `updateMetadataDisplay()` já usa hoje para tmdb-link.
- **`flask_backend/templates/alerts/admin/index.html`**: adiciona um link
  de edição (ícone de lápis com `aria-label="Editar"`, não apenas ícone —
  ver a diretriz de rotulagem do heurísticas de UX) ao lado do botão
  "Copiar", tanto na tabela desktop (`pending_actions` / linha da tabela,
  perto de linha 149) quanto no card mobile (perto de linha 183), apontando
  para `url_for('screening.update', id=row.screening.id)`, mesma aba —
  navegação padrão, sem `target="_blank"`. Como o POST de salvar não navega
  mais para fora da tela de edição, o botão "voltar" do navegador retorna o
  admin para `/admin/alerts` com filtros e posição de scroll intactos.

## Error handling

- **`POST /screening/<id>/movie`**: 400 se nem `movie_id` nem `new_title`
  forem enviados, ou se ambos forem; 404 se `movie_id` não existir; no-op
  (200, sem escrita) se `movie_id` for igual ao filme atual da sessão —
  evita o texto de confirmação sem sentido "desvinculado de X e associado a
  X" (o cliente já pula a confirmação nesse caso, mas o servidor também
  trata defensivamente). Condição de corrida em `new_title` (alguém cria um
  filme com slug igual entre a busca e a confirmação) resolve-se pela
  semântica já existente de `get_by_title_or_create`: reassocia ao filme
  existente em vez de duplicar.
- **TMDB search/link/unlink**: sem mudanças — os erros 502 já tratados em
  `routes/admin/movies.py` continuam valendo, incluindo pela tela unificada,
  já que reusa a mesma função `showError` do JS compartilhado.
- **Filme com 0 sessões** (órfão após uma troca em outro lugar): fora de
  escopo aqui — a página `/admin/movies/<id>` já cobre esse caso, pois não
  depende de nenhuma sessão específica.

## Testing

- **`flask_backend/tests/test_routes/test_screening.py`** (ou novo arquivo):
  `POST /screening/<id>/movie` — exige login; 404 em sessão inexistente;
  reassocia a filme existente por `movie_id`; cria filme novo com
  `new_title` sem correspondência; no-op quando o destino é o filme atual;
  400 quando corpo não tem `movie_id` nem `new_title` ou tem os dois; POST
  de sucesso em `/screening/<id>/update` redireciona para
  `screening.update`, não mais `screening.index`.
- **`flask_backend/tests/test_routes/test_movie.py`**: `search_movies`
  retorna `id`/`release_year` no JSON; `exclude_movie_id` omite o filme
  indicado dos resultados.
- **Smoke manual**: tela unificada renderiza as três seções para uma
  sessão; busca/vínculo de TMDB funciona embutida na tela unificada (não só
  na página isolada); texto de confirmação do "Trocar filme" mostra os
  títulos antigo/novo corretos; link de edição em `/admin/alerts` navega
  corretamente e o botão voltar do navegador retorna com filtros intactos;
  `/admin/movies/<id>` continua funcionando sem mudanças visíveis.
- Rodar suíte completa (`pytest flask_backend/tests`), `uv run ruff check
  --fix`, `uv run ruff format`, `uv run djlint --reformat
  flask_backend/templates --format-css --format-js` antes de considerar a
  spec pronta para virar plano.
