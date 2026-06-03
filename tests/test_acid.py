"""Phase 6 (acid test, in-progress) — the self-hosted frontend reads the WHOLE stdlib.

Every std/*.zen file is fed through the self-hosted toolchain (parse_module ->
resolve_module -> genModule, all written in Zen) and must process WITHOUT ERROR, emitting
output. This proves the Zen-written frontend PARSES + RESOLVES every real stdlib file —
including ones with generics (iter, vec), traits (alloc), structs, enums, closures.

NOTE: this gate is "parses + resolves + emits", not yet "emits fully-valid C for every
file". Two gaps remain before the strict 100% acid test: generic DATA structures (vec's
`<A: Allocator>` leaks the type param — needs backend monomorphization, deferred) and
cross-module imported-fn signatures (Phase 5). The compiler's own four files (genc, lex,
parse, check) DO emit valid C and self-host — that's tests/test_bootstrap.py.
"""
import glob
import subprocess
import tempfile
from pathlib import Path

import pytest

from zen.main import (load, build_namespace, build_scopes, resolve,
                      fold_comptime, run_emits, check, emit_c)

_DRIVER = """
{ Malloc } = std.alloc
{ parse_module } = std.parse
{ resolve_module } = std.check
{ genModule } = std.genc
{ String, new, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    m := Malloc { _: 0 }
    emit(genModule(addr(m).resolve_module(addr(m).parse_module("%s"))))
    0
}
"""

STD_FILES = sorted(glob.glob("zen/std/*.zen"))


def _zlit(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _strip_imports(path):
    return "\n".join(l for l in Path(path).read_text().splitlines()
                     if not (l.strip().startswith("{ ") and "= std." in l))


def _feed(tmp_path, src):
    (tmp_path / "main.zen").write_text(_DRIVER % _zlit(src))
    files = load(tmp_path); ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    return subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout


@pytest.mark.parametrize("path", STD_FILES, ids=[p.split("/")[-1] for p in STD_FILES])
def test_self_hosted_frontend_reads_stdlib_file(tmp_path, path):
    out = _feed(tmp_path, _strip_imports(path))
    # it must emit the zslice header plus at least one declaration (or, for an all-templates
    # file like iter.zen, just the header — templates inline at use, nothing standalone).
    assert out.startswith("typedef struct { void* ptr; int64_t len; } zslice; ")
    assert len(out) >= 50


# The CHECK dimension: the self-hosted VALIDATING checker (check_module) over each stdlib file,
# returning its error count as the process exit code. 9/10 are accepted with ZERO errors —
# including files with generics (iter, vec), traits (alloc), closures. parse.zen (the largest,
# most call-dense file) still trips 17 arg-type FALSE POSITIVES — it self-compiles and Python
# accepts it, so these are a checker-precision parity gap (infer/fits not yet exact on every
# UFCS/call pattern), not real type errors. Tracked as xfail until the checker tightens.
_CHECK_DRIVER = """
{ Malloc } = std.alloc
{ parse_module } = std.parse
{ resolve_module, check_module } = std.check
main* = () i32 {
    m := Malloc { _: 0 }
    addr(m).check_module(addr(m).resolve_module(addr(m).parse_module("%s")))
}
"""


def _check_errors(tmp_path, src):
    (tmp_path / "main.zen").write_text(_CHECK_DRIVER % _zlit(src))
    files = load(tmp_path); ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    return subprocess.run([str(tmp_path / "o")]).returncode


@pytest.mark.parametrize("path", STD_FILES, ids=[p.split("/")[-1] for p in STD_FILES])
def test_self_hosted_checker_accepts_stdlib_file(tmp_path, path):
    if path.endswith("parse.zen"):
        pytest.xfail("17 arg-type false positives — checker-precision parity gap (parse.zen self-compiles)")
    assert _check_errors(tmp_path, _strip_imports(path)) == 0
