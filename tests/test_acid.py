"""Phase 6 (acid test) — the self-hosted compiler BINARY reads the WHOLE real stdlib, AS-IS.

Every std/*.zen file is fed THROUGH the self-hosted EMIT binary (parse_module -> resolve_module
-> genModule, all the Zen-written frontend compiled to the committed bootstrap C) verbatim —
imports and all, no pre-processing. The binary PARSES + RESOLVES + emits C for every real stdlib
file (generics in iter/vec, traits in alloc, structs, enums, closures, @while) with no crash and a
non-trivial emission. NO Python is in the loop: `_oracle` drives only `cc` + the committed binary.

NOTE on what's NOT this gate (and why it differs from the old Python-host acid test): the binary's
CHECK mode is a FLAT single-module checker with no module resolver, so it can't type-check a real
std file's `{ … } = std.x` cross-module imports (those symbols would count as undefined). The old
acid test got a zero-error CHECK verdict only because the Python host resolved all std.* modules
into one namespace — that cross-module type-check moves to a future module loader. What the binary
DOES gate here is parse + resolve + codegen over the full, unstripped stdlib; the compiler's own
files additionally self-host (tests/test_bootstrap.py), and the per-construct CHECK/value behavior
is gated by the oracle corpus (tests/test_oracle.py).
"""
import glob
from pathlib import Path

import pytest

from _oracle import HEAD, emit_c_for

STD_FILES = sorted(glob.glob("zen/std/*.zen"))


def _source(path):
    return Path(path).read_text()   # the real file, imports included — no stripping


@pytest.mark.parametrize("path", STD_FILES, ids=[p.split("/")[-1] for p in STD_FILES])
def test_self_hosted_frontend_reads_stdlib_file(path):
    out = emit_c_for(_source(path))
    # it must emit the zslice header plus at least one declaration (or, for an all-templates
    # file like iter.zen, just the header — templates inline at use, nothing standalone).
    assert out.startswith(HEAD)
    assert len(out) >= 50
