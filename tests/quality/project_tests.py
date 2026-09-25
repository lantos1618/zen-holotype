#!/usr/bin/env python3
"""Exercise executable test targets through the real Zen CLI."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ZEN = ROOT / "zen"


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="zen-project-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.write("pass.zen", "main = () i32 { 0 }\n")
        self.write("fail.zen", "main = () i32 { 7 }\n")

    def write(self, name, text):
        (self.root / name).write_text(text)

    def build_file(self, registrations):
        self.write("build.zen", "Builder, BuildError = std.build\n"
                   "build = (b :: Builder) Res<(), BuildError> {\n"
                   + registrations + "\nOk(())\n}\n")

    def run_zen(self, *args):
        return subprocess.run([str(ZEN), *args], cwd=self.root,
                              env={**os.environ, "ZEN_STD": str(ROOT / "src")},
                              capture_output=True, text=True, timeout=90)

    def test_failures_continue_and_selection_is_explicit(self):
        self.build_file('b.exe_test("first", {src: Path("pass.zen"), deps: []}).try();\n'
                        'b.exe_test("bad", {src: Path("fail.zen"), deps: []}).try();\n'
                        'b.exe_test("last", {src: Path("pass.zen"), deps: []}).try();')
        all_tests = self.run_zen("test")
        self.assertEqual(all_tests.returncode, 1, all_tests.stdout + all_tests.stderr)
        self.assertIn("not ok bad (exit 7)\nok last", all_tests.stdout)
        self.assertIn("zen test: 2 passed, 1 failed", all_tests.stdout)
        selected = self.run_zen("test", str(self.root), "last")
        self.assertEqual(selected.returncode, 0, selected.stdout + selected.stderr)
        self.assertIn("zen test: 1 passed, 0 failed", selected.stdout)
        self.assertNotIn("not ok", selected.stdout)
        local = self.run_zen("test", "first")
        self.assertEqual(local.returncode, 0, local.stdout + local.stderr)

    def test_empty_and_unknown_selections_fail(self):
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: []}).try();')
        for args in (("test",), ("test", "missing")):
            result = self.run_zen(*args)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("no matching executable test targets", result.stdout)

    def test_registered_unimported_source_is_checked_before_any_execution(self):
        self.write("pass.zen", 'main = () () { println("must not run"); }\n')
        self.write("broken_test.zen", 'main = () () { absent_test_function(); }\n')
        self.build_file('b.exe_test("first", {src: Path("pass.zen"), deps: []}).try();\n'
                        'b.exe_test("broken", {src: Path("broken_test.zen"), deps: []}).try();')
        result = self.run_zen("test")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("undefined name", result.stdout)
        self.assertNotIn("must not run", result.stdout)
        self.assertNotIn("zen test: 2 passed", result.stdout)

    def test_trailing_arguments_require_a_separator(self):
        self.write("args.zen", 'main = (env: Env) () {\n'
                   'env.argv.get(1).when_ok((arg) { println("arg {}", arg); });\n}\n')
        self.build_file('b.exe_test("args", {src: Path("args.zen"), deps: []}).try();')
        result = self.run_zen("test", "--", "--help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("arg --help", result.stdout)
        for args in (("test", "--invalid"), ("test", "args", "extra")):
            result = self.run_zen(*args)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_duplicate_target_names_are_rejected(self):
        self.build_file('b.exe("same", {src: Path("pass.zen"), deps: []}).try();\n'
                        'b.exe_test("same", {src: Path("pass.zen"), deps: []}).try();')
        result = self.run_zen("test")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("zen test: 1 passed", result.stdout)

    def test_selected_targets_cannot_share_an_executable(self):
        self.build_file('b.exe_test("first", {src: Path("fail.zen"), deps: [], '
                        'out: Ok(Path("build/shared"))}).try();\n'
                        'b.exe_test("last", {src: Path("pass.zen"), deps: [], '
                        'out: Ok(Path("build/shared"))}).try();')
        result = self.run_zen("test")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("selected targets share output", result.stdout)
        self.assertNotIn("zen test: 2 passed", result.stdout)

    def test_ordinary_build_does_not_execute_or_build_test_targets(self):
        self.write("broken.zen", 'main = () () { missing(); }\n')
        self.build_file('b.exe("app", {src: Path("pass.zen"), deps: []}).try();\n'
                        'b.exe_test("test", {src: Path("broken.zen"), deps: []}).try();')
        result = self.run_zen("build")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / "build/linux-x86_64/test").exists())

    def test_suite_rejects_empty_and_reports_assertions(self):
        self.write("suite.zen", 'Suite = std.test\n'
                   'main = (env: Env) Res<i32, IoError> {\n'
                   'suite ::= Suite(env: env);\nsuite.finish()\n}\n')
        self.build_file('b.exe_test("suite", {src: Path("suite.zen"), deps: []}).try();')
        empty = self.run_zen("test")
        self.assertEqual(empty.returncode, 1, empty.stdout + empty.stderr)
        self.assertIn("0 passed, 0 failed", empty.stdout)
        self.write("suite.zen", 'Suite = std.test\n'
                   'main = (env: Env) Res<i32, IoError> {\n'
                   'suite ::= Suite(env: env);\n'
                   'suite.run("first", (t) { t.expect(false) }).try();\n'
                   'suite.run("last", (t) { t.expect_eq(2, 2) }).try();\n'
                   'suite.finish()\n}\n')
        failed = self.run_zen("test")
        self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
        self.assertIn("not ok first: expectation was false", failed.stdout)
        self.assertIn("ok last", failed.stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen", type=Path, default=ZEN)
    args, remaining = parser.parse_known_args()
    ZEN = args.zen.resolve()
    unittest.main(argv=[__file__, *remaining])
