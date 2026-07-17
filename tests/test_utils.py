from datetime import date, datetime
from unittest.mock import patch

from utils import (
    dump_utf8_json,
    get_formatted_day_str,
    is_monday,
    string_is_current_day,
    string_is_day,
)


class TestGetFormattedDayStr:
    def test_with_explicit_date(self):
        assert get_formatted_day_str("2026-08-05") == "5 de agosto"

    def test_with_none_uses_current_date(self):
        with patch("utils.datetime") as mock_dt:
            mock_dt.now.return_value.date.return_value = date(2026, 12, 25)
            assert get_formatted_day_str(None) == "25 de dezembro"


class TestStringIsDay:
    def test_matching_day(self):
        assert string_is_day("24 de agosto | quinta-feira | 16h", "2026-08-24") is True

    def test_non_matching_day(self):
        assert string_is_day("24 de agosto | quinta-feira | 16h", "2026-08-25") is False

    def test_matching_across_all_months(self):
        months = [
            "janeiro",
            "fevereiro",
            "março",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        ]
        for month_number, month_name in enumerate(months, start=1):
            date_str = f"2026-{month_number:02d}-10"
            assert string_is_day(f"10 de {month_name} | sexta | 16h", date_str) is True


class TestStringIsCurrentDay:
    def test_matches_current_day(self):
        with patch("utils.datetime") as mock_dt:
            mock_dt.now.return_value.date.return_value = date(2026, 8, 24)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert string_is_current_day("24 de agosto | quinta-feira | 16h") is True

    def test_does_not_match_other_day(self):
        with patch("utils.datetime") as mock_dt:
            mock_dt.now.return_value.date.return_value = date(2026, 8, 25)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert string_is_current_day("24 de agosto | quinta-feira | 16h") is False


class TestIsMonday:
    def test_true_when_monday(self):
        with patch("utils.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 3)  # a Monday
            assert is_monday() is True

    def test_false_when_not_monday(self):
        with patch("utils.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 4)  # a Tuesday
            assert is_monday() is False


class TestDumpUtf8Json:
    def test_keeps_accented_characters_unescaped(self):
        result = dump_utf8_json({"title": "Sessão"})
        assert result == '{"title": "Sessão"}'
