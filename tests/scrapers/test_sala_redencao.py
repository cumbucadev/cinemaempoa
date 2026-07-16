import os
import unittest
from unittest.mock import patch

import icalendar

from scrapers.sala_redencao import SalaRedencao

GCAL_FIXTURE = os.path.join("tests/files/files_sala-redencao/gcal/basic.ics")


def _load_gcal_fixture() -> icalendar.Calendar:
    with open(GCAL_FIXTURE, "rb") as f:
        return icalendar.Calendar.from_ical(f.read())


class TestSalaRedencao(unittest.TestCase):
    def test_get_events_blog_post_url(self):
        salaRedencao = SalaRedencao(date="2023-09-13")
        salaRedencao.dir = os.path.join("tests/files/files_sala-redencao/2023-09-13")
        salaRedencao._get_events_blog_post_url()
        self.assertIsInstance(salaRedencao.events, list)
        assert len(salaRedencao.events) > 0
        for url in salaRedencao.events:
            assert url.startswith("https://www.ufrgs.br/difusaocultural/")

    def test_get_events_blog_post_html(self):
        salaRedencao = SalaRedencao(date="2023-09-13")
        salaRedencao.dir = os.path.join("tests/files/files_sala-redencao/2023-09-13")
        salaRedencao.events = [
            "https://www.ufrgs.br/difusaocultural/sala-redencao-apresenta-programacao-de-cinema-japones/",
            "https://www.ufrgs.br/difusaocultural/programacao-da-sala-redencao-explora-vanguardas-no-cinema/",
            "https://www.ufrgs.br/difusaocultural/ciclo-cineciess-exibe-5-casas-na-sala-redencao/",
        ]

    def test__fetch_google_calendar_events_returns_expected_calendar(self):
        """`_fetch_google_calendar` should parse whatever `requests.get` returns
        into an `icalendar.Calendar` - no live network call involved here."""
        with open(GCAL_FIXTURE, "rb") as f:
            fixture_bytes = f.read()

        sala_redencao = SalaRedencao()
        with patch("scrapers.sala_redencao.requests.get") as mock_get:
            mock_get.return_value.content = fixture_bytes
            gcal = sala_redencao._fetch_google_calendar()

        assert isinstance(gcal, icalendar.Calendar)
        assert "Redenção" in gcal.calendar_name

    def test__parse_google_calendar_events(self):
        """Parses a frozen calendar snapshot - deterministic regardless of
        what the live Google Calendar feed currently contains."""
        sala_redencao = SalaRedencao("2025-08-21")
        gcal = _load_gcal_fixture()
        features = sala_redencao._parse_google_calendar_events(gcal)

        assert len(features) == 46
        assert features[0]["title"] == "Aleksandr Niévski"
        assert features[0]["director"] == "Serguei Eisenstein"
        assert features[0]["time"] == ["2025-08-21T19:00"]

    def test__parse_google_calendar_events_when_traditional_technique_fails(self):
        """When the blog-post ("traditional") technique finds nothing,
        `get_daily_features_json` should fall back entirely to the
        Google Calendar results."""
        sala_redencao = SalaRedencao("2025-08-21")

        with (
            patch.object(
                SalaRedencao,
                "_fetch_google_calendar",
                return_value=_load_gcal_fixture(),
            ),
            patch.object(SalaRedencao, "_get_events_blog_post_url", return_value=[]),
            patch.object(SalaRedencao, "_get_events_blog_post_html", return_value=[]),
        ):
            features_traditional = sala_redencao._get_events_blog_post_html()
            features_gcal = sala_redencao._parse_google_calendar_events(
                _load_gcal_fixture()
            )
            features_overall = sala_redencao.get_daily_features_json()

        assert len(features_traditional) == 0
        assert len(features_gcal) > 0
        assert len(features_overall) == len(features_gcal)
        assert features_overall == features_gcal

    def test__parse_google_calendar_events_when_traditional_technique_works(self):
        """When both sources find results, `get_daily_features_json` should
        combine the blog-post ("traditional") features with the Google
        Calendar features."""
        sala_redencao = SalaRedencao("2025-08-21")
        traditional_feature = {
            "poster": "",
            "time": "21 de agosto | quinta-feira | 19h",
            "title": "Filme do Blog",
            "original_title": "",
            "price": "",
            "director": "Diretor Exemplo",
            "classification": "",
            "general_info": "Brasil / 2024 / 90 min",
            "excerpt": "Sinopse de exemplo.",
            "read_more": "https://www.ufrgs.br/difusaocultural/filme-do-blog/",
        }

        with (
            patch.object(
                SalaRedencao,
                "_fetch_google_calendar",
                return_value=_load_gcal_fixture(),
            ),
            patch.object(SalaRedencao, "_get_events_blog_post_url", return_value=[]),
            patch.object(
                SalaRedencao,
                "_get_events_blog_post_html",
                return_value=[traditional_feature],
            ),
        ):
            features_traditional = sala_redencao._get_events_blog_post_html()
            features_gcal = sala_redencao._parse_google_calendar_events(
                _load_gcal_fixture()
            )
            features_overall = sala_redencao.get_daily_features_json()

        assert len(features_traditional) > 0
        assert len(features_gcal) > 0
        assert len(features_overall) == len(features_traditional) + len(features_gcal)
        assert features_overall == features_traditional + features_gcal

    def test_get_daily_features_json(self):
        salaRedencao = SalaRedencao(date="2025-08-21")

        with (
            patch.object(
                SalaRedencao,
                "_fetch_google_calendar",
                return_value=_load_gcal_fixture(),
            ),
            patch.object(SalaRedencao, "_get_events_blog_post_url", return_value=[]),
            patch.object(SalaRedencao, "_get_events_blog_post_html", return_value=[]),
        ):
            features = salaRedencao.get_daily_features_json()

        assert len(features) == 46
        titles = [f["title"] for f in features]
        self.assertIn("Aleksandr Niévski", titles)
        self.assertIn("Coming Out", titles)
        self.assertIn("Memórias de um Esclerosado", titles)


