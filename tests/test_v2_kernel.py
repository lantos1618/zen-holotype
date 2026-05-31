"""v2 kernel: the whole program folds into the one trie — structure is the symbol table."""
import pytest
from holotype.v2.parser import parse
from holotype.v2.kernel import into_trie
from holotype.types import Unresolved, Conflict


def test_structure_becomes_paths():
    ns = into_trie(parse(
        "Circle = { r: i32 }\n"
        "Circle.Area = { area = () i32 { @self.r } }\n"
        "Tax = Free | Rate : i32\n"))
    for p in ["Circle", "Circle.r", "Circle.Area", "Circle.Area.area",
              "Tax", "Tax.Free", "Tax.Rate"]:
        ns.walk(p)                       # all resolve — the impl/method nest under the type
    with pytest.raises(Unresolved):
        ns.walk("Circle.nope")


def test_two_decls_one_path_conflict():
    with pytest.raises(Conflict):
        into_trie(parse("Foo = 1\nFoo = 2\n"))
