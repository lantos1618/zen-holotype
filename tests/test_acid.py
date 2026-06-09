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
from pathlib import Path

import pytest

from _oracle import HEAD, emit_c_for

ROOT = Path(__file__).resolve().parent.parent
SOURCE_FILES = sorted([str(p.relative_to(ROOT)) for p in (ROOT / "zen" / "std").glob("*.zen")] +
                      [str(p.relative_to(ROOT)) for p in (ROOT / "zen" / "compiler").glob("*.zen")])


def _source(path):
    return (ROOT / path).read_text()   # the real file, imports included — no stripping


@pytest.mark.parametrize("path", SOURCE_FILES, ids=[p.split("/")[-1] for p in SOURCE_FILES])
def test_self_hosted_frontend_reads_source_file(path):
    out = emit_c_for(_source(path))
    # it must emit the zslice header plus at least one declaration (or, for an all-templates
    # file like iter.zen, just the header — templates inline at use, nothing standalone).
    assert out.startswith(HEAD)
    assert len(out) >= 50