class TestParseBlogPostWithRegex(unittest.TestCase):
    def test_extracts_feature_for_matching_day(self):
        from bs4 import BeautifulSoup

        html = """
        <div class="content-inner">
        Aleksandr Nievski(dir. Serguei Eisenstein | Russia | 1938 | 112 min)Um belo resumo aqui.05 de setembro | sexta-feira | 14h
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        sala_redencao = SalaRedencao("2026-09-05")
        feats = sala_redencao._parse_blog_post_with_regex(
            soup, "https://example.com/post"
        )

        assert len(feats) == 1
        assert feats[0]["title"] == "Aleksandr Nievski"
        assert feats[0]["director"] == "Serguei Eisenstein"
        assert feats[0]["general_info"] == "Russia / 1938 / 112 min"
        assert feats[0]["excerpt"] == "Um belo resumo aqui."
        assert feats[0]["time"] == "05 de setembro | sexta-feira | 14h"

    def test_skips_feature_when_date_does_not_match(self):
        from bs4 import BeautifulSoup

        html = """
        <div class="content-inner">
        Aleksandr Nievski(dir. Serguei Eisenstein | Russia | 1938 | 112 min)Um belo resumo aqui.05 de setembro | sexta-feira | 14h
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        sala_redencao = SalaRedencao("2026-09-06")
        feats = sala_redencao._parse_blog_post_with_regex(
            soup, "https://example.com/post"
        )
        assert feats == []


