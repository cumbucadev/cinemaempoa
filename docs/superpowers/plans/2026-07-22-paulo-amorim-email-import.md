# Paulo Amorim Newsletter Email Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second, independent ingestion path for Cinemateca Paulo Amorim's programming — reading its weekly newsletter email and extracting screenings with an LLM — additive to the existing HTML scraper (issue #251).

**Architecture:** A new scraper class (`PauloAmorimEmail`) connects to a dedicated Gmail mailbox over IMAP (`imap-tools`), reads unread newsletter emails, strips them to text, and hands the text to a new LLM extractor (`PauloAmorimEmailExtractorLLM`) that follows the same `Movie`/`Movies` schema already used by `CineBancariosExtractorLLM`/`CineCincoExtractorLLM`. Output flows through the existing `import-json` → `run-dedupper` pipeline unchanged, registered under a new room key `paulo-amorim-email` that writes to the existing `paulo-amorim` cinema slug. A new daily GitHub Actions workflow triggers it.

**Tech Stack:** Python 3.14, Flask, SQLAlchemy, llama-index + google-genai (Gemini), BeautifulSoup, `imap-tools` (new dependency), pytest, uv.

## Global Constraints

- Use **uv** for all dependency/environment management (`uv add`, `uv run`).
- Follow existing scraper conventions exactly: `scrapers/cinebancarios.py`, `scrapers/llms.py`, `scrapers/llm_cache.py` are the reference implementations for this feature.
- Run `uv run ruff check --fix` and `uv run ruff format` before each commit; this repo's CI fails on unformatted code.
- Never fabricate data in LLM prompts or extraction output — missing fields become empty strings, not guesses (existing convention in `CineCincoExtractorLLM`'s prompt).
- Design spec: `docs/superpowers/specs/2026-07-22-paulo-amorim-email-import-design.md`.

---

## Task 1: `PauloAmorimEmailExtractorLLM` (LLM extraction logic)

**Files:**
- Modify: `scrapers/llms.py` (append new class after `CineCincoExtractorLLM`)
- Test: `tests/scrapers/test_llms.py` (append new test classes after the existing CineCinco test classes)

**Interfaces:**
- Consumes: `Movie`/`Movies` (pydantic models already in `scrapers/llms.py`), `_build_llm(model_name)` (already in `scrapers/llms.py`), `GEMINI_API_KEY` (from `flask_backend.env_config`, already imported in `scrapers/llms.py`).
- Produces: `PauloAmorimEmailExtractorLLM(model_name)` with method `extract_screenings_from_text(str_received_date: str, text: str) -> str | None`. `str_received_date` is an RFC-2822-formatted date string (e.g. `"Wed, 22 Jul 2026 10:15:00 +0000"`) — the email's `Date` header, used the same way `CineBancariosExtractorLLM.extract_screenings_from_text` uses `strPubDate`. Returns a JSON string matching `Movies` schema, or `None` on failure (rate limit or any other exception).

This class mirrors `CineBancariosExtractorLLM` exactly in shape (same `__init__`, `_get_llm`, error handling), differing only in prompt content.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scrapers/test_llms.py`. First update the import line at the top of the file:

```python
from scrapers.llms import (
    CineBancariosExtractorLLM,
    CineCincoExtractorLLM,
    PauloAmorimEmailExtractorLLM,
)
```

Then append these classes at the end of the file:

```python
def _make_paulo_amorim_email_extractor():
    with (
        patch.object(
            PauloAmorimEmailExtractorLLM, "_get_llm", return_value=MagicMock()
        ),
        patch("scrapers.llms.Settings"),
    ):
        return PauloAmorimEmailExtractorLLM("gemini-2.5-flash")


class TestPauloAmorimEmailExtractorLLMGetLlm:
    def test_gemini_without_api_key_raises_value_error(self):
        with (
            patch("scrapers.llms.GEMINI_API_KEY", None),
            pytest.raises(ValueError, match="GEMINI_API_KEY is not set"),
        ):
            PauloAmorimEmailExtractorLLM("gemini-2.5-flash")

    def test_gemini_with_api_key_builds_google_genai_client(self):
        with (
            patch("scrapers.llms.GEMINI_API_KEY", "fake-key"),
            patch("llama_index.llms.google_genai.GoogleGenAI") as mock_cls,
            patch("scrapers.llms.Settings"),
        ):
            PauloAmorimEmailExtractorLLM("gemini-2.5-flash")
        mock_cls.assert_called_once_with(model="gemini-2.5-flash", api_key="fake-key")


class TestPauloAmorimEmailExtractScreeningsFromText:
    def test_success_returns_raw_json(self):
        extractor = _make_paulo_amorim_email_extractor()
        mock_response = MagicMock()
        mock_response.raw.model_dump_json.return_value = '{"movies": []}'
        extractor.llm.as_structured_llm.return_value.chat.return_value = mock_response

        result = extractor.extract_screenings_from_text(
            "Wed, 22 Jul 2026 10:15:00 +0000", "some newsletter text"
        )

        assert result == '{"movies": []}'

    def test_rate_limit_error_returns_none(self):
        extractor = _make_paulo_amorim_email_extractor()
        extractor.llm.as_structured_llm.return_value.chat.side_effect = (
            GoogleGenAIClientError(code=429, response_json={})
        )

        result = extractor.extract_screenings_from_text(
            "Wed, 22 Jul 2026 10:15:00 +0000", "some newsletter text"
        )

        assert result is None

    def test_generic_exception_returns_none(self):
        extractor = _make_paulo_amorim_email_extractor()
        extractor.llm.as_structured_llm.return_value.chat.side_effect = Exception(
            "boom"
        )

        result = extractor.extract_screenings_from_text(
            "Wed, 22 Jul 2026 10:15:00 +0000", "some newsletter text"
        )

        assert result is None


class TestPauloAmorimEmailPromptBuilders:
    def test_get_system_prompt_includes_year_and_rooms(self):
        extractor = _make_paulo_amorim_email_extractor()
        prompt = extractor._get_system_prompt(2026)
        assert "2026" in prompt
        assert "Sala Eduardo Hirtz" in prompt
        assert "Sinopse:" in prompt

    def test_get_prompt_builds_system_and_user_messages(self):
        extractor = _make_paulo_amorim_email_extractor()
        messages = extractor._get_prompt(2026, "some newsletter text")
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "some newsletter text"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scrapers/test_llms.py -v -k PauloAmorimEmail`
Expected: FAIL with `ImportError: cannot import name 'PauloAmorimEmailExtractorLLM'`

- [ ] **Step 3: Implement `PauloAmorimEmailExtractorLLM`**

Append to `scrapers/llms.py`, after the `CineCincoExtractorLLM` class:

```python
class PauloAmorimEmailExtractorLLM:
    def __init__(self, model_name):
        self.model_name = model_name
        self.llm = self._get_llm()
        Settings.llm = self.llm

    def _get_llm(self):
        return _build_llm(self.model_name)

    def extract_screenings_from_text(self, str_received_date, text):
        # str_received_date is the email's Date header,
        # e.g. "Wed, 22 Jul 2026 10:15:00 +0000"
        received_date = datetime.strptime(
            str_received_date, "%a, %d %b %Y %H:%M:%S %z"
        )
        year = received_date.year
        try:
            response = self.llm.as_structured_llm(Movies).chat(
                self._get_prompt(year, text)
            )
        except Exception as e:
            print(f"Error: {e}")
            if isinstance(e, GoogleGenAIClientError) and e.code == 429:
                print("LLM rate limit exceeded. Exiting...")
            return
        return response.raw.model_dump_json()

    def _get_system_prompt(self, year):
        return f"""You are a cinema programming auditor for "Cinemateca Paulo Amorim", a cinema in Porto Alegre, Brazil with three screening rooms: Sala Paulo Amorim, Sala Eduardo Hirtz and Sala Norberto Lubisco. You need to collect screening information from the following text, which is the cinema's weekly newsletter email.
The email begins with a title in the format "PROGRAMAÇÃO DE <day> A <day> DE <month> DE <year>", stating the date range covered that week, sometimes followed by a global note such as "SEGUNDA-FEIRA NÃO HÁ SESSÕES" (meaning NO film has any session at all on that weekday, for the whole week), and then a few paragraphs of prose highlighting some of the films - these intro paragraphs are NOT movies, ignore them. The rest of the text is organized into sections per screening room (headings like "SALA PAULO AMORIM", "SALA EDUARDO HIRTZ", "SALA NORBERTO LUBISCO"), each containing one block of text per movie. The email ends with ticket pricing information and a signature - these are NOT movies, ignore them too.
For each movie, extract the following information:
1. Title: The movie's name, given in caps at the start of its block. It may be prefixed by a label like "ESTREIA:", "REESTREIA:", "SESSÃO NOSTALGIA:", "SESSÃO VITRINE:" or "ESPECIAL:" - do not include these labels in the title.
2. Image URL: these emails never include per-movie poster images - always return an empty string.
3. General Info: Information in the format "Country/Genre/Year/Duration" (e.g. "Brasil/Drama/2025/86min"), using the country/year/duration found in parentheses right after the title (e.g. "(Itália/França, 2025, 110min)") and the genre found at the end of the line right after that (e.g. "Legendado. Drama."). Append " | " followed by the room name(s) the movie plays in (e.g. "Brasil/Drama/2025/86min | Sala Paulo Amorim").
4. Director: The director's name, found after "Direção de" or "Direção:".
5. Classification: The age rating, found right after the distributor name (e.g. "14 anos", "16 anos", or "Livre").
6. Excerpt: The movie's synopsis, found after "Sinopse:".
7. Screening Dates: One or more sessions. Each movie has a "Sessões:" or "Sessão:" line giving a time (e.g. "14h45min", "19h"). By default, that time applies to every day of the newsletter's date range EXCEPT any weekday excluded by the global note (e.g. "SEGUNDA-FEIRA NÃO HÁ SESSÕES" excludes every Monday in the range). Watch for exceptions written in parentheses (or after a comma) next to the time:
   - "não haverá exibição no dia N" / "não haverá exibições nos dias N e M" excludes those specific dates from the default range.
   - "exibições nos dias N e M" / "exibições apenas no dia N" restricts the movie to ONLY those specific dates (ignore the default range entirely for this movie).
   A session may also be scoped to a single day directly (e.g. "Sessão: dia 28 (terça), às 19h" means only that one date).
   Convert every resulting screening into "YYYY-MM-DD HH:MM" format. Use {year} as the year unless the "PROGRAMAÇÃO DE ... A ... DE <year>" header states a different year explicitly, and take care with month rollovers when the date range spans two months.
Make sure to:
- Extract all available information for each movie
- If the exact same movie title appears in more than one room section, merge all its occurrences into a SINGLE entry: combine every screening date/time from every room into one screening_dates list, use the general_info/director/classification/excerpt from its first occurrence, and list every distinct room it plays in in the general_info room list.
- Handle cases where some information might be missing - use an empty string, never fabricate data
- Return the data in JSON format that matches the following structure:

If no movies are found, return an empty list."""

    def _get_prompt(self, year, text_content):
        messages = [
            ChatMessage(role="system", content=self._get_system_prompt(year)),
            ChatMessage(role="user", content=text_content),
        ]
        return messages
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scrapers/test_llms.py -v -k PauloAmorimEmail`
Expected: PASS (8 tests)

- [ ] **Step 5: Lint and format**

Run: `uv run ruff check --fix scrapers/llms.py tests/scrapers/test_llms.py && uv run ruff format scrapers/llms.py tests/scrapers/test_llms.py`

- [ ] **Step 6: Commit**

```bash
git add scrapers/llms.py tests/scrapers/test_llms.py
git commit -m "feat: add PauloAmorimEmailExtractorLLM for newsletter email extraction"
```

---

## Task 2: `PauloAmorimEmail` scraper (IMAP fetch + extraction orchestration)

**Files:**
- Create: `scrapers/paulo_amorim_email.py`
- Modify: `flask_backend/env_config.py` (add mailbox config vars)
- Modify: `example.env` (document new vars)
- Modify: `.gitignore` (add `paulo-amorim-email/` cache dir)
- Modify: `pyproject.toml` / `uv.lock` (via `uv add imap-tools`)
- Test: `tests/scrapers/test_paulo_amorim_email.py`
- Test fixture: `tests/files/files_paulo_amorim_email/newsletter.html`

**Interfaces:**
- Consumes: `PauloAmorimEmailExtractorLLM` (Task 1), `hash_text`/`load_cache`/`save_cache` (already in `scrapers/llm_cache.py`), `PAULO_AMORIM_EMAIL_ADDRESS`/`PAULO_AMORIM_EMAIL_APP_PASSWORD`/`PAULO_AMORIM_NEWSLETTER_SENDER_EMAIL` (new vars this task adds to `flask_backend/env_config.py`).
- Produces: `PauloAmorimEmail()` with method `get_weekly_features_json() -> list[dict]`, returning the same movie-dict shape as `CinematecaPauloAmorim.get_weekly_features_json()` (`poster`, `time`, `title`, `director`, `classification`, `general_info`, `excerpt`, `read_more` keys) — this is what Task 3 wires into `cinemaempoa.py`.

### Step 0: Add the dependency and confirm the real `imap-tools` API

`imap-tools`'s exact keyword-argument names for search/flagging aren't verifiable from this repo, so confirm them against the installed library before writing code against them.

- [ ] **Step 0a: Add the dependency**

Run: `uv add imap-tools`
Expected: `pyproject.toml` and `uv.lock` updated, command exits 0.

- [ ] **Step 0b: Confirm the API surface**

Run:
```bash
uv run python -c "
from imap_tools import MailBox, AND, MailMessageFlags
import inspect
print(inspect.signature(MailBox.fetch))
print(inspect.signature(MailBox.flag))
print(inspect.signature(AND))
"
```
Expected: output showing `fetch`'s signature includes a `mark_seen` parameter, `flag`'s signature accepts `(self, messages, flag_set, value, ...)`, and `AND`/search criteria accept a `from_` keyword for filtering by sender and `seen` for the `\Seen` flag. **If any of these names differ from what's used below, adjust Steps 3–4 of this task to match the real signatures before proceeding** — do not silently keep the code below if it doesn't match reality.

### Step 1: Add mailbox config

- [ ] **Step 1a: Add config vars**

In `flask_backend/env_config.py`, add after the `TMDB_API_TOKEN` line:

```python
PAULO_AMORIM_EMAIL_ADDRESS = config("PAULO_AMORIM_EMAIL_ADDRESS", default=None)
PAULO_AMORIM_EMAIL_APP_PASSWORD = config(
    "PAULO_AMORIM_EMAIL_APP_PASSWORD", default=None
)
PAULO_AMORIM_NEWSLETTER_SENDER_EMAIL = config(
    "PAULO_AMORIM_NEWSLETTER_SENDER_EMAIL", default=None
)  # sender address to filter for in the mailbox; fill in once the newsletter is subscribed to
```

- [ ] **Step 1b: Document the vars**

In `example.env`, add after the `TMDB_API_TOKEN` line:

```
PAULO_AMORIM_EMAIL_ADDRESS=youremail@gmail.com # dedicated mailbox subscribed to the Paulo Amorim newsletter
PAULO_AMORIM_EMAIL_APP_PASSWORD=yourgmailapppassword # Gmail app password for IMAP access
PAULO_AMORIM_NEWSLETTER_SENDER_EMAIL=newsletter@example.com # sender address of the Paulo Amorim newsletter, used to filter the inbox
```

- [ ] **Step 1c: Ignore the new cache dir**

In `.gitignore`, add `paulo-amorim-email/` after the `paulo-amorim/` line.

- [ ] **Step 1d: Commit**

```bash
git add flask_backend/env_config.py example.env .gitignore pyproject.toml uv.lock
git commit -m "feat: add imap-tools dependency and mailbox config for Paulo Amorim email import"
```

### Step 2: Build the test fixture

- [ ] **Step 2a: Create the fixture file**

Create `tests/files/files_paulo_amorim_email/newsletter.html` with this content (a realistic approximation of the newsletter's HTML — one `<p>` per paragraph, built from a real newsletter email — exact source markup wasn't available, only the rendered text):

```html
<html>
<body>
<p>CINEMATECA PAULO AMORIM<br>PROGRAMAÇÃO DE 23 A 29 DE JULHO DE 2026<br>SEGUNDA-FEIRA NÃO HÁ SESSÕES</p>
<p>A última cinesemana de julho destaca a estreia da produção gaúcha FUTURO FUTURO, quarto longa-metragem do diretor Davi Pretto e consagrado com os principais prêmios do Festival de Brasília 2025. Outra novidade é PEQUENAS CRIATURAS, novo filme da diretora Anne Pinheiro Guimarães e que traz uma história ambientada em Brasília na década de 1980.</p>
<p>A programação segue com vários filmes elogiados, como o longa-metragem francês A DIVINA SARAH BERNHARDT, em que Sandrine Kiberlain dá vida a uma das maiores atrizes de todos os tempos; e também O CONVITE, da diretora Olivia Wilde, campeão absoluto de público e que coloca em cena dois casais que discutem as relações. Também continuam em exibição dois títulos baseados na vida e obra de grandes autores: FRANZ é uma elogiada produção da polonesa Agnieszka Holland sobre o escritor Franz Kafka, enquanto FANON destaca o trabalho do psiquiatra Franz Fanon na Argélia.</p>
<p>Esta é a última semana para conferir os longas PRIMAVERA, do cineasta italiano Damiano Michieletto, e UMA INFÂNCIA ALEMÃ, em que o cineasta Fatih Akin mostra as consequências da guerra a partir do olhar de um menino de 12 anos.</p>
<p>Entre as sessões especiais deste final de mês estão PINK FLOYD – THE WALL, clássico da década de 1980 escolhido para a Sessão Nostalgia, além do segundo programa do ciclo PRESERVAÇÃO E HISTÓRIA DO CINEMA GAÚCHO, com títulos restaurados do acervo audiovisual do Museu de Comunicação Social Hipólito José da Costa.</p>
<p>Confira nossa programação completa e o Portal do Cinema Gaúcho em www.cinematecapauloamorim.com.br</p>
<p>SALA PAULO AMORIM</p>
<p>PRIMAVERA (Itália/França, 2025, 110min). Direção de Damiano Michieletto, com Tecla Insolia, Michele Riondino, Stefano Accorsi. Imagem Filmes, 14 anos. Legendado. Drama.</p>
<p>Sinopse: Cecília é uma das muitas jovens que vivem no orfanato Ospedale della Pietà, que também funciona como conservatório e abriga uma orquestra respeitada na cidade de Veneza, em meados do século XVIII. Com talento para o violino, a jovem começa a estudar com Antonio Vivaldi, que lecionou na escola durante três décadas.</p>
<p>Sessões: 14h45min (não haverá exibição no dia 26, domingo)</p>
<p>O CONVITE (The invite - EUA, 2025, 107min). Direção de Olivia Wilde, com Olivia Wilde, Penélope Cruz, Seth Rogen, Edward Norton. O2 Play, 16 anos. Legendado. Drama</p>
<p>Sinopse: Joe e Angela enfrentam os desafios de um casamento que está desgastado. Quando Hawk e Pinã, os novos vizinhos do andar de cima, chegam para jantar, não demora para que o caos se instale.</p>
<p>Sessões: 17h</p>
<p>ESTREIA: FUTURO, FUTURO (Brasil, 2025, 86min). Direção de Davi Pretto, com Zé Maria Pescador, João Carlos Castanha, Carlota Joaquina, Clara Choveaux. Cajuína Filmes. 16 anos. Drama.</p>
<p>Sinopse: Em um futuro próximo e chuvoso, um homem sem memória conhecido como K embarca em uma jornada trágica e absurda para tentar encontrar o seu lugar no mundo.</p>
<p>Sessões: 19h15min (exibições nos dias 23 e 24 – quinta e sexta, seguidas de debate com o diretor, equipe e convidados).</p>
<p>FRANZ (Franz – República Tcheca/Polônia/Alemanha/França/Turquia, 2025, 127min). Direção de Agnieszka Holland, com Idan Weiss, Daniel Dongres, Jenovéfa Boková, Carol Schuler. A2 Filmes, 14 anos. Legendado. Drama</p>
<p>Sinopse: Um dos escritores mais icônicos e estudados do século XX, Franz Kafka (1883 – 1924) transcreveu em sua obra todas as angústias, dilemas e vivências dos seus 40 anos de vida.</p>
<p>Sessões: 19h15min (exibições nos dias 25, 26, 28 e 29 – de sábado a quarta-feira)</p>
<p>SESSÃO NOSTALGIA: PINK FLOYD - THE WALL (Reino Unido, 1982, 95min). Direção de Alan Parker, com Bob Geldof.</p>
<p>Sinopse: No mês do rock, o destaque é o longa baseado no álbum "The Wall" (1979), da banda britânica Pink Floyd.</p>
<p>Sessão: dia 26 (domingo), às 14h15min. Ingressos a R$ 10,00.</p>
<p>SALA EDUARDO HIRTZ</p>
<p>UMA INFÂNCIA ALEMÃ (Amrum - Alemanha, 2025, 93min). Direção de Fatih Akin, com Jasper Billerbeck, Diane Kruger, Laura Tonke. Imovision, 14 anos. Legendado. Drama.</p>
<p>Sinopse: Na primavera de 1945, a maioria dos moradores da isolada ilha de Amrum, no norte da Alemanha, vibra com as notícias do fim da guerra.</p>
<p>Sessões: 15h</p>
<p>FRANZ (Franz – República Tcheca/Polônia/Alemanha/França/Turquia, 2025, 127min). Direção de Agnieszka Holland, com Idan Weiss, Daniel Dongres, Jenovéfa Boková, Carol Schuler. A2 Filmes, 14 anos. Legendado. Drama</p>
<p>Sinopse: Um dos escritores mais icônicos e estudados do século XX, Franz Kafka (1883 – 1924) transcreveu em sua obra todas as angústias, dilemas e vivências dos seus 40 anos de vida.</p>
<p>Sessões: 16h45min (exibições nos dias 23 e 24 – quinta e sexta)</p>
<p>ESTREIA: FUTURO, FUTURO (Brasil, 2025, 86min). Direção de Davi Pretto, com Zé Maria Pescador, João Carlos Castanha, Carlota Joaquina, Clara Choveaux. Cajuína Filmes. 16 anos. Drama.</p>
<p>Sinopse: Num futuro próximo e chuvoso, um homem sem memória conhecido como K embarca em uma jornada trágica e absurda para tentar encontrar o seu lugar no mundo.</p>
<p>Sessões: 16h45min (exibições nos dias 25, 26, 28 e 29 – de sábado a quarta-feira)</p>
<p>A DIVINA SARAH BERNHARDT (Sarah Bernhardt, La Divine - França, 2024, 98min). Direção de Guillaume Nicloux, com Sandrine Kiberlain, Laurent Lafitte, Amira Casar. Imovision, 16 anos. Legendado. Drama</p>
<p>Sinopse: A atriz francesa Sarah Bernhardt (1844 - 1923) foi uma mulher à frente do seu tempo.</p>
<p>Sessões: 19h (não haverá exibições nos dias 28 e 29 – terça e quarta)</p>
<p>SESSÃO VITRINE: CRIADAS (Brasil, 2025, 105min). Direção de Carol Rodrigues, com Ana Flavia Cavalcanti, Mawusi Tulani. Sessão Vitrine Petrobras, 14 anos. Drama.</p>
<p>Sinopse: Sandra retorna à casa de sua prima Mariana em busca de uma foto de sua falecida mãe, que trabalhou ali como empregada.</p>
<p>Sessão: dia 28 (terça), às 19h, seguida de debate com integrantes do Cineclube Academia das Musas. Entrada franca, com distribuição de senhas uma hora antes da sessão.</p>
<p>SALA NORBERTO LUBISCO</p>
<p>REESTREIA: XICA DA SILVA (Brasil, 1976, 117min). Direção de Cacá Diegues, com Zezé Motta, Walmor Chagas. Sessão Vitrine Petrobras, 16 anos. Comédia dramática.</p>
<p>Sinopse: Em comemoração aos seus 50 anos de estreia, "Xica da Silva" retorna aos cinemas em uma versão restaurada em 4K.</p>
<p>Sessões: 14h30min (não haverá exibições nos dias 28 e 29 – terça e quarta)</p>
<p>ESTREIA: PEQUENAS CRIATURAS (Brasil, 2025, 100min). Direção de Anne Pinheiro Guimarães, com Carolina Dieckmann, Letícia Sabatella, Caco Ciocler. Filmes do Estação, 16 anos.</p>
<p>Sinopse: Em 1986, Helena se muda com a família para Brasília.</p>
<p>Sessões: 16h30min</p>
<p>FANON (França/Luxemburgo/Canadá/Bélgica, 2024, 132min). Direção de Jean-Claude Flamand-Barny, com Alexandre Bouyer, Déborah François, Stanislas Merhar. Fênix Filmes, 16 anos. Legendado. Drama.</p>
<p>Sinopse: Psiquiatra e filósofo político, Frantz Fanon (1925 - 1961) nasceu na ilha da Martinica e se tornou conhecido a partir do seu trabalho em um hospital psiquiátrico da Argélia.</p>
<p>Sessões: 18h45min</p>
<p>PREÇOS DOS INGRESSOS: TERÇAS, QUARTAS e QUINTAS-FEIRAS: R$ 16,00 (R$ 8,00 – ESTUDANTES E MAIORES DE 60 ANOS). SEXTAS, SÁBADOS, DOMINGOS, FERIADOS: R$ 20,00 (R$ 10,00 - ESTUDANTES E MAIORES DE 60 ANOS).</p>
<p>Mônica Kanitz (jornalista MTb. 8103)<br>Direção e curadoria da Cinemateca Paulo Amorim – SEDAC<br>Rua dos Andradas, 736 – Porto Alegre RS<br>www.cinematecapauloamorim.com.br</p>
</body>
</html>
```

- [ ] **Step 2b: Commit the fixture**

```bash
git add tests/files/files_paulo_amorim_email/newsletter.html
git commit -m "test: add Paulo Amorim newsletter email fixture"
```

### Step 3: Write the failing tests for `PauloAmorimEmail`

- [ ] **Step 3a: Write the test file**

Create `tests/scrapers/test_paulo_amorim_email.py`:

```python
import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from scrapers.llm_cache import hash_text
from scrapers.paulo_amorim_email import PauloAmorimEmail


def _make_message(uid, html, date):
    msg = MagicMock()
    msg.uid = uid
    msg.html = html
    msg.text = ""
    msg.date = date
    return msg


class TestGetTextFromHtml:
    def test_strips_tags_and_returns_plain_text(self, tmp_path):
        scraper = PauloAmorimEmail()
        scraper.dir = str(tmp_path)
        html = "<html><body><p>FRANZ</p><script>ignored()</script></body></html>"

        text = scraper._get_text_from_html(html)

        assert "FRANZ" in text
        assert "ignored()" not in text

    def test_real_newsletter_fixture_contains_expected_movies(self):
        scraper = PauloAmorimEmail()
        with open("tests/files/files_paulo_amorim_email/newsletter.html") as f:
            html = f.read()

        text = scraper._get_text_from_html(html)

        assert "FUTURO, FUTURO" in text
        assert "SALA EDUARDO HIRTZ" in text
        assert "Sinopse:" in text
        assert "ignored()" not in text


class TestGetWeeklyFeaturesJson:
    def _make_scraper(self, tmp_path):
        scraper = PauloAmorimEmail()
        scraper.dir = str(tmp_path)
        return scraper

    def test_no_unread_messages_returns_empty_list(self, tmp_path):
        scraper = self._make_scraper(tmp_path)
        mock_mailbox = MagicMock()
        mock_mailbox.fetch.return_value = []

        with patch("scrapers.paulo_amorim_email.MailBox") as mock_mailbox_cls:
            mock_mailbox_cls.return_value.login.return_value.__enter__.return_value = (
                mock_mailbox
            )
            result = scraper.get_weekly_features_json()

        assert result == []
        mock_mailbox.flag.assert_not_called()

    def test_successful_extraction_marks_message_seen(self, tmp_path):
        scraper = self._make_scraper(tmp_path)
        msg = _make_message(
            uid="101",
            html="<p>FRANZ</p>",
            date=datetime(2026, 7, 22, 10, 15, tzinfo=timezone.utc),
        )
        mock_mailbox = MagicMock()
        mock_mailbox.fetch.return_value = [msg]

        llm_output = json.dumps(
            {
                "movies": [
                    {
                        "title": "Franz",
                        "image_url": "",
                        "general_info": "Alemanha/Drama/2025/127min | Sala Paulo Amorim",
                        "director": "Agnieszka Holland",
                        "classification": "14 anos",
                        "excerpt": "sinopse",
                        "screening_dates": ["2026-07-25 19:15"],
                    }
                ]
            }
        )

        with (
            patch("scrapers.paulo_amorim_email.MailBox") as mock_mailbox_cls,
            patch(
                "scrapers.paulo_amorim_email.PauloAmorimEmailExtractorLLM"
            ) as mock_extractor_cls,
        ):
            mock_mailbox_cls.return_value.login.return_value.__enter__.return_value = (
                mock_mailbox
            )
            mock_extractor_cls.return_value.extract_screenings_from_text.return_value = (
                llm_output
            )
            result = scraper.get_weekly_features_json()

        assert result[0]["title"] == "Franz"
        mock_mailbox.flag.assert_called_once()
        assert mock_mailbox.flag.call_args[0][0] == "101"

    def test_failed_extraction_does_not_mark_seen(self, tmp_path):
        scraper = self._make_scraper(tmp_path)
        msg = _make_message(
            uid="102",
            html="<p>FRANZ</p>",
            date=datetime(2026, 7, 22, 10, 15, tzinfo=timezone.utc),
        )
        mock_mailbox = MagicMock()
        mock_mailbox.fetch.return_value = [msg]

        with (
            patch("scrapers.paulo_amorim_email.MailBox") as mock_mailbox_cls,
            patch(
                "scrapers.paulo_amorim_email.PauloAmorimEmailExtractorLLM"
            ) as mock_extractor_cls,
        ):
            mock_mailbox_cls.return_value.login.return_value.__enter__.return_value = (
                mock_mailbox
            )
            mock_extractor_cls.return_value.extract_screenings_from_text.return_value = None
            result = scraper.get_weekly_features_json()

        assert result == []
        mock_mailbox.flag.assert_not_called()

    def test_cache_hit_skips_gemini_call(self, tmp_path):
        scraper = self._make_scraper(tmp_path)
        html = "<p>FRANZ</p>"
        text = scraper._get_text_from_html(html)
        content_hash = hash_text(text)
        cached_features = [{"title": "Cached Movie"}]
        cache_file = os.path.join(scraper.dir, "103.json")
        with open(cache_file, "w") as f:
            json.dump({"content_hash": content_hash, "features": cached_features}, f)

        msg = _make_message(
            uid="103",
            html=html,
            date=datetime(2026, 7, 22, 10, 15, tzinfo=timezone.utc),
        )
        mock_mailbox = MagicMock()
        mock_mailbox.fetch.return_value = [msg]

        with (
            patch("scrapers.paulo_amorim_email.MailBox") as mock_mailbox_cls,
            patch(
                "scrapers.paulo_amorim_email.PauloAmorimEmailExtractorLLM"
            ) as mock_extractor_cls,
        ):
            mock_mailbox_cls.return_value.login.return_value.__enter__.return_value = (
                mock_mailbox
            )
            result = scraper.get_weekly_features_json()

        mock_extractor_cls.assert_not_called()
        assert result == cached_features
        mock_mailbox.flag.assert_called_once()

    def test_multiple_unread_messages_processed_independently(self, tmp_path):
        scraper = self._make_scraper(tmp_path)
        msg_1 = _make_message(
            uid="201",
            html="<p>FRANZ</p>",
            date=datetime(2026, 7, 22, 10, 15, tzinfo=timezone.utc),
        )
        msg_2 = _make_message(
            uid="202",
            html="<p>FANON</p>",
            date=datetime(2026, 7, 15, 10, 15, tzinfo=timezone.utc),
        )
        mock_mailbox = MagicMock()
        mock_mailbox.fetch.return_value = [msg_1, msg_2]

        def fake_extract(str_received_date, text):
            title = "Franz" if "FRANZ" in text else "Fanon"
            return json.dumps(
                {
                    "movies": [
                        {
                            "title": title,
                            "image_url": "",
                            "general_info": "",
                            "director": "",
                            "classification": "",
                            "excerpt": "",
                            "screening_dates": [],
                        }
                    ]
                }
            )

        with (
            patch("scrapers.paulo_amorim_email.MailBox") as mock_mailbox_cls,
            patch(
                "scrapers.paulo_amorim_email.PauloAmorimEmailExtractorLLM"
            ) as mock_extractor_cls,
        ):
            mock_mailbox_cls.return_value.login.return_value.__enter__.return_value = (
                mock_mailbox
            )
            mock_extractor_cls.return_value.extract_screenings_from_text.side_effect = (
                fake_extract
            )
            result = scraper.get_weekly_features_json()

        titles = sorted(movie["title"] for movie in result)
        assert titles == ["Fanon", "Franz"]
        assert mock_mailbox.flag.call_count == 2
        assert os.path.exists(os.path.join(scraper.dir, "201.json"))
        assert os.path.exists(os.path.join(scraper.dir, "202.json"))
```

- [ ] **Step 3b: Run tests to verify they fail**

Run: `uv run pytest tests/scrapers/test_paulo_amorim_email.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scrapers.paulo_amorim_email'`

### Step 4: Implement `PauloAmorimEmail`

- [ ] **Step 4a: Write the implementation**

Create `scrapers/paulo_amorim_email.py`. **Before writing this, re-check the `imap_tools` signatures confirmed in Step 0b** — if `fetch`'s mark-as-read parameter, `AND`'s sender-filter keyword, or `flag`'s parameter shape differ from what's used below, adjust accordingly:

```python
import json
import os

from bs4 import BeautifulSoup
from imap_tools import AND, MailBox, MailMessageFlags

from flask_backend.env_config import (
    PAULO_AMORIM_EMAIL_ADDRESS,
    PAULO_AMORIM_EMAIL_APP_PASSWORD,
    PAULO_AMORIM_NEWSLETTER_SENDER_EMAIL,
)
from scrapers.llm_cache import hash_text, load_cache, save_cache
from scrapers.llms import PauloAmorimEmailExtractorLLM

IMAP_HOST = "imap.gmail.com"


class PauloAmorimEmail:
    def __init__(self):
        self.dir = os.path.join("paulo-amorim-email")
        if not os.path.exists(self.dir):
            os.mkdir(self.dir)

    def _get_text_from_html(self, html):
        soup = BeautifulSoup(html, "html.parser")
        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()
        return soup.get_text()

    def _extract_features(self, str_received_date, text):
        gemini = PauloAmorimEmailExtractorLLM("gemini-2.5-flash")
        gemini_output_str = gemini.extract_screenings_from_text(
            str_received_date, text
        )
        if gemini_output_str is None:
            return None
        gemini_output = json.loads(gemini_output_str)
        return [
            {
                "poster": movie.get("image_url"),
                "time": movie.get("screening_dates"),
                "title": movie.get("title"),
                "director": movie.get("director"),
                "classification": movie.get("classification"),
                "general_info": movie.get("general_info"),
                "excerpt": movie.get("excerpt"),
                "read_more": "https://www.cinematecapauloamorim.com.br",
            }
            for movie in gemini_output["movies"]
        ]

    def _connect(self):
        return MailBox(IMAP_HOST).login(
            PAULO_AMORIM_EMAIL_ADDRESS, PAULO_AMORIM_EMAIL_APP_PASSWORD
        )

    def _process_message(self, mailbox, msg):
        html = msg.html or msg.text
        text = self._get_text_from_html(html)
        content_hash = hash_text(text)
        cache_file = os.path.join(self.dir, f"{msg.uid}.json")
        cache = load_cache(cache_file)

        if cache is not None and cache.get("content_hash") == content_hash:
            movies = cache["features"]
        else:
            str_received_date = msg.date.strftime("%a, %d %b %Y %H:%M:%S %z")
            movies = self._extract_features(str_received_date, text)
            if movies is None:
                return None
            save_cache(cache_file, content_hash, movies)

        mailbox.flag(msg.uid, MailMessageFlags.SEEN, True)
        return movies

    def get_weekly_features_json(self):
        features = []
        with self._connect() as mailbox:
            messages = list(
                mailbox.fetch(
                    AND(seen=False, from_=PAULO_AMORIM_NEWSLETTER_SENDER_EMAIL),
                    mark_seen=False,
                )
            )
            for msg in messages:
                movies = self._process_message(mailbox, msg)
                if movies is not None:
                    features.extend(movies)
        return features
```

- [ ] **Step 4b: Run tests to verify they pass**

Run: `uv run pytest tests/scrapers/test_paulo_amorim_email.py -v`
Expected: PASS (7 tests)

- [ ] **Step 4c: Run the full scraper test suite to check nothing broke**

Run: `uv run pytest tests/scrapers -v`
Expected: PASS (all tests, including Task 1's additions)

- [ ] **Step 5: Lint and format**

Run: `uv run ruff check --fix scrapers/paulo_amorim_email.py tests/scrapers/test_paulo_amorim_email.py && uv run ruff format scrapers/paulo_amorim_email.py tests/scrapers/test_paulo_amorim_email.py`

- [ ] **Step 6: Commit**

```bash
git add scrapers/paulo_amorim_email.py tests/scrapers/test_paulo_amorim_email.py
git commit -m "feat: add PauloAmorimEmail scraper for IMAP-based newsletter ingestion"
```

---

## Task 3: Wire the new room into `cinemaempoa.py`

**Files:**
- Modify: `cinemaempoa.py`

**Interfaces:**
- Consumes: `PauloAmorimEmail` and its `get_weekly_features_json()` method (Task 2).
- Produces: room key `"paulo-amorim-email"` usable via `python cinemaempoa.py -r paulo-amorim-email`.

There's no existing automated test harness for `cinemaempoa.py` (it's a `if __name__ == "__main__":` script with no tests today), so this task is verified by direct CLI invocation instead of pytest.

- [ ] **Step 1: Add the import**

In `cinemaempoa.py`, add to the imports at the top (alphabetically among the existing `from scrapers.* import *` lines):

```python
from scrapers.paulo_amorim_email import PauloAmorimEmail
```

- [ ] **Step 2: Add the room to `allowed_rooms`**

In `cinemaempoa.py`, change:

```python
    allowed_rooms = [
        "capitolio",
        "sala-redencao",
        "cinebancarios",
        "paulo-amorim",
        "cine-cinco",
    ]
```

to:

```python
    allowed_rooms = [
        "capitolio",
        "sala-redencao",
        "cinebancarios",
        "paulo-amorim",
        "paulo-amorim-email",
        "cine-cinco",
    ]
```

- [ ] **Step 3: Add the room branch**

In `cinemaempoa.py`, immediately after the closing of the existing `if "paulo-amorim" in args.rooms:` block (after its `with open(json_filename, "w") as json_file: json_file.write(dump_utf8_json(features))` block) and before `if "cine-cinco" in args.rooms:`, add:

```python
    if "paulo-amorim-email" in args.rooms:
        feature = {
            "url": "https://www.cinematecapauloamorim.com.br",
            "cinema": "Cinemateca Paulo Amorim",
            "slug": "paulo-amorim",
        }
        pauloAmorimEmail = PauloAmorimEmail()
        feature["features"] = pauloAmorimEmail.get_weekly_features_json()
        features.append(feature)
```

- [ ] **Step 4: Verify with a syntax check and a CLI dry run**

Run: `uv run python -c "import ast; ast.parse(open('cinemaempoa.py').read())"`
Expected: no output, exit code 0 (valid syntax)

Run: `uv run python cinemaempoa.py -r bogus-room 2>&1 | grep "paulo-amorim-email"`
Expected: a line is printed (the argparse error message lists `paulo-amorim-email` among the valid room choices), confirming the new room was registered correctly

- [ ] **Step 5: Lint and format**

Run: `uv run ruff check --fix cinemaempoa.py && uv run ruff format cinemaempoa.py`

- [ ] **Step 6: Commit**

```bash
git add cinemaempoa.py
git commit -m "feat: register paulo-amorim-email room in cinemaempoa CLI"
```

---

## Task 4: Daily GitHub Actions workflow

**Files:**
- Create: `.github/workflows/import-paulo-amorim-email.yml`

**Interfaces:**
- Consumes: the `paulo-amorim-email` room registered in Task 3, and the existing `import-json` Flask CLI command.
- Produces: a scheduled daily import job.

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/import-paulo-amorim-email.yml`, modeled directly on `.github/workflows/import-cinebancarios.yml`:

```yaml
name: Import Paulo Amorim Email

on:
  schedule:
    - cron: "0 4 * * *" # At 04:00 UTC every day
  workflow_dispatch:

jobs:
  import-paulo-amorim-email:
    if: ${{ github.repository == 'cumbucadev/cinemaempoa' }}
    name: Import Paulo Amorim Email
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - name: Checkout
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.HOST }}
          username:  ${{ secrets.USERNAME }}
          key: ${{ secrets.KEY }}
          script: |
            docker exec cinemaempoa_flask bash -c "python cinemaempoa.py -r paulo-amorim-email > /app/import.json"
            docker exec cinemaempoa_flask bash -c "flask --app flask_backend import-json /app/import.json"
