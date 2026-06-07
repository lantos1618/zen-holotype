"""CLI / build driver. `zen build` reads build.zen, compiles + links + runs the executable
and its declared Tests — and is HONEST about results: a failing Zen test makes the build
exit nonzero (not print ✗ and exit 0). These shell out to the real `python -m zen build`,
or drive cmd_build / run_test_root directly. (Split out of test_end_to_end.py, which keeps
the checker-verdict and codegen-compile-and-run tests.)"""
import subprocess
import sys

import pytest

from zen.main import run_test_root, cmd_build
from conftest import EXAMPLES


def test_void_main_harness(tmp_path):
    # a void-returning main gets a harness WITHOUT printf("%d", …) — would fail at cc otherwise
    (tmp_path / "build.zen").write_text(
        '{ Builder, BuildConfig, BuildError, Executable } = @builtin.build\n'
        'build = (b: Builder) Result<BuildConfig, BuildError> {\n'
        '    b.add(Executable { name: "v", main: "main.zen", out_dir: "build" })\n'
        '    b.config()\n}\n')
    (tmp_path / "main.zen").write_text("main* = () void { y := 5 }\n")
    out = subprocess.run([sys.executable, "-m", "zen", "build", str(tmp_path)],
                         capture_output=True, text=True, cwd=str(EXAMPLES.parent))
    assert out.returncode == 0, out.stderr
    c = (tmp_path / "build" / "v.c").read_text()
    assert "main_main();" in c and "printf" not in c.split("int main(void)")[1]


def test_full_build_runs_and_prints_12():
    # the real `zen build examples` end to end: the exe runs, and the declared Test root is
    # compiled + run with per-test verdicts printed.
    out = subprocess.run([sys.executable, "-m", "zen", "build", str(EXAMPLES)],
                         capture_output=True, text=True, cwd=str(EXAMPLES.parent))
    assert out.returncode == 0, out.stderr
    assert "rectdemo -> 12" in out.stdout
    assert "tests: test.zen" in out.stdout
    assert "PASS ✓  test.test_width" in out.stdout


def test_test_runner_reports_pass_fail_skip(tmp_path, capsys):
    (tmp_path / "lib.zen").write_text("three* = () i32 { 3 }\n")
    (tmp_path / "t.zen").write_text(
        "{ three } = lib\n"
        "t_pass* = () bool { three() == 3 }\n"   # true  -> PASS
        "t_fail* = () bool { three() == 9 }\n"   # false -> FAIL
        "t_bad*  = () bool { three() == true }\n")  # type error -> SKIP
    failures = run_test_root(tmp_path, "t.zen")
    out = capsys.readouterr().out
    assert "PASS ✓  t.t_pass" in out
    assert "FAIL ✗  t.t_fail" in out
    assert "SKIP    t.t_bad" in out
    # the count is the contract: a FAIL and a SKIP (didn't type-check) each count, so the
    # caller (cmd_build) can fail the build honestly — one PASS, one FAIL, one SKIP -> 2.
    assert failures == 2


def test_build_exits_nonzero_when_a_zen_test_fails(tmp_path):
    # the honest-CLI contract: `zen build` must FAIL (SystemExit) when a declared Test FAILs,
    # not print ✗ and exit 0. (Regression guard for the harness-returns-fails change.)
    (tmp_path / "build.zen").write_text(
        '{ Builder, Executable, Test } = @builtin.build\n'
        'build* = (b: Builder) i32 {\n'
        '    b.add(Executable { name: "x", main: "main.zen" })\n'
        '    b.add(Test { root: "test.zen" })\n'
        '    0\n'
        '}\n')
    (tmp_path / "main.zen").write_text("main* = () i32 { 0 }\n")
    (tmp_path / "test.zen").write_text("t_fail* = () bool { 1 == 2 }\n")   # always FAILs
    with pytest.raises(SystemExit):
        cmd_build(str(tmp_path))
