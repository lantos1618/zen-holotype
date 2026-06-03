"""The bootstrap fixpoint 🏁 — the self-hosted compiler reproduces itself with no Python.

`cc bootstrap/*.c -o zenc` builds a standalone binary from the COMMITTED C (bootstrap/
zenc.gen.c + a tiny runtime). That binary reads Zen source and emits C. Fed its OWN four
source files, it emits byte-for-byte the C it was built from — the fixpoint.

If these fail after editing std/{genc,lex,parse,check}.zen, regenerate the committed C:
    python3 bootstrap/generate.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bootstrap"))
import generate  # noqa: E402

BOOT = ROOT / "bootstrap"


def _build(tmp_path):
    """cc the committed bootstrap sources into a binary — NO Python toolchain involved."""
    exe = tmp_path / "zenc"
    r = subprocess.run(["cc", "-std=gnu11", "-w",
                        str(BOOT / "zenc.gen.c"), str(BOOT / "zenrt.c"), str(BOOT / "main.c"),
                        "-o", str(exe)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return exe


def test_bootstrap_binary_compiles_zen(tmp_path):
    # the standalone binary turns Zen source into C
    exe = _build(tmp_path)
    out = subprocess.run([str(exe)], input="sq* = (n: i32) i32 { n * n }\n",
                         capture_output=True, text=True).stdout
    assert "int32_t sq(int32_t n)" in out
    assert "return (n * n);" in out
    # and that emitted C is itself valid (compile + run it)
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + out
                                  + "\nint main(void){ return sq(7) == 49 ? 0 : 1; }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 0


def test_bootstrap_committed_c_matches_sources(tmp_path):
    # the committed bootstrap/zenc.gen.c is what the toolchain emits for std/*.zen RIGHT NOW.
    # (catches an edit to a .zen source without re-running bootstrap/generate.py)
    out = generate.generate_c(tmp_path)
    expected = generate.gen_c_file(out)
    committed = (BOOT / "zenc.gen.c").read_text()
    assert committed == expected, "bootstrap/zenc.gen.c is stale — run `python3 bootstrap/generate.py`"


def test_bootstrap_fixpoint(tmp_path):
    # 🏁 the binary, fed the compiler's own four source files, reproduces the C it was built from.
    exe = _build(tmp_path)
    (tmp_path / "compiler.zen").write_text(generate.compiler_source())
    repro = subprocess.run([str(exe), str(tmp_path / "compiler.zen")],
                           capture_output=True, text=True).stdout
    assert generate.gen_c_file(repro) == (BOOT / "zenc.gen.c").read_text()
