"""S1 module-resolver PROTOTYPE — the self-hosted replacement for generate.py's strip_imports.

generate.py today flat-concatenates the std SOURCES with imports STRIPPED (compiler_source /
strip_imports, in Python) and feeds ONE flat file to the zenc binary. The binary cannot resolve
`{ a, b } = std.x` imports itself. std.resolve (a @self-hosted-only module) is the start of moving
that pre-processing INTO Zen: it carries the exact line-classifier strip_imports uses.

This test proves the load-bearing slice — that a pure-Zen function classifies "import lines"
EXACTLY as Python's strip_imports does — two ways:

  1. run_value: the classifier, compiled + run by the self-hosted toolchain, returns the right
     count of KEPT (non-import) lines for hand-picked cases.
  2. differential: over the REAL compiler SOURCES (generate.py's SOURCES list), the Zen
     classifier's kept-line count equals Python strip_imports' kept-line count, byte-decision for
     byte-decision. If these agree on every line of every real module, Zen can produce the same
     flat source compiler_source() produces.

NB self-containment: a run_value binary links only the driver's own functions (std templates like
std.lex.byte_at are emitted at use, not as standalone symbols). So the classifier under test here
INLINES byte access (load(offset(...))) — it is the SAME logic as zen/std/resolve.zen, which acid
(test_acid.py) checks as a real module importing std.lex.byte_at.
"""
import subprocess

import pytest

from _selfhost import HEAD, emit_c_for
from bootstrap.generate import strip_imports, SOURCES, ROOT


# The classifier, self-contained (inline byte access). Mirrors zen/std/resolve.zen exactly.
# `test()` returns strip_count of the embedded source: the number of lines strip_imports KEEPS.
_CLASSIFIER = r"""
byte_at = (s: str, i: i32) u8 { load(offset(s, i)) }
is_ws = (b: u8) bool { (b == ' ') || (b == 9) }
lstrip = (s: str, p: i32) i32 {
    byte_at(s, p).is_ws().match ({ true => lstrip(s, p + 1), false => p })
}
opens_import = (s: str, p: i32) bool { (byte_at(s, p) == '{') && (byte_at(s, p + 1) == ' ') }
is_marker_at = (s: str, p: i32) bool {
    (byte_at(s, p) == '=') && (byte_at(s, p + 1) == ' ') && (byte_at(s, p + 2) == 's')
        && (byte_at(s, p + 3) == 't') && (byte_at(s, p + 4) == 'd') && (byte_at(s, p + 5) == '.')
}
has_std_marker = (s: str, p: i32) bool {
    b := byte_at(s, p)
    ((b == 0) || (b == 10)).match ({
        true  => false,
        false => is_marker_at(s, p).match ({ true => true, false => has_std_marker(s, p + 1) })
    })
}
is_import_line = (s: str, p: i32) bool {
    ls := lstrip(s, p)
    opens_import(s, ls).match ({ true => has_std_marker(s, ls), false => false })
}
next_line = (s: str, p: i32) i32 {
    b := byte_at(s, p)
    (b == 0).match ({
        true  => p,
        false => (b == 10).match ({ true => p + 1, false => next_line(s, p + 1) })
    })
}
strip_count = (s: str, p: i32, n: i32) i32 {
    (byte_at(s, p) == 0).match ({
        true  => n,
        false => strip_count(s, next_line(s, p), is_import_line(s, p).match ({ true => n, false => n + 1 }))
    })
}
test* = () i32 { strip_count("%s", 0, 0) }
"""


def _zlit(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _zen_kept_count(tmp_path, src):
    """Run the self-hosted classifier over `src`; return its strip_count (kept-line count).

    NB the value is PRINTED to stdout (printf), NOT returned as the process exit code — a kept-line
    count can exceed 255 (real compiler sources keep ~1000 lines) and an exit code truncates mod 256.
    """
    prog = _CLASSIFIER % _zlit(src)
    emitted = emit_c_for(tmp_path, prog)
    assert emitted.startswith(HEAD)
    body = emitted[len(HEAD):]
    c = ("#include <stdint.h>\n#include <stdbool.h>\n#include <stdio.h>\n" + HEAD + "\n" + body
         + '\nint main(void){ printf("%d", test()); return 0; }\n')
    (tmp_path / "g.c").write_text(c)
    assert subprocess.run(["cc", "-std=gnu11", "-w", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    out = subprocess.run([str(tmp_path / "g")], capture_output=True, text=True).stdout
    return int(out)


def _py_kept_count(src):
    """The Python reference: lines strip_imports keeps."""
    return sum(1 for l in src.splitlines()
               if not (l.strip().startswith("{ ") and "= std." in l))


@pytest.mark.parametrize("src,kept", [
    ("a = 1\n{ x } = std.foo\nb = 2\n", 2),                        # one import in the middle
    ("{ A, B } = std.string\n{ heap } = std.alloc\nf = 1\n", 1),   # leading imports
    ("  { x } = std.y\nplain\n", 1),                               # indented import (lstrip)
    ("{ not_import }\n{ also } = local.thing\n", 2),               # `{ ` but no `= std.` -> kept
    ("no_imports_here = 5\n", 1),                                  # nothing to strip
])
def test_classifier_kept_count(tmp_path, src, kept):
    """The self-hosted classifier counts kept lines correctly, and agrees with Python."""
    assert _zen_kept_count(tmp_path, src) == kept
    assert _py_kept_count(src) == kept


@pytest.mark.parametrize("path", SOURCES, ids=[p.split("/")[-1] for p in SOURCES])
def test_matches_strip_imports_on_real_sources(tmp_path, path):
    """The DIFFERENTIAL gate: over each REAL compiler source, the Zen classifier keeps EXACTLY the
    lines Python strip_imports keeps. (strip_imports returns the kept lines joined by \\n, so its
    line count is len(splitlines).) Agreement here = Zen can reproduce compiler_source()."""
    src = (ROOT / path).read_text()
    py_kept = len(strip_imports(path).splitlines())
    assert py_kept == _py_kept_count(src)            # sanity: our oracle == strip_imports itself
    assert _zen_kept_count(tmp_path, src) == py_kept
