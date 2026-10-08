import cinemaempoa


class _WorkingScraper:
    def get_daily_features_json(self):
        return [{"title": "Filme"}]


class _BrokenScraper:
    def get_daily_features_json(self):
        raise ConnectionResetError(104, "Connection reset by peer")


class TestScrapeRooms:
    def test_failing_room_does_not_stop_the_others(self, monkeypatch, capsys):
        monkeypatch.setitem(
            cinemaempoa.ROOMS, "capitolio", ("url-c", "Capitólio", _WorkingScraper)
        )
        monkeypatch.setitem(
            cinemaempoa.ROOMS, "sala-redencao", ("url-s", "Redenção", _BrokenScraper)
        )

        features = cinemaempoa.scrape_rooms(["sala-redencao", "capitolio"])

        assert features == [
            {
                "url": "url-c",
                "cinema": "Capitólio",
                "slug": "capitolio",
                "features": [{"title": "Filme"}],
            },
            {
                "url": "url-s",
                "cinema": "Redenção",
                "slug": "sala-redencao",
                "features": [],
            },
        ]
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Erro ao extrair a sala sala-redencao" in captured.err
        assert "ConnectionResetError" in captured.err

    def test_only_requested_rooms_are_scraped(self, monkeypatch):
        monkeypatch.setitem(
            cinemaempoa.ROOMS, "cine-cinco", ("url", "Cine Cinco", _WorkingScraper)
        )

        features = cinemaempoa.scrape_rooms(["cine-cinco"])

        assert [room["slug"] for room in features] == ["cine-cinco"]
