from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_official_notice import parse_notice_text  # noqa: E402
from validate_holidays import ValidationError, validate_document  # noqa: E402


class NoticeParserTests(unittest.TestCase):
    def test_parses_2026_notice(self) -> None:
        source = (ROOT / "tests" / "fixtures" / "2026-notice.txt").read_text(encoding="utf-8")
        periods = parse_notice_text(source, 2026)
        self.assertEqual(7, len(periods))
        self.assertEqual(
            ["2026-02-15", "2026-02-16", "2026-02-17", "2026-02-18",
             "2026-02-19", "2026-02-20", "2026-02-21", "2026-02-22", "2026-02-23"],
            periods[1]["daysOff"],
        )
        self.assertEqual(["2026-02-14", "2026-02-28"], periods[1]["adjustedWorkdays"])
        self.assertEqual(["2026-09-20", "2026-10-10"], periods[-1]["adjustedWorkdays"])


class ValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads((ROOT / "holidays" / "2026.json").read_text(encoding="utf-8"))

    def test_accepts_reviewed_document(self) -> None:
        validate_document(self.document, 2026)

    def test_rejects_conflicting_day(self) -> None:
        invalid = copy.deepcopy(self.document)
        invalid["periods"][0]["adjustedWorkdays"].append("2026-01-01")
        invalid["periods"][0]["adjustedWorkdays"].sort()
        invalid["adjustedWorkdays"].append("2026-01-01")
        invalid["adjustedWorkdays"].sort()
        with self.assertRaises(ValidationError):
            validate_document(invalid, 2026)

    def test_rejects_non_official_source(self) -> None:
        invalid = copy.deepcopy(self.document)
        invalid["source"]["url"] = "https://example.com/holidays"
        with self.assertRaises(ValidationError):
            validate_document(invalid, 2026)


if __name__ == "__main__":
    unittest.main()

