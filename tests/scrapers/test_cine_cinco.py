import json
import os
from unittest.mock import patch

import pytest
import requests

from scrapers.cine_cinco import CineCinco, drop_repeated_sessions

FIXTURE_DIR = "tests/files/files_cine_cinco/2026-11-19"
EVENT_URL = "https://www.pucrs.br/cultura/evento/{}/"
NOVEMBER = EVENT_URL.format("cine-cinco-programacao-de-novembro")
ENCRUZILHADA = EVENT_URL.format("cine-cinco-encruzilhada")
CINEMA_NEGRO = EVENT_URL.format("cine-cinco-mostra-de-cinema-negro")
ANJO_EXTERMINADOR = EVENT_URL.format(
    "cine-cinco-cineclube-filosofia-o-anjo-exterminador"
)
LEGADO = EVENT_URL.format("cine-cinco-estreia-internacional-do-filme-legado")
HAMNET = EVENT_URL.format("cine-cinco-hamnet-a-vida-antes-de-hamlet")


def _make_scraper(tmp_path):
    cine_cinco = CineCinco()
    cine_cinco.todays_dir = FIXTURE_DIR
    cine_cinco.cache_dir = os.path.join(tmp_path, "cache")
    return cine_cinco


def _llm_output(*movies):
    return json.dumps(
        {
            "movies": [
                {
                    "title": title,
                    "image_url": "",
                    "general_info": "Brasil, 2024 | Drama • 95 min",
                    "director": "",
                    "classification": "14 anos",
                    "excerpt": "sinopse",
                    "screening_dates": dates,
                }
                for title, dates in movies
            ]
        }
    )


class TestGetEventUrls:
    def test_lists_the_cine_cinco_events_on_the_agenda(self, tmp_path):
        """The agenda lists every PUCRS cultural event of the month; only those
        whose title or venue names Cine Cinco are screenings - here the TENDA
        play is not."""
        scraper = _make_scraper(tmp_path)

        assert scraper._get_event_urls() == [
            NOVEMBER,
            ENCRUZILHADA,
            CINEMA_NEGRO,
            ANJO_EXTERMINADOR,
            LEGADO,
        ]

    def test_matches_on_the_venue_when_the_title_omits_it(self, tmp_path):
        scraper = _make_scraper(tmp_path)
        agenda_dir = tmp_path / "agenda"
        agenda_dir.mkdir()
        (agenda_dir / "agenda.html").write_text(
            """
            <div class="item"><div class="imagem">
              <a href="https://www.pucrs.br/cultura/evento/legado/">
                <div class="local"><small>Local</small><br>
                  Cine Cinco - Sala de Cinema da PUCRS (Prédio 5)</div>
              </a></div>
              <div class="titulo"><a href="https://www.pucrs.br/cultura/evento/legado/">
                Estreia internacional do filme Legado</a></div>
            </div>
            <div class="item"><div class="imagem">
              <a href="https://www.pucrs.br/cultura/evento/coral/">
                <div class="local"><small>Local</small><br>Salão de Atos</div>
              </a></div>
              <div class="titulo"><a href="https://www.pucrs.br/cultura/evento/coral/">
                Concerto do Coral</a></div>
            </div>
            """
        )
        scraper.todays_dir = str(agenda_dir)

        assert scraper._get_event_urls() == [
            "https://www.pucrs.br/cultura/evento/legado/"
        ]


class TestGetEventText:
    def test_keeps_the_post_and_the_event_dates(self, tmp_path):
        """The sessions carry no year ("9/11 • segunda"), so the event's own
        date range - which does - must reach the LLM alongside the post."""
        scraper = _make_scraper(tmp_path)

        text = scraper._get_event_text(HAMNET)

        assert "Sessão: 9/11" in text
        assert "Chloé Zhao" in text
        assert "09/11/2026" in text

    def test_drops_the_other_events_listed_below_the_post(self, tmp_path):
        scraper = _make_scraper(tmp_path)

        text = scraper._get_event_text(HAMNET)

        assert "Outros eventos" not in text
        assert "Próximos eventos" not in text
        assert "Ópera do Malandro" not in text

    def test_raises_when_the_page_structure_changed(self, tmp_path):
        scraper = _make_scraper(tmp_path)
        events_dir = tmp_path / "events"
        events_dir.mkdir()
        (events_dir / "novo.html").write_text("<html><body>nada</body></html>")
        scraper.todays_dir = str(tmp_path)

        with pytest.raises(ValueError, match="structure may have changed"):
            scraper._get_event_text("https://www.pucrs.br/cultura/evento/novo/")


