"""
Tests flask_backend/service/motifs.py.
"""

from flask_backend.service.motifs import _dedupe_preserve_order


class TestDedupePreserveOrder:
    def test_removes_duplicates_keeping_first_occurrence_order(self):
        assert _dedupe_preserve_order(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]

    def test_returns_empty_list_unchanged(self):
        assert _dedupe_preserve_order([]) == []

    def test_returns_list_with_no_duplicates_unchanged(self):
        assert _dedupe_preserve_order(["a", "b", "c"]) == ["a", "b", "c"]
