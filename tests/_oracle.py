"""Python-FREE self-hosted oracle for emitted values and checker verdicts.

The self-hosted `zenc` BINARY is the sole correctness reference: NO `zen.main` (the Python
reference frontend) is imported here. Two binaries, both built from the committed bootstrap C
(`cc` is the only toolchain in the loop — zero Python compiler):

  EMIT  binary  (bootstrap/{zenc.gen.c,zenrt.c,main.c})        — Zen source -> C on stdout
  CHECK binary  (a check-mode gen.c + check_main.c)            — exit code = check error count

`emit_value(src, want)` compiles `src` with the EMIT binary, compiles + runs the emitted C, and
returns the int `test()` computes (silent-miscompile guard: assert == want).
`verdict(src)` runs the CHECK binary; exit 0 == "accept", >0 == "reject" (reject-parity guard).

How the CHECK binary stays Python-free: the committed EMIT binary compiles the compiler sources
PLUS check_validate.zen (which the emit-only binary leaves out) into check-mode C, which `cc`
links with check_main.c. So `cc` + the committed `zenc` binary build BOTH — Python never runs.
(The import-strip+concat used to assemble the check-mode source is the same transform std.internal.resolve
reproduces byte-for-byte; here it's done in this harness's setup, OUTSIDE the per-test loop.)
"""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOT = ROOT / "bootstrap"
HEAD = "typedef struct { void* ptr; int64_t len; } zslice; "
_CC = ["cc", "-std=gnu11", "-w"]
_RUNNER = "\n#include <stdio.h>\nint main(void){ printf(\"%%lld\", (long long)(test())); return 0; }\n"

# The bootstrap sources come from bootstrap/sources.txt. The CHECK binary includes check_validate.zen;
# the emit-only binary omits that validating pass. Imports (`{...} = std.x` / `compiler.x`) are
# stripped, and runtime types come from zenrt.{h,c}. This mirrors bootstrap/main.c's source prep
# without duplicating the manifest order here.
def _bootstrap_compiler_sources(include_validate=False):
    out = []
    for raw in (BOOT / "sources.txt").read_text().splitlines():
        rel = raw.strip()
        if not rel or rel.startswith("#") or not (rel.startswith("zen/compiler/") or rel.startswith("zen/std/")):
            continue
        if rel.endswith("/check_validate.zen") and not include_validate:
            continue
        out.append(rel)
    return out


_EMIT_SOURCES = _bootstrap_compiler_sources()
_CHECK_SOURCES = _bootstrap_compiler_sources(include_validate=True)

# a CLI entry that returns check_module's error count as the process exit code.
_CHECK_MAIN = r"""#include "zenrt.h"
#include <stdio.h>
#include <stdlib.h>
zslice parse_module(Malloc* a, const char* src);
zslice resolve_module(Malloc* a, zslice decls);
int32_t check_module(Malloc* a, zslice decls);
int main(int argc, char** argv){
    size_t cap = 1<<20, len = 0; char* buf = malloc(cap);
    FILE* in = stdin;
    if (argc > 1){ in = fopen(argv[1], "r"); if (!in){ fprintf(stderr, "cannot open %s\n", argv[1]); return 2; } }
    int c; while ((c = fgetc(in)) != EOF){ if (len + 1 >= cap){ cap *= 2; buf = realloc(buf, cap); } buf[len++] = (char)c; }
    buf[len] = 0;
    Malloc m = { 0 };
    return check_module(&m, resolve_module(&m, parse_module(&m, buf)));
}
"""

