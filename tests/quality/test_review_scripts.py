#!/usr/bin/env python3
"""Regression checks for local source-review artifact tooling."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import zen_review_pack as pack
import zen_source_health as health
import zen_source_judge as judge


class ReviewScriptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="zen-review-check-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_previous_review_excludes_current_and_future_rounds(self):
        for label in ("round-01", "round-02", "round-03"):
            (self.root / f"{label}-{judge.MODEL}.md").touch()
        with patch.object(judge, "SNAPSHOTS", self.root):
            self.assertIsNone(judge.previous_review("round-01"))
            self.assertEqual(
                judge.previous_review("round-02"),
                self.root / f"round-01-{judge.MODEL}.md",
            )

    def test_line_budget_counts_empty_and_unterminated_files(self):
        path = self.root / "source.zen"
        for content, count in ((b"", 0), (b"a", 1), (b"a\n", 1), (b"a\nb", 2)):
            with self.subTest(content=content):
                path.write_bytes(content)
                self.assertEqual(pack.line_count(path), count)

    def test_report_can_have_a_separate_new_parent(self):
        snapshots = self.root / "snapshots"
        report = self.root / "reports" / "health.md"
        snapshot = {"schema": 3, "label": "round-01", "totals": {"files": 1}}
        argv = ["zen_source_health.py", "--label", "round-01",
                "--revision", "working-tree", "--snapshots", str(snapshots),
                "--report", str(report)]
        with patch.object(sys, "argv", argv), \
                patch.object(health, "measure", return_value=snapshot), \
                patch.object(health, "report_of", return_value="report\n"), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(health.main(), 0)
        self.assertEqual(report.read_text(), "report\n")
        self.assertTrue((snapshots / "round-01.json").is_file())


if __name__ == "__main__":
    unittest.main()
