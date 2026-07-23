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
            mock_extractor_cls.return_value.extract_screenings_from_text.return_value = llm_output
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
