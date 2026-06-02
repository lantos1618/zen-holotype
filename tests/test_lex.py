"""std.lex — a lexer written IN zen, the first piece of the self-hosted front-end.

It reads the source RAW (a `str` is a const char*, so `load(offset(src, i))` gives a
byte — no slices, so genc can lower it) and emits tokens as spans { kind, start, len }
into the source. These tests compile a small zen driver around the lexer and check its
output: scan() printing each token as `<kind-letter>:<lexeme>`, count() returning a
token count, and tokenize() building then walking the materialized cons-list.
"""
import subprocess

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def run_driver(tmp_path, src):
    """Compile + run a zen `main* () i32` driver; return (stdout, exit_code)."""
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(tmp_path / "o.c"), "-o", str(tmp_path / "o")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    done = subprocess.run([str(tmp_path / "o")], capture_output=True, text=True)
    return done.stdout, done.returncode


# A driver that walks scan() to Eof, printing "<kind>:<lexeme>\n" per token. Kind letters:
# I dent · N umber · S tring · Y symbol · E of.
SCAN_DRIVER = """
{ Scan, Token, TokKind, scan, byte_at } = std.lex
putchar = (c: i32) i32
kind_char = (k: TokKind) i32 { k.match { .Ident => 73, .Int => 78, .Str => 83, .Sym => 89, .Eof => 69 } }
is_eof = (k: TokKind) bool { k.match { .Eof => true, _ => false } }
emit_span = (src: str, start: i32, len: i32) void {
    i := start
    e := start + len
    @while(i < e) {
        putchar(byte_at(src, i))
        i = i + 1
    }
}
main* = () i32 {
    src := %s
    pos := 0
    done := false
    @while(done == false) {
        sc := scan(src, pos)
        putchar(kind_char(sc.tok.kind))
        putchar(58)
        emit_span(src, sc.tok.start, sc.tok.len)
        putchar(10)
        pos = sc.next
        done = is_eof(sc.tok.kind)
    }
    0
}
"""

# Build the cons-list via tokenize(), then WALK it, printing each node's kind:lexeme —
# proof the list holds the real tokens (Eof is the terminal Nil, not a node).
LIST_DRIVER = """
{ Malloc } = std.alloc
{ TokList, TokCell, TokKind, tokenize, byte_at } = std.lex
putchar = (c: i32) i32
kind_char = (k: TokKind) i32 { k.match { .Ident => 73, .Int => 78, .Str => 83, .Sym => 89, .Eof => 69 } }
emit_span = (src: str, start: i32, len: i32) void {
    i := start
    e := start + len
    @while(i < e) {
        putchar(byte_at(src, i))
        i = i + 1
    }
}
emit_cell = (src: str, c: TokCell) i32 {
    putchar(kind_char(c.head.kind))
    putchar(58)
    emit_span(src, c.head.start, c.head.len)
    putchar(10)
    walk(src, c.tail)
}
walk = (src: str, l: Ptr<TokList>) i32 { l.match { .Nil => 0, .Cons(c) => emit_cell(src, c) } }
main* = () i32 {
    src := %s
    m := Malloc { _: 0 }
    walk(src, addr(m).tokenize(src))
}
"""


def scan_tokens(tmp_path, literal):
    return run_driver(tmp_path, SCAN_DRIVER % literal)[0]


def count_tokens(tmp_path, literal):
    return run_driver(tmp_path, "{ count } = std.lex\nmain* = () i32 { count(%s) }\n" % literal)[1]


def walk_list(tmp_path, literal):
    return run_driver(tmp_path, LIST_DRIVER % literal)[0]


def test_idents_ints_syms_strings_and_comments(tmp_path):
    # identifiers, an int, a symbol, a // line-comment (skipped), a string (quotes kept
    # in the span), then Eof with an empty lexeme.
    out = scan_tokens(tmp_path, r'"foo = 42 // hi\n\"hey\" bar"')
    assert out == "I:foo\nY:=\nN:42\nS:\"hey\"\nI:bar\nE:\n"


def test_multi_char_operators_lex_as_one_token(tmp_path):
    # the two-char operators glue into a single Sym; a lone `*` stays one byte.
    out = scan_tokens(tmp_path, r'"x := y == z"')
    assert out == "I:x\nY::=\nI:y\nY:==\nI:z\nE:\n"
    assert scan_tokens(tmp_path, r'"a*b"') == "I:a\nY:*\nI:b\nE:\n"


def test_underscore_and_digits_in_identifiers(tmp_path):
    # an identifier is alpha/underscore then alnum; `_x9` is one Ident, `0` a separate Int.
    out = scan_tokens(tmp_path, r'"_x9 0"')
    assert out == "I:_x9\nN:0\nE:\n"


def test_only_whitespace_and_comment_yields_just_eof(tmp_path):
    assert scan_tokens(tmp_path, r'"   // nothing here\n  "') == "E:\n"


def test_count_walks_the_whole_stream(tmp_path):
    assert count_tokens(tmp_path, r'"foo = 42 // hi\n\"hey\" bar"') == 5   # foo = 42 "hey" bar
    assert count_tokens(tmp_path, r'""') == 0                              # empty -> just Eof
    assert count_tokens(tmp_path, r'"a*b"') == 3                           # a * b


def test_materialized_cons_list_holds_the_real_tokens(tmp_path):
    # the heap cons-list, walked, yields exactly the 5 tokens — same stream scan produced.
    out = walk_list(tmp_path, r'"foo = 42 // hi\n\"hey\" bar"')
    assert out == "I:foo\nY:=\nN:42\nS:\"hey\"\nI:bar\n"