class TestParseBlogPostByHtml(unittest.TestCase):
    def test_extracts_feature_for_matching_day(self):
        from bs4 import BeautifulSoup

        html = """
        <div class="content-inner">
        <p>
        Berlim na esquina(dir. Gerhard Klein | Alemanha Oriental | 1966 | 86 min)Um belo resumo do filme.
        05 de setembro | sexta-feira | 14h
        </p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        sala_redencao = SalaRedencao("2026-09-05")
        feats = sala_redencao._parse_blog_post_by_html(soup, "https://example.com/post")

        assert len(feats) == 1
        assert feats[0]["title"] == "Berlim na esquina"
        assert feats[0]["director"] == "Gerhard Klein"
        assert feats[0]["general_info"] == "Alemanha Oriental / 1966 / 86 min"
        assert feats[0]["time"] == "05 de setembro | sexta-feira | 14h"

    def test_skips_feature_when_no_screening_dates_found(self):
        from bs4 import BeautifulSoup

        html = """
        <div class="content-inner">
        <p>Berlim na esquina(dir. Gerhard Klein | Alemanha Oriental | 1966 | 86 min)Sem datas aqui.</p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        sala_redencao = SalaRedencao("2026-09-05")
        feats = sala_redencao._parse_blog_post_by_html(soup, "https://example.com/post")
        assert feats == []

    def test_skips_feature_when_date_does_not_match(self):
        from bs4 import BeautifulSoup

        html = """
        <div class="content-inner">
        <p>
        Berlim na esquina(dir. Gerhard Klein | Alemanha Oriental | 1966 | 86 min)Um belo resumo do filme.
        05 de setembro | sexta-feira | 14h
        </p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        sala_redencao = SalaRedencao("2026-09-06")
        feats = sala_redencao._parse_blog_post_by_html(soup, "https://example.com/post")
        assert feats == []


class TestParseBlogPostAlternateFormat(unittest.TestCase):
    def test_extracts_feature_with_screening_time(self):
        from bs4 import BeautifulSoup

        html = """
        <div class="content-inner">
        <p>Dia 13 de setembro, domingo, às 19h</p>
        <p>Algum texto de preenchimento.</p>
        <p><strong>13 de setembro</strong></p>
        <p><strong>Nome Do Filme</strong></p>
        <p>(Brasil, 2022, 1h15min. Direção: Fulano de Tal. Distribuição: Something.)</p>
        <p><strong>Temas: </strong>Drama. Amor.</p>
        <p><strong>Sinopse: </strong> Um resumo aqui.</p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        sala_redencao = SalaRedencao("2026-09-13")
        feature = sala_redencao._parse_blog_post_alternate_format(
            soup, "https://example.com/post"
        )

        assert feature is not None
        assert feature["title"] == "Nome Do Filme"
        assert feature["director"] == "Fulano de Tal"
        assert feature["general_info"] == "Brasil, 2022, 1h15min"
        assert feature["time"] == "19h"
        assert "Um resumo aqui." in feature["excerpt"]

    def test_returns_none_when_no_matching_day_found(self):
        from bs4 import BeautifulSoup

        html = """
        <div class="content-inner">
        <p><strong>13 de setembro</strong></p>
        <p><strong>Nome Do Filme</strong></p>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        sala_redencao = SalaRedencao("2026-09-14")
        feature = sala_redencao._parse_blog_post_alternate_format(
            soup, "https://example.com/post"
        )
        assert feature is None


class TestGetNextSiblingWithContent(unittest.TestCase):
    def test_returns_none_at_end_of_siblings(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<div><p>only</p></div>", "html.parser")
        tag = soup.find("p")
        sala_redencao = SalaRedencao("2026-09-13")
        assert sala_redencao._get_next_sibling_with_content(tag) is None

    def test_skips_empty_siblings(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(
            "<div><p>first</p><p>   </p><p>second</p></div>", "html.parser"
        )
        tag = soup.find_all("p")[0]
        sala_redencao = SalaRedencao("2026-09-13")
        result = sala_redencao._get_next_sibling_with_content(tag)
        assert result.text == "second"


class TestGetPrevSiblingWithContent(unittest.TestCase):
    def test_returns_none_at_start_of_siblings(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<div><p>only</p></div>", "html.parser")
        tag = soup.find("p")
        sala_redencao = SalaRedencao("2026-09-13")
        assert sala_redencao._get_prev_sibling_with_content(tag) is None

    def test_skips_empty_siblings(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(
            "<div><p>first</p><p>   </p><p>second</p></div>", "html.parser"
        )
        tag = soup.find_all("p")[2]
        sala_redencao = SalaRedencao("2026-09-13")
        result = sala_redencao._get_prev_sibling_with_content(tag)
        assert result.text == "first"