# ── DIAGNOSTIC ERROR-KIND driver (check_validate.check_module_kind) ──────────────────────────────
# The CHECK binary above pins WHETHER a module is rejected (exit = error COUNT) but not WHY. This
# CHECK-KIND binary calls check_module_kind, which re-walks the SAME resolved AST in the SAME order
# and exits with the KIND code of the FIRST error (0 = accept, else 1..13 per the K* table in
# check_validate.zen). It lets a reject be asserted by REASON — so "rejected for the wrong reason"
# (e.g. an undefined-name reject that the corpus expected to be an arity reject) is now catchable.
# NO Python compiler — built from the same check-mode gen.c (which already contains check_module_kind
# from check_validate.zen) linked with this main. The COUNT path (check_module) is untouched.
_CHECK_KIND_MAIN = r"""#include "zenrt.h"
#include <stdio.h>
#include <stdlib.h>
zslice parse_module(Malloc* a, const char* src);
zslice resolve_module(Malloc* a, zslice decls);
int32_t check_module_kind(Malloc* a, zslice decls);
int main(int argc, char** argv){
    size_t cap = 1<<20, len = 0; char* buf = malloc(cap);
    FILE* in = stdin;
    if (argc > 1){ in = fopen(argv[1], "r"); if (!in){ fprintf(stderr, "cannot open %s\n", argv[1]); return 2; } }
    int c; while ((c = fgetc(in)) != EOF){ if (len + 1 >= cap){ cap *= 2; buf = realloc(buf, cap); } buf[len++] = (char)c; }
    buf[len] = 0;
    Malloc m = { 0 };
    /* check_module_kind packs the first error's byte offset alongside the kind (kind + pos*16,
     * U1.4 Phase 2); the exit code is 8-bit, so return the bare kind. */
    return check_module_kind(&m, resolve_module(&m, parse_module(&m, buf))) & 15;
}
"""

# the KIND codes, mirroring check_validate.zen's K* table. KIND_NAME maps a probe exit code to a label
# so a test can assert verdict_kind(src) == "arity" rather than a bare integer.
KIND_NAME = {
    0: "none", 1: "arity", 2: "arg-type", 3: "undefined-name", 4: "struct-field",
    5: "exhaustiveness", 6: "dup-variant", 7: "operand-type", 8: "index", 9: "return-fit",
    10: "assign-fit", 11: "conformance", 12: "dup-fn", 13: "value-pos-return",
    14: "parse",   # KPARSE — the parser's `__syntax_error` sentinel (parser-totality rejects)
}

# ── S1 CROSS-MODULE TYPE-CHECK driver (check_validate.check_linked) ─────────────────────────────
# The CHECK binary above type-checks ONE flat module and treats every `{…} = std.x` import as an
# undefined-but-tolerated name (the DImport "known-but-unchecked" path) — so it gates parse+resolve
# +typing of LOCAL code, but an imported call's arity/arg-types are NEVER verified. That was the
# proof deleting the Python frontend lost: that the stdlib type-checks as an inter-module WHOLE.
#
# check_linked recovers it. For a TARGET module, we gather the EXPORTED signatures of every std.x it
# imports (parse those modules; module_header reduces each `name* = (params) ret { … }` to a bodyless
# DForeign sig), prepend that header, and run check_module. Now an imported call resolves to the REAL
# signature in `the_func`, so check_call -> call_errs verifies arity AND arg types exactly like a
# local call — while the header's bodyless sigs are never re-checked (check_module only descends
# function BODIES). This main reads the target file + a concatenated lib file and exits with the
# cross-module error count. NO Python compiler — only the committed `zenc` binary + cc, as ever.
_CHECK_LINKED_MAIN = r"""#include "zenrt.h"
#include <stdio.h>
#include <stdlib.h>
zslice parse_module(Malloc* a, const char* src);
int32_t check_linked(Malloc* a, zslice decls, zslice lib);
static char* slurp(const char* path){
    FILE* in = fopen(path, "r"); if (!in){ fprintf(stderr, "cannot open %s\n", path); exit(2); }
    size_t cap = 1<<20, len = 0; char* buf = malloc(cap); int c;
    while ((c = fgetc(in)) != EOF){ if (len + 1 >= cap){ cap *= 2; buf = realloc(buf, cap); } buf[len++] = (char)c; }
    buf[len] = 0; fclose(in); return buf;
}
int main(int argc, char** argv){
    if (argc < 3){ fprintf(stderr, "usage: %s <target.zen> <lib.zen>\n", argv[0]); return 2; }
    char* tgt = slurp(argv[1]);
    char* lib = slurp(argv[2]);
    Malloc m = { 0 };
    zslice td = parse_module(&m, tgt);
    zslice ld = parse_module(&m, lib);
    return check_linked(&m, td, ld);
}
"""

# Runtime/compiler symbols made visible to checked source snippets
# (Malloc, heap, slice, putchar, …). The check binary's flat source has no module resolver, so a
# program that uses these names would otherwise count them as undefined. We prepend bodyless
# DForeign decls so the checker treats them as known imported signatures.
# (Only used by the CHECK path; the emit path tolerates them via genc's intrinsic handling.)
_PRELUDE = (
    "heap = (n: i64) RawPtr<u8>\n"
    "putchar = (c: i32) i32\n"
)

