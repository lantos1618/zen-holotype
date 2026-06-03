"""Phase 6 (acid test) — the self-hosted frontend reads the WHOLE real stdlib, AS-IS.

Every std/*.zen file is fed THROUGH the self-hosted toolchain (parse_module -> resolve_module
-> genModule/check_module, all written in Zen) verbatim — imports and all, no pre-processing.
The Zen-written frontend PARSES + RESOLVES + TYPE-CHECKS every real stdlib file (generics in
iter/vec, traits in alloc, structs, enums, closures, @while) with ZERO check errors — matching
the Python frontend's verdict.

NOTE on what's still NOT this gate: codegen VALIDITY for generic DATA structures (vec's
`<A: Allocator>` leaks the type param in the EMITTED C — needs backend monomorphization, the
deferred backend piece) and full cross-module SIGNATURE resolution (a call to an imported fn is
skipped, not type-checked — that needs a module loader). The compiler's own four files emit
valid C and self-host (tests/test_bootstrap.py); this gate is parse + resolve + type-check.
"""
import glob
from pathlib import Path

import pytest

from _selfhost import HEAD, emit_c_for, check_errors

STD_FILES = sorted(glob.glob("zen/std/*.zen"))


def _source(path):
    return Path(path).read_text()   # the real file, imports included — no stripping


@pytest.mark.parametrize("path", STD_FILES, ids=[p.split("/")[-1] for p in STD_FILES])
def test_self_hosted_frontend_reads_stdlib_file(tmp_path, path):
    out = emit_c_for(tmp_path, _source(path))
    # it must emit the zslice header plus at least one declaration (or, for an all-templates
    # file like iter.zen, just the header — templates inline at use, nothing standalone).
    assert out.startswith(HEAD)
    assert len(out) >= 50


# The CHECK dimension: the self-hosted VALIDATING checker (check_module) over each REAL file,
# returning its error count. ALL 10 are accepted with ZERO errors — generics (iter, vec), traits
# (alloc), closures, imports. So the self-hosted FRONTEND parses AND type-checks the whole real
# stdlib as written, matching the Python frontend's verdict.
@pytest.mark.parametrize("path", STD_FILES, ids=[p.split("/")[-1] for p in STD_FILES])
def test_self_hosted_checker_accepts_stdlib_file(tmp_path, path):
    assert check_errors(tmp_path, _source(path)) == 0