class TestDropRepeatedSessions:
    def test_keeps_the_first_announcement_of_a_session(self):
        """The monthly post repeats the films that also get their own event
        page; Cine Cinco has a single room, so one time is one screening."""
        features = [
            {"title": "Hamnet: A vida antes de Hamlet", "time": ["2026-11-09 19:15"]},
            {"title": "Malês", "time": ["2026-11-18 17:00"]},
            {"title": "Hamnet", "time": ["2026-11-09 19:15"]},
        ]

        assert drop_repeated_sessions(features) == features[:2]

    def test_keeps_a_feature_with_some_new_sessions(self):
        features = [
            {"title": "Ran", "time": ["2026-11-13 19:00"]},
            {"title": "Ran", "time": ["2026-11-13 19:00", "2026-11-20 19:00"]},
        ]

        assert drop_repeated_sessions(features) == [
            {"title": "Ran", "time": ["2026-11-13 19:00"]},
            {"title": "Ran", "time": ["2026-11-20 19:00"]},
        ]


class TestGetDailyFeaturesJson:
    def test_extracts_each_event_and_links_back_to_it(self, tmp_path):
        scraper = _make_scraper(tmp_path)
        outputs = {
            NOVEMBER: _llm_output(
                ("Malês", ["2026-11-18 17:00"]), ("Legado", ["2026-11-27 17:00"])
            ),
            ENCRUZILHADA: _llm_output(("Encruzilhada", ["2026-11-16 19:00"])),
            CINEMA_NEGRO: _llm_output(("Malês", ["2026-11-18 17:00"])),
            ANJO_EXTERMINADOR: _llm_output(
                ("O Anjo Exterminador", ["2026-11-23 19:15"])
            ),
            LEGADO: _llm_output(("Legado", ["2026-11-27 17:00"])),
        }

        with patch("scrapers.cine_cinco.CineCincoExtractorLLM") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_screenings_from_text.side_effect = [
                outputs[url] for url in scraper._get_event_urls()
            ]
            result = scraper.get_daily_features_json()

        assert [(f["title"], f["read_more"]) for f in result] == [
            ("Malês", NOVEMBER),
            ("Legado", NOVEMBER),
            ("Encruzilhada", ENCRUZILHADA),
            ("O Anjo Exterminador", ANJO_EXTERMINADOR),
        ]
        assert result[0]["time"] == ["2026-11-18 17:00"]

    def test_unchanged_events_skip_the_llm(self, tmp_path):
        scraper = _make_scraper(tmp_path)
        with patch("scrapers.cine_cinco.CineCincoExtractorLLM") as mock_extractor_cls:
            extract = mock_extractor_cls.return_value.extract_screenings_from_text
            extract.return_value = _llm_output(("Legado", ["2026-11-27 17:00"]))
            first = scraper.get_daily_features_json()
            second = scraper.get_daily_features_json()

        assert extract.call_count == 5
        assert second == first

    def test_llm_failure_falls_back_to_the_events_last_features(self, tmp_path):
        scraper = _make_scraper(tmp_path)
        with patch("scrapers.cine_cinco.CineCincoExtractorLLM") as mock_extractor_cls:
            extract = mock_extractor_cls.return_value.extract_screenings_from_text
            extract.return_value = _llm_output(("Legado", ["2026-11-27 17:00"]))
            first = scraper.get_daily_features_json()

            for cache_file in os.listdir(scraper.cache_dir):
                path = os.path.join(scraper.cache_dir, cache_file)
                with open(path) as f:
                    cache = json.load(f)
                cache["content_hash"] = "stale-hash"
                with open(path, "w") as f:
                    json.dump(cache, f)
            extract.return_value = None
            second = scraper.get_daily_features_json()

        assert first
        assert second == first

    def test_llm_failure_without_cache_returns_empty_list(self, tmp_path):
        scraper = _make_scraper(tmp_path)

        with patch("scrapers.cine_cinco.CineCincoExtractorLLM") as mock_extractor_cls:
            mock_extractor_cls.return_value.extract_screenings_from_text.return_value = None
            result = scraper.get_daily_features_json()

        assert result == []

    def test_an_unreachable_event_does_not_drop_the_others(self, tmp_path):
        scraper = _make_scraper(tmp_path)
        real_get_event_text = scraper._get_event_text

        def get_event_text(url):
            if url == NOVEMBER:
                raise requests.exceptions.ConnectionError("reset")
            return real_get_event_text(url)

        with (
            patch.object(scraper, "_get_event_text", side_effect=get_event_text),
            patch("scrapers.cine_cinco.CineCincoExtractorLLM") as mock_extractor_cls,
        ):
            mock_extractor_cls.return_value.extract_screenings_from_text.side_effect = [
                _llm_output(("Encruzilhada", ["2026-11-16 19:00"])),
                _llm_output(("Malês", ["2026-11-18 17:00"])),
                _llm_output(("O Anjo Exterminador", ["2026-11-23 19:15"])),
                _llm_output(("Legado", ["2026-11-27 17:00"])),
            ]
            result = scraper.get_daily_features_json()

        assert [f["title"] for f in result] == [
            "Encruzilhada",
            "Malês",
            "O Anjo Exterminador",
            "Legado",
        ]