```

- [ ] **Step 2: Verify the YAML is well-formed**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/import-paulo-amorim-email.yml'))"`
Expected: no output, exit code 0

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/import-paulo-amorim-email.yml
git commit -m "ci: add daily workflow to import Paulo Amorim newsletter emails"
```

---

## Task 5: Documentation

**Files:**
- Modify: `scrapers/README.md`

**Interfaces:**
- Consumes: nothing new — documents Tasks 1-4's already-committed behavior.
- Produces: nothing consumed by later tasks — this is the last task.

- [ ] **Step 1: Add the documentation section**

In `scrapers/README.md`, add a new section after the existing `## CineBancários` section (before any section that follows it, or at the end of the file if CineBancários is currently the last section):

```markdown
## Paulo Amorim (newsletter por e-mail)

Além do scraper de HTML (`scrapers/paulo_amorim.py`), existe uma segunda fonte de dados
para a Cinemateca Paulo Amorim: `scrapers/paulo_amorim_email.py`, que lê a newsletter
semanal enviada por e-mail e usa uma LLM pra extração das sessões (mesma estratégia do
CineBancários, ver acima). Essa segunda fonte existe porque a newsletter costuma chegar
com alguns dias de antecedência em relação à atualização do site, e o site às vezes atrasa
alguns dias no início de cada semana (ver issue #251).

As duas fontes rodam de forma independente e escrevem sessões pra mesma sala
(`paulo-amorim`) no banco. Eventuais duplicatas entre elas são resolvidas pelo
`flask --app flask_backend run-dedupper`, que já existe pra esse propósito.

### Recebendo os e-mails

Uma conta de e-mail dedicada (Gmail, com senha de app) é cadastrada na newsletter e
consultada via IMAP (biblioteca `imap-tools`) uma vez por dia. Só mensagens não lidas do
remetente da newsletter são processadas; cada mensagem só é marcada como lida depois que
a extração via LLM funciona - se a extração falhar, a mensagem continua não lida e é
reprocessada no próximo dia.

Variáveis de ambiente necessárias (ver `example.env`):

- `PAULO_AMORIM_EMAIL_ADDRESS` / `PAULO_AMORIM_EMAIL_APP_PASSWORD`: credenciais IMAP da
  conta dedicada.
- `PAULO_AMORIM_NEWSLETTER_SENDER_EMAIL`: endereço de origem da newsletter, usado pra
  filtrar quais e-mails da caixa de entrada são processados.

### Formato da newsletter

Ao contrário da página `grade-semanal` do site (organizada por dia, com uma linha por
sessão), o e-mail é organizado por sala (Sala Paulo Amorim, Sala Eduardo Hirtz, Sala
Norberto Lubisco), com um bloco de texto por filme contendo um único horário e exceções
descritas em linguagem natural, por exemplo:

```
FRANZ (...). Direção de Agnieszka Holland...
Sinopse: ...
Sessões: 19h15min (exibições nos dias 25, 26, 28 e 29 – de sábado a quarta-feira)
```

O prompt em `PauloAmorimEmailExtractorLLM` (`scrapers/llms.py`) é responsável por expandir
essas exceções (e a exceção global do tipo "SEGUNDA-FEIRA NÃO HÁ SESSÕES") em datas
concretas.
```

- [ ] **Step 2: Lint the markdown (if the repo lints markdown; otherwise just proofread)**

Run: `uv run ruff check --fix scrapers/README.md 2>&1 || true` (ruff doesn't lint markdown; this step is a no-op safety check — the real verification is a manual read-through for typos and that the fenced code block inside the fenced markdown example doesn't break rendering — GitHub renders nested triple-backtick fences correctly as long as the outer fence uses 4 backticks or the inner example is de-fenced to plain indentation; verify by previewing the file locally or checking `scrapers/README.md`'s existing nested-fence examples, e.g. the CineBancários HTML snippets, for the pattern already in use)

- [ ] **Step 3: Commit**

```bash
git add scrapers/README.md
git commit -m "docs: document Paulo Amorim newsletter email import source"
```
