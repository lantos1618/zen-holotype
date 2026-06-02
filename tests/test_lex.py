"""std.lex — a lexer written IN zen, the first piece of the self-hosted front-end.

It reads the source RAW (a `str` is a const char*, so `load(offset(src, i))` gives a
byte — NO slices, so genc can lower this later) and emits tokens as spans { kind, start,
len } into the source (no allocation). These tests compile a zen driver that scans a
snippet and prints each token as `<kind-letter>:<lexeme>`, then assert the exact stream.
"""
import subprocess

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)

# a driver that walks scan() to Eof, printing "<kind>:<lexeme>\n" per token. Kind letters:
# I dent · N umber · S tring · Y symbol · E of.
DRIVER = """
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


def tokenize(tmp_path, zen_string_literal):
    """Compile + run the driver over the given zen *source-literal*; return its stdout."""
    (tmp_path / "main.zen").write_text(DRIVER % zen_string_literal)
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
    return subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout


def test_idents_ints_syms_strings_and_comments(tmp_path):
    # identifiers, an int, a symbol, a // line-comment (skipped), a string (quotes kept
    # in the span), then Eof with an empty lexeme.
    out = tokenize(tmp_path, r'"foo = 42 // hi\n\"hey\" bar"')
    assert out == "I:foo\nY:=\nN:42\nS:\"hey\"\nI:bar\nE:\n"


def test_adjacent_symbols_scan_one_byte_each(tmp_path):
    # symbols are single-char for now: `*:|` lexes as three Sym tokens.
    out = tokenize(tmp_path, r'"a*b"')
    assert out == "I:a\nY:*\nI:b\nE:\n"


def test_underscore_and_digits_in_identifiers(tmp_path):
    # an identifier is alpha/underscore then alnum; `_x9` is one Ident, `0` a separate Int.
    out = tokenize(tmp_path, r'"_x9 0"')
    assert out == "I:_x9\nN:0\nE:\n"


def test_only_whitespace_and_comment_yields_just_eof(tmp_path):
    out = tokenize(tmp_path, r'"   // nothing here\n  "')
    assert out == "E:\n"


# count() recursively walks the ENTIRE stream (scan -> Eof) — proof that the token stream
# needs no materialized list: pure positional scan IS the stream.
COUNT_DRIVER = '{ count } = std.lex\nmain* = () i32 { count(%s) }\n'


def count(tmp_path, zen_string_literal):
    (tmp_path / "main.zen").write_text(COUNT_DRIVER % zen_string_literal)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")]).returncode


def test_count_walks_the_whole_stream(tmp_path):
    assert count(tmp_path, r'"foo = 42 // hi\n\"hey\" bar"') == 5   # foo = 42 "hey" bar
    assert count(tmp_path, r'""') == 0                              # empty -> just Eof
    assert count(tmp_path, r'"a*b"') == 3                           # a * b
