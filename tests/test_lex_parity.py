"""Lexer parity (Phase 8 gate): the Zen-written lexer (std.lex) must tokenize the same
way the reference grammar (tree-sitter) does.

We compare the two token streams over real declarations: tree-sitter's leaf tokens vs
std.lex's `scan`. They agree on boundaries and lexemes. The one principled difference is
KEYWORDS: std.lex is keyword-free by design (the *parser* tells `i32`/`match`/`true` from
a plain name by context), so a tree-sitter keyword token is counted here as the Ident
std.lex produces. `@`-constructs (`@while`, `@emit`, `@ident`) are a known divergence —
tree-sitter lexes `@x` as one identifier, std.lex as `@` + `x` — so they're excluded.
"""
import subprocess

import pytest

from zen.parser import _PARSER
from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)

_NAMED = {"identifier": "I", "integer": "N", "string": "S"}


def ts_tokens(src):
    """tree-sitter's leaf tokens as [(kind_letter, lexeme)] — keywords counted as Idents."""
    b = src.encode()
    out = []

    def walk(n):
        if n.child_count == 0 and n.type.strip() and n.type != "comment":
            tx = b[n.start_byte:n.end_byte].decode()
            if n.type in _NAMED:
                k = _NAMED[n.type]
            else:                                    # an anonymous token: a keyword -> Ident, else Sym
                k = "I" if (tx[:1].isalpha() or tx[:1] == "_") else "Y"
            out.append((k, tx))
        for c in n.children:
            walk(c)

    walk(_PARSER.parse(b).root_node)
    return out


# Drives std.lex over a source string and prints "<kind>:<lexeme>" per token (kinds:
# I dent / N umber / S tring / Y symbol / E of), exactly like ts_tokens' letters.
_DRIVER = """
{ TokKind, scan, byte_at } = std.lex
putchar = (c: i32) i32
kc = (k: TokKind) i32 { k.match { .Ident => 73, .Int => 78, .Str => 83, .Sym => 89, .Eof => 69 } }
is_eof = (k: TokKind) bool { k.match { .Eof => true, _ => false } }
sp = (src: str, s: i32, l: i32) void { i := s\n e := s + l\n @while(i < e) { putchar(byte_at(src, i))\n i = i + 1 } }
main* = () i32 {
    src := "%s"
    pos := 0
    done := false
    @while(done == false) {
        c := scan(src, pos)
        putchar(kc(c.tok.kind))
        putchar(58)
        sp(src, c.tok.start, c.tok.len)
        putchar(10)
        pos = c.next
        done = is_eof(c.tok.kind)
    }
    0
}
"""


def _zen_literal(src):
    return src.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def zen_tokens(tmp_path, src):
    """std.lex's tokens as [(kind_letter, lexeme)] — the trailing Eof dropped."""
    (tmp_path / "main.zen").write_text(_DRIVER % _zen_literal(src))
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    out = subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout
    toks = [(line[0], line[2:]) for line in out.splitlines() if line]
    assert toks and toks[-1][0] == "E"               # std.lex ends every stream with Eof
    return toks[:-1]


SNIPPETS = [
    "f* = () i32 { 1 + 2 * 3 }",
    "g* = (x: i32, y: i32) i32 { x + y }",
    "h* = () i32 { a := 10\n b := a - 1\n a + b }",
    "Pt*: { x: i32, y: i32 }",
    "k* = () i32 { (1 + 2) * (3 - 4) }",
    "cmp* = (x: i32) bool { x <= 3 }",
]


@pytest.mark.parametrize("src", SNIPPETS)
def test_std_lex_matches_tree_sitter(tmp_path, src):
    assert zen_tokens(tmp_path, src) == ts_tokens(src)
