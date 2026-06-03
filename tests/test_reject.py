"""Phase 6 — reject-parity: the self-hosted checker (check_module) catches errors, not just
accepts valid code. Toward "same accept/reject as the Python frontend".

Each program is run through parse_module -> resolve_module -> check_module; the error count is
the process exit code. Valid programs give 0; the listed bugs give >= 1.

Scope today: call ARITY, arg-TYPE fit, and RETURN-type mismatches — both CATEGORY (str/bool/
struct where another is declared) AND computed numeric NARROWING (an i64-returning call declared
i32). A polymorphic int LITERAL returned to a numeric type is fine (`(…) u8 { 10 }`); a Cond that
mixes a literal and a typed branch takes the typed branch's type (so `esc_byte` checks clean).
"""
import pytest

from _selfhost import check_errors as _errors


@pytest.mark.parametrize("src", [
    "f* = (n: i32) i32 { n + 1 }",
    "f* = (a: i32, b: i32) bool { a < b }",
    "g* = (n: i32) u8 { 10 }",                       # int literal -> u8 is fine (polymorphic)
    "id* = (s: str) str { s }",
    "Pt*: { x: i32 }\nf* = (p: Pt) i32 { p.x }",
])
def test_checker_accepts_valid(tmp_path, src):
    assert _errors(tmp_path, src) == 0


@pytest.mark.parametrize("src", [
    'f* = (n: i32) i32 { "hi" }',                    # str returned where i32 declared
    "f* = (n: i32) i32 { n < 5 }",                   # bool returned where i32 declared
    "f* = (n: i32) str { n }",                       # i32 returned where str declared
    "f* = (a: i32) i32 { a }\ng* = () i32 { f(1, 2) }",   # arity: f takes 1, called with 2
    "g* = () i64 { 5 }\nf* = () i32 { g() }",             # computed i64 narrowed to i32
])
def test_checker_rejects_invalid(tmp_path, src):
    assert _errors(tmp_path, src) >= 1


@pytest.mark.parametrize("src", [
    "f* = () i32 { x := 5\n x = \"hi\"\n x }",       # str assigned to a numeric local
    "f* = () i32 { x := 5\n x = (3 < 4)\n x }",     # bool assigned to a numeric local
])
def test_checker_rejects_assignment_mismatch(tmp_path, src):
    assert _errors(tmp_path, src) >= 1


@pytest.mark.parametrize("src", [
    "f* = () i32 { x := 5\n x = 99\n x }",          # polymorphic int literal -> numeric local: fine
    "f* = () i32 { x := 5\n x = x + 1\n x }",
])
def test_checker_accepts_valid_assignment(tmp_path, src):
    assert _errors(tmp_path, src) == 0


@pytest.mark.parametrize("src", [
    # xs[i] = v where v doesn't fit the element type
    "mk* = (a: Ptr<Malloc>) [i32] { slice(heap(8), 2) }\n"
    "f* = (a: Ptr<Malloc>) i32 { b := addr(mk)\n b[0] = (3 < 4)\n 0 }".replace("addr(mk)", "a.mk()"),
])
def test_checker_rejects_index_store_mismatch(tmp_path, src):
    assert _errors(tmp_path, src) >= 1


@pytest.mark.parametrize("src", [
    "mk* = (a: Ptr<Malloc>) [i32] { slice(heap(8), 2) }\n"
    "f* = (a: Ptr<Malloc>) i32 { b := a.mk()\n b[0] = 7\n 0 }",   # literal store: fine
])
def test_checker_accepts_index_store(tmp_path, src):
    assert _errors(tmp_path, src) == 0


# operand-type checking: arithmetic needs numeric operands, logical needs bool — matching the Python
# frontend. Sound: an uninferable operand is skipped, comparisons accept any operands.
@pytest.mark.parametrize("src,want", [
    ("t* = (b: bool) i32 { (1 + b) }", 1),                                      # '+' on a bool
    ("t* = () i32 { (true && 5).match({ true => 1, false => 0 }) }", 1),        # '&&' on an int
    ("t* = () i32 { 1 + 2 * 3 }", 0),                                           # all numeric -> ok
    ("t* = (a: bool, b: bool) i32 { (a && b).match({ true => 1, false => 0 }) }", 0),  # all bool -> ok
    ("t* = () i32 { (3 < 5).match({ true => 1, false => 0 }) }", 0),            # comparison unchecked
])
def test_operand_type_checking(tmp_path, src, want):
    assert _errors(tmp_path, src) == want


# index validation: `seq[idx]` needs a slice seq and a numeric idx — matching the Python frontend.
@pytest.mark.parametrize("src,want", [
    ("f* = (xs: [i32]) i32 { xs[(3 < 4)] }", 1),          # bool index
    ("f* = (n: i32) i32 { n[0] }", 1),                     # indexing a non-slice
    ("f* = (xs: [i32]) i32 { xs[0] }", 0),                 # numeric literal index -> ok
    ("f* = (xs: [i32], i: i32) i32 { xs[i] }", 0),         # numeric var index -> ok
])
def test_index_validation(tmp_path, src, want):
    assert _errors(tmp_path, src) == want


# struct-literal validation: every init field must exist on the struct and its value must fit the
# field type. Matching the Python frontend; missing fields are allowed (partial init). Generic/
# imported struct literals are skipped (sound).
@pytest.mark.parametrize("src,want", [
    ("P*: { x: i32 }\nt* = () i32 { P{ x: (3 < 4) }.x }", 1),       # bool value for an i32 field
    ("P*: { x: i32 }\nt* = () i32 { P{ x: 1, z: 2 }.x }", 1),       # unknown field z
    ("P*: { x: i32 }\nt* = () i32 { P{ x: 5 }.x }", 0),             # correct -> ok
    ("P*: { x: i32, y: i32 }\nt* = () i32 { P{ x: 1 }.x }", 0),     # missing field allowed (partial init)
    ("P*: { b: u8 }\nt* = () i32 { P{ b: 5 }.b }", 0),              # polymorphic literal fits a u8 field
])
def test_struct_literal_validation(tmp_path, src, want):
    assert _errors(tmp_path, src) == want


# field-access validation: `obj.field` must name a real field of obj's struct — matching the Python
# frontend ("no field 'nope' on P"). Handles value (Member) and Ptr (Arrow) receivers; sound (an
# uninferable receiver / enum / generic instance is skipped).
@pytest.mark.parametrize("src,want", [
    ("P*: { x: i32 }\nf* = (p: P) i32 { p.nope }", 1),              # bad field, value receiver
    ("P*: { x: i32 }\nf* = (p: Ptr<P>) i32 { p.nope }", 1),         # bad field, ptr receiver
    ("P*: { x: i32 }\nf* = (p: P) i32 { p.x }", 0),                 # valid field
    ("P*: { x: i32 }\nf* = (p: Ptr<P>) i32 { p.x }", 0),            # valid field through a ptr
])
def test_field_access_validation(tmp_path, src, want):
    assert _errors(tmp_path, src) == want
