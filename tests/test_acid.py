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
from pathlib import Path

import pytest

from _selfhost import HEAD, emit_c_for, check_errors

STD_FILES = sorted(glob.glob("zen/std/*.zen"))


def _strip_imports(path):
    return "\n".join(l for l in Path(path).read_text().splitlines()
                     if not (l.strip().startswith("{ ") and "= std." in l))


@pytest.mark.parametrize("path", STD_FILES, ids=[p.split("/")[-1] for p in STD_FILES])
def test_self_hosted_frontend_reads_stdlib_file(tmp_path, path):
    out = emit_c_for(tmp_path, _strip_imports(path))
    # it must emit the zslice header plus at least one declaration (or, for an all-templates
    # file like iter.zen, just the header — templates inline at use, nothing standalone).
    assert out.startswith(HEAD)
    assert len(out) >= 50


# The CHECK dimension: the self-hosted VALIDATING checker (check_module) over each stdlib file,
# returning its error count. ALL 10 are accepted with ZERO errors — generics (iter, vec), traits
# (alloc), closures. So the self-hosted FRONTEND parses AND type-checks the whole real stdlib,
# matching the Python frontend's verdict.
@pytest.mark.parametrize("path", STD_FILES, ids=[p.split("/")[-1] for p in STD_FILES])
def test_self_hosted_checker_accepts_stdlib_file(tmp_path, path):
    assert check_errors(tmp_path, _strip_imports(path)) == 0
