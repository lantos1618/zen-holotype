"""Phase 6 reject-parity — undefined-name detection. The self-hosted checker (check_module) flags
a call to a name that is neither a local decl, an imported name, nor a compiler intrinsic — a typo
or a missing import — matching the Python frontend's verdict.

This was gated on foreign-decl + import recording: without them, libc bindings and `{ f } = std.x`
imports looked "undefined," so every unknown call had to be waved through. Now they're KNOWN, so a
genuinely unknown call can be rejected.
"""
import pytest

from _selfhost import check_errors


@pytest.mark.parametrize("src", [
    # a bare undefined call
    "t* = () i32 { nope(3) }",
    # an undefined call nested in an argument
    "id* = (n: i32) i32 { n }\nt* = () i32 { id(nope(3)) }",
    # a typo of a real local function
    "square* = (n: i32) i32 { n * n }\nt* = () i32 { squrae(3) }",
])
def test_undefined_call_is_rejected(tmp_path, src):
    assert check_errors(tmp_path, src) > 0


@pytest.mark.parametrize("src", [
    # a local fn, used before its definition (whole-module resolution)
    "t* = () i32 { sq(4) }\nsq* = (n: i32) i32 { n * n }",
    # a foreign binding (bodyless) — known by signature
    "ext = (n: i32) i32\nt* = () i32 { ext(3) }",
    # compiler intrinsics (addr/load) are always known
    "t* = () i32 { x := 5\n load(addr(x)) }",
    # an imported name is known-but-unchecked, not undefined
    "{ view } = std.str\nt* = (s: str) i32 { view(s, 0, 1)\n 0 }",
])
def test_defined_call_is_accepted(tmp_path, src):
    assert check_errors(tmp_path, src) == 0
