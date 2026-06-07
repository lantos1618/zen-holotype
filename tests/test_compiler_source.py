"""Zen reproduces bootstrap/generate.py's compiler_source() — byte-for-byte, with NO Python.

generate.py.compiler_source() reads a FIXED ordered list of the compiler's own SOURCE files,
strips each file's `{ … } = std.x` import lines, and joins the results with "\n" — the flat module
the bootstrap binary consumes. This test proves a *Zen* program can produce the SAME bytes:

  1) We synthesize a self-contained Zen `main` that
       - inlines std.io's POSIX read_file (open/lseek/read/close + NUL-terminate),
       - inlines std.resolve's strip logic (is_import_line / strip_into / the per-file "\n" join),
       - reads the real SOURCES files, strips + concatenates them into one growable String,
       - write_file()s that flat source to disk and returns its length.
     (We INLINE rather than `import std.resolve` because there is no module resolver yet — std
      templates aren't emitted into a standalone test binary; resolve.zen/io.zen themselves are
      acid-checked, see tests/test_acid.py. The inlined bodies are verbatim copies of those modules.)
  2) The driver is compiled THROUGH the self-hosted toolchain (parse_module -> resolve_module ->
     genModule, all Zen), then the emitted C is cc'd and RUN — so the FFI + strip execute for real.
  3) Python reads the file the Zen binary wrote and asserts it == generate.py.compiler_source()
     BYTE-FOR-BYTE. That is the milestone: Zen, not Python, built the compiler's own flat source.

This touches neither generate.py nor the bootstrap path — it is a pure proof-of-capability.
"""
import subprocess
from pathlib import Path

import pytest

from _selfhost import HEAD, emit_c_for

import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import bootstrap.generate as gen


# The Zen driver. It mirrors, in inlined form, std.io.read_file + std.resolve.{is_import_line,
# strip_into, append_span, ...}. SOURCES paths + the output path are formatted in by Python.
# It returns the number of bytes written, which the harness checks == len(compiler_source()).
#
# Notes on the inlining:
#  - `read_file` here returns the heap str (caller owns it) exactly like std.io.read_file.
#  - `strip_one` folds one file's stripped body into the SHARED output String `out`, emitting a
#    leading "\n" before the file's first kept line ONLY when `out` already holds prior files
#    (parameter `sep`). Within a file, kept lines are separated by "\n" (parameter `first`).
#    Composed over all files this yields exactly  "\n".join(strip_imports(p) for p in SOURCES).
_DRIVER = r"""
malloc = (n: i64) RawPtr<u8>
realloc = (p: RawPtr<u8>, n: i64) RawPtr<u8>
strlen = (s: str) i64
memcpy = (dst: RawPtr<u8>, src: RawPtr<u8>, n: i64) RawPtr<u8>
open  = (path: str, flags: i32, mode: i32) i32
read  = (fd: i32, buf: RawPtr<u8>, n: i64) i64
write = (fd: i32, buf: RawPtr<u8>, n: i64) i64
close = (fd: i32) i32
lseek = (fd: i32, off: i64, whence: i32) i64

// ── std.io.read_file (inlined) ──────────────────────────────────────────────
read_file = (path: str) str {
    fd  := open(path, 0, 0)
    n   := lseek(fd, 0, 2)
    rw  := lseek(fd, 0, 0)
    buf := malloc(n + 1)
    rd  := read(fd, buf, n)
    store(offset(buf, n), 0)
    cl  := close(fd)
    cstr(buf)
}

// ── std.string (inlined: a growable byte String) ────────────────────────────
String: { ptr: RawPtr<u8>, len: i64, cap: i64 }
with_cap = (cap: i64) String { String { ptr: malloc(cap), len: 0, cap: cap } }
sgrow = (s: String, ncap: i64) String { String { ptr: realloc(s.ptr, ncap), len: s.len, cap: ncap } }
sreserve = (s: String, need: i64) String {
    (s.len + need > s.cap).match ({ true => sgrow(s, (s.cap + need) * 2), false => s })
}
spush = (s: String, b: u8) String {
    r := sreserve(s, 1)
    store(offset(r.ptr, r.len), b)
    String { ptr: r.ptr, len: r.len + 1, cap: r.cap }
}

// ── std.resolve (inlined: the import-line classifier + strip) ───────────────
byte_at = (s: str, i: i32) u8 { load(offset(s, i)) }
is_ws = (b: u8) bool { (b == ' ') || (b == 9) }
lstrip = (s: str, p: i32) i32 { byte_at(s, p).is_ws().match ({ true => s.lstrip(p + 1), false => p }) }
opens_import = (s: str, p: i32) bool { (s.byte_at(p) == '{') && (s.byte_at(p + 1) == ' ') }
is_marker_at = (s: str, p: i32) bool {
    (s.byte_at(p) == '=') && (s.byte_at(p + 1) == ' ') && (s.byte_at(p + 2) == 's')
        && (s.byte_at(p + 3) == 't') && (s.byte_at(p + 4) == 'd') && (s.byte_at(p + 5) == '.')
}
has_std_marker = (s: str, p: i32) bool {
    b := s.byte_at(p)
    ((b == 0) || (b == 10)).match ({
        true  => false,
        false => s.is_marker_at(p).match ({ true => true, false => s.has_std_marker(p + 1) })
    })
}
is_import_line = (s: str, p: i32) bool {
    ls := s.lstrip(p)
    s.opens_import(ls).match ({ true => s.has_std_marker(ls), false => false })
}
next_line = (s: str, p: i32) i32 {
    b := s.byte_at(p)
    (b == 0).match ({ true => p, false => (b == 10).match ({ true => p + 1, false => s.next_line(p + 1) }) })
}
line_end = (s: str, p: i32) i32 {
    b := s.byte_at(p)
    ((b == 0) || (b == 10)).match ({ true => p, false => s.line_end(p + 1) })
}
append_span = (out: String, s: str, p: i32, e: i32) String {
    (p == e).match ({ true => out, false => out.spush(s.byte_at(p)).append_span(s, p + 1, e) })
}
strip_into = (out: String, s: str, p: i32, first: bool) String {
    (s.byte_at(p) == 0).match ({
        true  => out,
        false => s.is_import_line(p).match ({
            true  => out.strip_into(s, s.next_line(p), first),
            false => first.match ({
                true  => out.append_span(s, p, s.line_end(p)).strip_into(s, s.next_line(p), false),
                false => out.spush(10).append_span(s, p, s.line_end(p)).strip_into(s, s.next_line(p), false)
            })
        })
    })
}
// fold ONE file into the shared output: emit a "\n" file-separator first iff `out` already has
// content (`sep`), then strip that file's body in. (`first` resets per-file inside strip_into.)
strip_one = (out: String, path: str, sep: bool) String {
    src := read_file(path)
    pre := sep.match ({ true => out.spush(10), false => out })
    pre.strip_into(src, 0, true)
}

// ── the build: fold SOURCES through strip_one, then write the flat source out ─
build = () String {
    out := with_cap(262144)
%s
    out
}
test* = () i64 {
    flat := build()
    wfd  := open(cstr("%s"), 577, 420)
    w    := write(wfd, flat.ptr, flat.len)
    cl   := close(wfd)
    flat.len
}
"""


