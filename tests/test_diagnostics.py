"""Diagnostics (goal #22): a type error's message carries its structured source
location (a `Located` string), and the report renders a caret straight from that
location — no re-parsing of the formatted text."""
from zen.types import Located
from zen.main import caret, check, build_space, build_scopes, resolve
from zen.parser import parse


def test_located_is_a_string_but_carries_structure():
    d = Located("m:2:5: bad", ns="m", pos=(1, 4))
    assert d == "m:2:5: bad"                  # it IS the message string
    assert "bad" in d and d.startswith("m:")  # str ops still work
    assert d.ns == "m" and d.pos == (1, 4)    # …plus the structured location


def test_check_attaches_a_location_to_failures():
    files = {"m": parse("f* = (a: i32, b: bool) i32 { a + b }", "m")}
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    (_, ok, why), = [r for r in check(files, space)[0] if r[0] == "m.f"]
    assert ok is False
    assert isinstance(why, Located) and why.ns == "m" and why.pos is not None


def test_caret_renders_from_structure(tmp_path):
    (tmp_path / "m.zen").write_text("a* = () i32 { 1 }\nbad* = () i32 { x + y }")
    why = Located("m:2:16: unbound", ns="m", pos=(1, 15))     # 0-based row,col
    out = caret(str(tmp_path), why)
    line, mark = out.strip("\n").split("\n")
    assert line.strip() == "bad* = () i32 { x + y }"
    assert mark.endswith("^") and mark.index("^") == 8 + 15   # 8 indent + col 15 → over `x`


def test_caret_empty_without_a_location(tmp_path):
    assert caret(str(tmp_path), "just a plain string") == ""
    assert caret(str(tmp_path), Located("x", ns="m", pos=(99, 0))) == ""   # off the end
