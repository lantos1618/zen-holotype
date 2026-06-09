"""Stage A — Python-free regeneration of bootstrap/zenc.gen.c, driven by the BINARY.

bootstrap/main.c has a `--build-self <out.c> <srcroot>` mode: the binary reads
`<srcroot>/bootstrap/sources.txt`, strips each listed file's module import lines, concatenates them
with "\n",
then runs the existing parse_module -> resolve_module -> genModule path on it and writes the emitted C
(head swapped for `#include "zenrt.h"`) to <out.c>. ZERO Python participates in the source-prep or the
emit: only `cc` (to build the binary once) and the binary itself.

This is the Stage-A goal: a Python-free path that reproduces the committed bootstrap/zenc.gen.c
byte-for-byte. (The fixpoint that the COMMITTED C reproduces ITS sources is tests/test_bootstrap.py;
this proves the new C *driver* reproduces the committed file with no Python source-prep.)
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOT = ROOT / "bootstrap"


def _build(tmp_path):
    """cc the committed bootstrap sources into a binary — NO Python toolchain involved."""
    exe = tmp_path / "zenc"
    r = subprocess.run(["cc", "-std=gnu11", "-w",
                        str(BOOT / "zenc.gen.c"), str(BOOT / "zenrt.c"), str(BOOT / "main.c"),
                        "-o", str(exe)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return exe


def test_build_self_reproduces_committed_c(tmp_path):
    # cc + --build-self + diff, NO python3 in the loop: the binary reads/strips/concats the manifest,
    # compiles, and writes C == the committed bootstrap/zenc.gen.c byte-for-byte.
    exe = _build(tmp_path)
    out_c = tmp_path / "out.c"
    r = subprocess.run([str(exe), "--build-self", str(out_c), str(ROOT)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out_c.read_bytes() == (BOOT / "zenc.gen.c").read_bytes(), \
        "--build-self output != committed bootstrap/zenc.gen.c"


def test_build_self_usage_errors(tmp_path):
    # missing args -> clean nonzero exit (usage), never a crash.
    exe = _build(tmp_path)
    r = subprocess.run([str(exe), "--build-self"], capture_output=True, text=True, timeout=15)
    assert r.returncode == 2 and "usage" in r.stderr
    # a bad srcroot -> exit 1 with a diagnostic, not a segfault.
    r = subprocess.run([str(exe), "--build-self", str(tmp_path / "x.c"), "/nonexistent/zzz"],
                       capture_output=True, text=True, timeout=15)
    assert r.returncode == 1 and "cannot open" in r.stderr
