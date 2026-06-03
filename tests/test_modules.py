"""Goal Arc 1 — cross-module type-checking. The self-hosted checker can resolve a call to an
IMPORTED function against the exporting module's signature, so a cross-module call is arity- and
arg-type-checked exactly like a local one — `check_linked(file, lib)` links a file against an
imported module's header (each function reduced to a bodyless DForeign signature).

Before this, an imported name was known-but-unchecked (#204): the checker had no signature for it,
so any call shape was accepted. Linking supplies the signature.
"""
import pytest

from _selfhost import check_linked_errors, check_errors

LIB = "add* = (a: i32, b: i32) i32 { a + b }\nnarrow* = (b: u8) i32 { 0 }"


@pytest.mark.parametrize("call,want", [
    ("add(1, 2)", 0),          # correct arity + types
    ("add(1)", 1),             # too few args
    ("add(1, 2, 3)", 1),       # too many args
])
def test_cross_module_arity(tmp_path, call, want):
    src = "{ add } = std.lib\nuse* = () i32 { %s }" % call
    assert check_linked_errors(tmp_path, src, LIB) == want


def test_cross_module_arg_type(tmp_path):
    # passing an i64 where the imported fn wants a u8 narrows -> rejected, same as a local call.
    src = "{ narrow } = std.lib\nuse* = (m: i64) i32 { narrow(m) }"
    assert check_linked_errors(tmp_path, src, LIB) == 1
    # a u8 fits -> accepted.
    ok = "{ narrow } = std.lib\nuse* = (b: u8) i32 { narrow(b) }"
    assert check_linked_errors(tmp_path, ok, LIB) == 0


def test_name_absent_from_header_is_unchecked(tmp_path):
    # `missing` isn't in LIB's header -> it stays known-but-unchecked (the #204 import path), so a
    # partial/foreign header never false-rejects.
    src = "{ missing } = std.lib\nuse* = () i32 { missing(1, 2, 3, 4) }"
    assert check_linked_errors(tmp_path, src, LIB) == 0


def test_linking_is_what_enables_the_check(tmp_path):
    # WITHOUT linking, the same wrong-arity cross-module call is accepted (imported = unchecked);
    # WITH linking it's rejected. This isolates what Arc 1 adds.
    src = "{ add } = std.lib\nuse* = () i32 { add(1) }"
    assert check_errors(tmp_path, src) == 0          # unlinked: known-but-unchecked
    assert check_linked_errors(tmp_path, src, LIB) == 1   # linked: checked against the signature
