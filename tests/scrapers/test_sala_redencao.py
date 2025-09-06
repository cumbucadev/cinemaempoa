import os
import unittest

import icalendar

from scrapers.sala_redencao import SalaRedencao


class TestSalaRedencao(unittest.TestCase):
    def test_get_events_blog_post_url(self):
        salaRedencao = SalaRedencao(date="2023-09-13")
        salaRedencao.dir = os.path.join("tests/files/files_sala-redencao/2023-09-13")
        salaRedencao._get_events_blog_post_url()
        assert salaRedencao.events == [
            "https://www.ufrgs.br/difusaocultural/sala-redencao-apresenta-programacao-de-cinema-japones/",
            "https://www.ufrgs.br/difusaocultural/programacao-da-sala-redencao-explora-vanguardas-no-cinema/",
            "https://www.ufrgs.br/difusaocultural/ciclo-cineciess-exibe-5-casas-na-sala-redencao/",
        ]

    def test_get_events_blog_post_html(self):
        salaRedencao = SalaRedencao(date="2023-09-13")
        salaRedencao.dir = os.path.join("tests/files/files_sala-redencao/2023-09-13")
        salaRedencao.events = [
            "https://www.ufrgs.br/difusaocultural/sala-redencao-apresenta-programacao-de-cinema-japones/",
            "https://www.ufrgs.br/difusaocultural/programacao-da-sala-redencao-explora-vanguardas-no-cinema/",
            "https://www.ufrgs.br/difusaocultural/ciclo-cineciess-exibe-5-casas-na-sala-redencao/",
        ]

    def test__fetch_google_calendar_events_returns_expected_calendar(self):
        sala_redencao = SalaRedencao()
        gcal = sala_redencao._fetch_google_calendar()

        assert isinstance(gcal, icalendar.Calendar)
        assert "Redenção" in gcal.calendar_name

    def test__parse_google_calendar_events(self):
        sala_redencao = SalaRedencao("2025-08-28")
        gcal = sala_redencao._fetch_google_calendar()
        features = sala_redencao._parse_google_calendar_events(gcal)
        assert len(features) > 0
        assert features[0]["title"] == "EL GRECO, O PINTOR DO INVISÍVEL"

    def test__parse_google_calendar_events_when_traditional_technique_fails(self):
        sala_redencao = SalaRedencao("2025-08-28")
        gcal = sala_redencao._fetch_google_calendar()
        features_gcal = sala_redencao._parse_google_calendar_events(gcal)
        features_traditional = sala_redencao._get_events_blog_post_html()
        features_overall = sala_redencao.get_daily_features_json()

        print(f"Features (gcal): {features_gcal}")
        print(f"Features (traditional): {features_traditional}")
        print(f"Features (overall): {features_overall}")

        assert len(features_traditional) == 0
        assert len(features_gcal) > 0
        assert len(features_overall) == len(features_gcal)
        assert features_overall == features_gcal

    def test__parse_google_calendar_events_when_traditional_technique_works(self):
        sala_redencao = SalaRedencao("2025-09-11")
        gcal = sala_redencao._fetch_google_calendar()
        features_gcal = sala_redencao._parse_google_calendar_events(gcal)
        sala_redencao._get_events_blog_post_url()
        features_traditional = sala_redencao._get_events_blog_post_html()
        features_overall = sala_redencao.get_daily_features_json()

        print(f"Features (gcal): {features_gcal}")
        print(f"Features (traditional): {features_traditional}")
        print(f"Features (overall): {features_overall}")

        assert len(features_traditional) > 0
        assert len(features_gcal) > 0
        assert len(features_overall) == len(features_gcal)
        assert len(features_overall) == len(features_traditional)
        assert features_overall == features_traditional

    def test_get_daily_features_json(self):
        salaRedencao = SalaRedencao(date="2025-09-02")
        features = salaRedencao.get_daily_features_json()
        assert len(features) == 3
        titles = [f["title"] for f in features]
        self.assertIn("Nu entre lobos", titles)
        self.assertIn("Lissy", titles)
        self.assertIn("Estrelas", titles)
