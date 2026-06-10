"""Phase 6 (acid test) — the self-hosted compiler BINARY reads the real stdlib/compiler sources, AS-IS.

Every std/*.zen and compiler/*.zen file is fed THROUGH the self-hosted EMIT binary (parse_module ->
resolve_module -> genModule, all the Zen-written frontend compiled to the committed bootstrap C)
verbatim — imports and all, no pre-processing. The binary PARSES + RESOLVES + emits C for every real
source file with no crash and a non-trivial emission. NO Python is in the loop: `_oracle` drives only
`cc` + the committed binary.

NOTE on what's NOT this gate: the binary's CHECK mode is a FLAT single-module checker with no module
resolver, so it can't type-check a real std file's `{ … } = std.x` cross-module imports (those
symbols would count as undefined). Cross-module type-checking is covered separately by the module
oracle tests. What this gate DOES cover is parse + resolve + codegen over the full, unstripped
stdlib; the compiler's own files additionally self-host (tests/test_bootstrap.py), and the
per-construct CHECK/value behavior is gated by the oracle corpus (tests/test_oracle.py).
"""
import re
from pathlib import Path

import pytest

from _oracle import HEAD, emit_c_for, emit_rc

ROOT = Path(__file__).resolve().parent.parent
SOURCE_FILES = sorted([str(p.relative_to(ROOT)) for p in (ROOT / "zen" / "std").glob("*.zen")] +
                      [str(p.relative_to(ROOT)) for p in (ROOT / "zen" / "compiler").glob("*.zen")])


def _source(path):
    return (ROOT / path).read_text()   # the real file, imports included — no stripping


# top-level non-generic, non-exported decls — generic `name = <T>(` decls don't match, and
# exported `name* = (` decls are excluded too (some inline at use, e.g. fn-typed params),
# so this pins a conservative subset whose names MUST survive into the C.
_DECL_RE = re.compile(r"^([a-zA-Z_]\w*)\s*=\s*\(", re.M)


@pytest.mark.parametrize("path", SOURCE_FILES, ids=[p.split("/")[-1] for p in SOURCE_FILES])
def test_self_hosted_frontend_reads_source_file(path):
    src = _source(path)
    assert emit_rc(src) == 0
    out = emit_c_for(src)
    # the emission must at least start with the zslice header (an all-templates file like
    # iter.zen may emit only the header — templates inline at use, nothing standalone) ...
    assert out.startswith(HEAD)
    # ... and every top-level non-generic declaration must survive into the emitted C.
    for name in _DECL_RE.findall(src):
        assert name in out, name