def _build_driver(out_path):
    """Emit the per-file fold lines (out := out.strip_one("path", sep)) for the real SOURCES."""
    folds = []
    for i, p in enumerate(gen.SOURCES):
        sep = "true" if i > 0 else "false"
        folds.append('    out = out.strip_one(cstr("%s"), %s)' % (str(gen.ROOT / p), sep))
    return _DRIVER % ("\n".join(folds), str(out_path))


def test_zen_reproduces_compiler_source_byte_for_byte(tmp_path):
    out_path = tmp_path / "flat_from_zen.zen"
    driver = _build_driver(out_path)

    # The reference, AS BYTES. compiler_source() is a Python str (Unicode); the stdlib comments hold
    # non-ASCII UTF-8 (box-drawing rules, the 🏁 flag, …), so len(str) (code points) < len(utf-8 bytes).
    # Zen reads + writes raw BYTES, so the byte-exact comparison is against the UTF-8 ENCODING.
    reference = gen.compiler_source().encode("utf-8")
    want_len = len(reference)

    # compile the driver THROUGH the self-hosted toolchain, then build + run the emitted C.
    emitted = emit_c_for(tmp_path, driver)
    assert emitted.startswith(HEAD), emitted[:80]
    body = emitted[len(HEAD):]
    (tmp_path / "g.c").write_text(
        "#include <stdint.h>\n#include <stdbool.h>\n" + HEAD + "\n" + body
        + "\nint main(void){ return test() == %d ? 0 : 1; }\n" % want_len)
    assert subprocess.run(["cc", "-std=gnu11", "-w", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    # run: returns 0 iff the byte count the Zen binary wrote == len(compiler_source() utf-8 bytes)
    assert subprocess.run([str(tmp_path / "g")]).returncode == 0, "Zen flat length != compiler_source() byte length"

    # THE PROOF: the file the Zen binary wrote is byte-for-byte the Python reference.
    produced = out_path.read_bytes()
    assert produced == reference, (
        f"len(zen)={len(produced)} len(py)={len(reference)}; "
        f"first diff at {next((i for i, (a, b) in enumerate(zip(produced, reference)) if a != b), 'n/a')}")
