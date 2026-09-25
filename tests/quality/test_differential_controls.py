#!/usr/bin/env python3
"""Regression tests for the semantic differential harness controls."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUN_PATH = HERE.parent / "differential" / "run.py"
SPEC = importlib.util.spec_from_file_location("differential_run", RUN_PATH)
assert SPEC and SPEC.loader
run = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run
SPEC.loader.exec_module(run)


class DifferentialHarnessControlTests(unittest.TestCase):
    def test_empty_collection_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps({"version": 1, "fixtures": []}))
            with self.assertRaisesRegex(run.HarnessError, "zero fixtures"):
                run.load_manifest(manifest)

    def test_zen_accepted_valid_c_is_a_positive_control(self):
        """The classifier must also recognize a successful native run."""
        fixture = run.Fixture(
            "known_success",
            run.FIXTURES / "ran_ok.zen",
            run.RAN_OK,
            None,
            None,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            zen = root / "zen"
            zen.write_text(
                "#!/bin/sh\n"
                "out=\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = -o ]; then shift; out=$1; fi\n"
                "  shift\n"
                "done\n"
                "cat > \"$out\" <<'EOF'\n"
                "int main(void) { return 0; }\n"
                "EOF\n"
                "exit 0\n"
            )
            zen.chmod(zen.stat().st_mode | stat.S_IXUSR)
            work = root / "work"
            work.mkdir()
            outcome = run.classify(
                fixture, work, str(zen), os.environ.get("CC", "cc"),
                run.DEFAULT_CC_FLAGS.split(), 30, 5,
            )
            self.assertEqual(outcome.kind, run.RAN_OK)

    def test_zen_accepted_c_rejected_is_a_red_control(self):
        """A Zen stand-in that emits invalid C must classify as CC_REJECTED."""
        fixture = run.Fixture(
            "known_c_rejection",
            run.FIXTURES / "ran_ok.zen",
            run.RAN_OK,
            None,
            None,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            zen = root / "zen"
            zen.write_text(
                "#!/bin/sh\n"
                "out=\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = -o ]; then shift; out=$1; fi\n"
                "  shift\n"
                "done\n"
                "printf 'this is not valid C\\n' > \"$out\"\n"
                "exit 0\n"
            )
            zen.chmod(zen.stat().st_mode | stat.S_IXUSR)
            work = root / "work"
            work.mkdir()
            outcome = run.classify(
                fixture, work, str(zen), os.environ.get("CC", "cc"),
                run.DEFAULT_CC_FLAGS.split(), 30, 5,
            )
            self.assertEqual(outcome.kind, run.CC_REJECTED)


if __name__ == "__main__":
    unittest.main()
