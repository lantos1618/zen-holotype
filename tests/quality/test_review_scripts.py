#!/usr/bin/env python3
"""Regression checks for local source-review artifact tooling."""

from contextlib import redirect_stdout
import io
import json
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

    def test_foreign_json_in_the_snapshot_directory_is_skipped(self):
        # The scratch snapshot directory also holds unrelated outputs. A
        # list-shaped document there raised AttributeError on `.get` and
        # made the structural report ungeneratable by default; the control
        # below is the shape that did it.
        snapshots = self.root / "snapshots"
        snapshots.mkdir()
        (snapshots / "text-frame-negative-control.json").write_text("[]")
        (snapshots / "keep.json").write_text(
            json.dumps({"schema": health.SNAPSHOT_SCHEMA,
                        "label": "round-01", "totals": {"files": 1}})
        )
        loaded = health.load_snapshots(snapshots)
        self.assertEqual([item["label"] for item in loaded], ["round-01"])

    def test_load_snapshots_survives_unreadable_and_foreign_documents(self):
        snapshots = self.root / "snapshots"
        snapshots.mkdir()
        # Not JSON, a bare scalar, a different schema, and the empty
        # document: none is a snapshot, and none may raise.
        (snapshots / "broken.json").write_text("{not json")
        (snapshots / "scalar.json").write_text("42")
        (snapshots / "future.json").write_text(json.dumps({"schema": 4}))
        (snapshots / "empty.json").write_text("{}")
        (snapshots / "invalid-utf8.json").write_bytes(b"\xff")
        (snapshots / "directory.json").mkdir()
        self.assertEqual(health.load_snapshots(snapshots), [])

    def test_unreadable_snapshot_is_skipped(self):
        (self.root / "denied.json").touch()
        with patch.object(Path, "read_text", side_effect=PermissionError):
            self.assertEqual(health.load_snapshots(self.root), [])

    def test_measured_snapshot_can_be_loaded(self):
        # Exercise the writer and reader together without needing a grammar
        # build: an empty source directory never invokes the parser.
        source = self.root / "src"
        source.mkdir()
        with patch.object(health, "parser_for"):
            snapshot = health.measure(source, self.root / "unused.so", "round-01", "test")
        (self.root / "round-01.json").write_text(json.dumps(snapshot))
        self.assertEqual(health.load_snapshots(self.root), [snapshot])

    def test_foreign_json_does_not_break_generating_the_report(self):
        # End to end: the foreign file is present, and the run still
        # produces a report and a snapshot.
        snapshots = self.root / "snapshots"
        snapshots.mkdir()
        (snapshots / "foreign.json").write_text("[]")
        report = self.root / "health.md"
        snapshot = {"schema": health.SNAPSHOT_SCHEMA, "label": "round-01",
                    "totals": {"files": 1}}
        argv = ["zen_source_health.py", "--label", "round-01",
                "--revision", "working-tree", "--snapshots", str(snapshots),
                "--report", str(report)]
        with patch.object(sys, "argv", argv), \
                patch.object(health, "measure", return_value=snapshot), \
                patch.object(health, "report_of", return_value="report\n"), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(health.main(), 0)
        self.assertEqual(report.read_text(), "report\n")


if __name__ == "__main__":
    unittest.main()