_emit_exe = None
_check_exe = None
_check_linked_exe = None
_check_kind_exe = None


def _is_import_line(line):
    s = line.strip()
    return s.startswith("{ ") and ("= std." in s or "= compiler." in s)


def _strip_imports(path):
    return "\n".join(l for l in (ROOT / path).read_text().splitlines()
                     if not _is_import_line(l))


def _build_emit():
    """The committed EMIT binary: cc bootstrap/{zenc.gen.c,zenrt.c,main.c}. NO Python."""
    global _emit_exe
    if _emit_exe is None:
        d = Path(tempfile.mkdtemp())
        exe = d / "zenc"
        r = subprocess.run(_CC + [str(BOOT / "zenc.gen.c"), str(BOOT / "zenrt.c"),
                                  str(BOOT / "main.c"), "-o", str(exe)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        _emit_exe = exe
    return _emit_exe


def _build_check():
    """The CHECK binary: have the EMIT binary compile (SOURCES + check_validate.zen) into check-mode
    C, then cc that with check_main.c. NO Python compiler — only the committed binary + cc."""
    global _check_exe
    if _check_exe is None:
        emit = _build_emit()
        d = Path(tempfile.mkdtemp())
        (d / "checksrc.zen").write_text("\n".join(_strip_imports(p) for p in _CHECK_SOURCES))
        c = subprocess.run([str(emit), str(d / "checksrc.zen")], capture_output=True, text=True).stdout
        assert c.startswith(HEAD), c[:80]
        (d / "checkc.gen.c").write_text('#include "zenrt.h"\n' + c[len(HEAD):])
        (d / "check_main.c").write_text(_CHECK_MAIN)
        exe = d / "zenc-check"
        r = subprocess.run(_CC + ["-I", str(BOOT), str(d / "checkc.gen.c"), str(BOOT / "zenrt.c"),
                                  str(d / "check_main.c"), "-o", str(exe)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        _check_exe = exe
    return _check_exe


def _build_check_kind():
    """The CHECK-KIND binary: same check-mode gen.c as _build_check (it already contains
    check_module_kind from check_validate.zen), linked with _CHECK_KIND_MAIN — a `src -> first-error
    KIND code` entry. Only the committed `zenc` binary + cc are used; NO Python compiler."""
    global _check_kind_exe
    if _check_kind_exe is None:
        emit = _build_emit()
        d = Path(tempfile.mkdtemp())
        (d / "checksrc.zen").write_text("\n".join(_strip_imports(p) for p in _CHECK_SOURCES))
        c = subprocess.run([str(emit), str(d / "checksrc.zen")], capture_output=True, text=True).stdout
        assert c.startswith(HEAD), c[:80]
        (d / "checkc.gen.c").write_text('#include "zenrt.h"\n' + c[len(HEAD):])
        (d / "check_kind_main.c").write_text(_CHECK_KIND_MAIN)
        exe = d / "zenc-check-kind"
        r = subprocess.run(_CC + ["-I", str(BOOT), str(d / "checkc.gen.c"), str(BOOT / "zenrt.c"),
                                  str(d / "check_kind_main.c"), "-o", str(exe)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        _check_kind_exe = exe
    return _check_kind_exe


def _build_check_linked():
    """The CHECK_LINKED binary: same check-mode C as _build_check (it already contains check_linked +
    module_header from check_validate.zen), but linked with _CHECK_LINKED_MAIN — a `(target, lib) ->
    cross-module error count` entry. Only the committed `zenc` binary + cc are used; NO Python."""
    global _check_linked_exe
    if _check_linked_exe is None:
        emit = _build_emit()
        d = Path(tempfile.mkdtemp())
        (d / "checksrc.zen").write_text("\n".join(_strip_imports(p) for p in _CHECK_SOURCES))
        c = subprocess.run([str(emit), str(d / "checksrc.zen")], capture_output=True, text=True).stdout
        assert c.startswith(HEAD), c[:80]
        (d / "checkc.gen.c").write_text('#include "zenrt.h"\n' + c[len(HEAD):])
        (d / "check_linked_main.c").write_text(_CHECK_LINKED_MAIN)
        exe = d / "zenc-check-linked"
        r = subprocess.run(_CC + ["-I", str(BOOT), str(d / "checkc.gen.c"), str(BOOT / "zenrt.c"),
                                  str(d / "check_linked_main.c"), "-o", str(exe)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        _check_linked_exe = exe
    return _check_linked_exe


def imports_of(path):
    """The modules `path` imports — every `{ … } = std.X` / `compiler.X` head as `namespace/name`.
    This is exactly the import classification std.internal.resolve.is_import_line makes, read here to assemble
    the lib header. Returns module ids in first-seen order, de-duplicated."""
    seen, out = set(), []
    for l in (ROOT / path).read_text().splitlines():
        s = l.strip()
        for ns in ("std", "compiler"):
            marker = "= " + ns + "."
            if s.startswith("{ ") and marker in s:
                mod = s.split(marker, 1)[1].strip().split()[0].rstrip()
                mod = "".join(ch for ch in mod if ch.isalnum() or ch in "_.")
                mid = ns + "/" + mod.replace(".", "/")
                if mod and mid not in seen:
                    seen.add(mid)
                    out.append(mid)
    return out


def _module_relpath(module_id):
    if "/" in module_id:
        ns, name = module_id.split("/", 1)
        return "zen/" + ns + "/" + name + ".zen"
    return "zen/std/" + module_id + ".zen"


# (Removed: imports_a_cross_module_generic — the marker the two cross-module oracle tests used to SKIP a
# module that calls an imported generic, e.g. std.concurrent.cown -> std.mem.own's new<T>/own_get<T>. That checker gap
# is FIXED: check_validate.call_errs now skips the strict arg-TYPE check for an imported generic call —
# its param types still carry the unbound tparam `T`, uninferable at the call site — exactly as a LOCAL
# generic call is monomorphized away before the validating pass; arity is still enforced. cown now
# namespaced-checks at 0, so both tests run it for real with no skip.)


def check_linked_count(target, libs=None):
    """Cross-module error count for std module `target` checked against the REAL signatures of the
    std modules it imports (auto-discovered via imports_of, or override with `libs`). The target's own
    import lines are stripped (the layered header — not the DImport fallback — supplies the sigs), and
    every imported module's body is concatenated (also import-stripped) into the lib parsed for its
    header. 0 == the module type-checks as an inter-module whole."""
    exe = _build_check_linked()
    if libs is None:
        libs = imports_of(target)
    d = Path(tempfile.mkdtemp())
    tgt = d / "target.zen"
    tgt.write_text("\n".join(_strip_imports(target).splitlines()))
    lib = d / "lib.zen"
    lib.write_text("\n".join("\n".join(_strip_imports(_module_relpath(m)).splitlines())
                             for m in libs if (ROOT / _module_relpath(m)).exists()))
    return subprocess.run([str(exe), str(tgt), str(lib)], capture_output=True,
                          text=True, timeout=60).returncode


def check_namespaced_count(target, modules=None):
    """FULL S1 RESOLVER cross-module error count: like check_linked_count, but the lib is built by the
    real module RESOLVER (tests/_resolver.resolve) — the transitive import closure of `target`,
    deduplicated per-NAME so each top-level name resolves to its defining module exactly once (the
    per-module namespace). Where check_linked_count flat-concats `target`'s DIRECT imports (and would
    false-positive on a genuine cross-module name clash), this resolves names through the whole graph
    with no clash. 0 == `target` type-checks against its REAL transitive imports as a namespaced unit."""
    import _resolver
    exe = _build_check_linked()
    target_id = _resolver._real_id(target)
    d = Path(tempfile.mkdtemp())
    tgt = d / "target.zen"
    tgt.write_text("\n".join(_strip_imports(_resolver.module_relpath(target_id)).splitlines()))
    lib = d / "lib.zen"
    lib.write_text(_resolver.resolve(target_id, modules))
    return subprocess.run([str(exe), str(tgt), str(lib)], capture_output=True,
                          text=True, timeout=60).returncode


def check_namespaced_count_src(target, mods):
    """FULL RESOLVER over a SYNTHETIC module map `mods` = {name: source}. The resolver computes
    `target`'s transitive, per-name-deduped (namespaced) lib from `mods`, then check_linked verifies
    `target`'s imported calls against it. Used by the clash + transitive + wrong-call proof cases:
    construct modules with a deliberate cross-module name clash / re-export chain and assert the
    resolver namespaces / resolves it (no false positive; a real wrong call still caught)."""
    import _resolver
    exe = _build_check_linked()
    d = Path(tempfile.mkdtemp())
    tgt = d / "target.zen"
    tgt.write_text("\n".join(_strip_imports_text(mods[target]).splitlines()))
    lib = d / "lib.zen"
    lib.write_text(_resolver.resolve_src(target, mods))
    return subprocess.run([str(exe), str(tgt), str(lib)], capture_output=True,
                          text=True, timeout=60).returncode


def _strip_imports_text(text):
    """_strip_imports, but over an in-memory source string (the same import-line classifier)."""
    return "\n".join(l for l in text.splitlines()
                     if not _is_import_line(l))


def check_linked_count_src(target_src, lib_src):
    """check_linked over raw SOURCE strings (no files on disk besides the temp pair). Used by the
    NEGATIVE test: a synthesized `lib_src` exports a signature, `target_src` calls it wrong, and the
    nonzero return proves the cross-module check actually verifies imported arity/arg-types."""
    exe = _build_check_linked()
    d = Path(tempfile.mkdtemp())
    (d / "t.zen").write_text(target_src)
    (d / "l.zen").write_text(lib_src)
    return subprocess.run([str(exe), str(d / "t.zen"), str(d / "l.zen")], capture_output=True,
                          text=True, timeout=60).returncode


def emit_c_for(src):
    """The C (stdout) the self-hosted EMIT binary produces for `src`, returned regardless of the
    binary's exit code — callers that need crash gating use emit_rc. Raises TimeoutExpired on a hang."""
    return subprocess.run([str(_build_emit())], input=src, capture_output=True, text=True,
                          timeout=60).stdout


def emit_rc(src):
    """The EMIT binary's process exit code for `src`: 0 on a clean emit, NEGATIVE on a signal (a
    parse/resolve/monomorphize crash). Used by the fuzz gate to assert the front-to-back EMIT pipeline
    never segfaults on malformed input. Raises TimeoutExpired on a hang (also a robustness failure)."""
    return subprocess.run([str(_build_emit())], input=src, capture_output=True, text=True,
                          timeout=30).returncode


def check_count(src):
    """The CHECK binary's error count (process exit code).
    The runtime _PRELUDE makes imported runtime symbols (heap, ...) known to the checker."""
    return subprocess.run([str(_build_check())], input=_PRELUDE + src, capture_output=True,
                          text=True, timeout=30).returncode


def verdict(src):
    """'accept' iff the CHECK binary reports zero errors, else 'reject'."""
    return "accept" if check_count(src) == 0 else "reject"


def check_kind(src):
    """The CHECK-KIND binary's first-error KIND code (process exit code): 0 == accept, 1..13 == the
    kind of the first error in check_module's traversal order (see KIND_NAME). The runtime _PRELUDE
    makes imported runtime symbols known, exactly as check_count does, so the two agree on accept."""
    return subprocess.run([str(_build_check_kind())], input=_PRELUDE + src, capture_output=True,
                          text=True, timeout=30).returncode


def verdict_kind(src):
    """The first-error KIND as a label ('arity', 'undefined-name', …); 'none' for an accepted module.
    A reject can now be asserted by REASON, not just by the binary accept/reject verdict."""
    return KIND_NAME.get(check_kind(src), "kind-%d" % check_kind(src))


def emit_value(src):
    """Compile `src` with the EMIT binary, compile+run the emitted C, return test()'s int (or None)."""
    c = emit_c_for(src)
    if not c.strip():
        return None
    body = c[len(HEAD):] if c.startswith(HEAD) else c
    d = Path(tempfile.mkdtemp())
    # the standalone runner links no zenrt.c, so provide the one runtime piece lowered code can
    # reach: `eq` (str content equality — `a == b` on strs lowers to __str_eq -> eq(a, b)).
    shim = "static bool eq(const char* a, const char* b){ for (; *a && *a == *b; a++, b++); return *a == *b; }\n"
    prog = "#include <stdint.h>\n#include <stdbool.h>\n" + shim + HEAD + "\n" + body + (_RUNNER % ())
    (d / "g.c").write_text(prog)
    if subprocess.run(_CC + [str(d / "g.c"), "-o", str(d / "g")],
                      capture_output=True, text=True).returncode != 0:
        return None
    out = subprocess.run([str(d / "g")], capture_output=True, text=True, timeout=10)
    s = out.stdout.strip()
    return int(s) if s.lstrip("-").isdigit() else None


def self_side(src):
    """Return the oracle shape used by tests: {verdict, value}."""
    v = verdict(src)
    val = emit_value(src) if ("test*" in src or "test *" in src) else None
    return {"verdict": v, "value": val}
