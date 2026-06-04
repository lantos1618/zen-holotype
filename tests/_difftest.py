"""Differential tester: run a Zen program through BOTH frontends and compare.

  • the PYTHON reference frontend (zen.main) — the source of truth
  • the SELF-HOSTED toolchain (std.{lex,parse,check,genc} run as a program, via _selfhost)

A divergence is a candidate bug:
  • accept/reject disagreement  (one frontend accepts, the other rejects)
  • value disagreement          (both accept + run, but `test()` computes different ints)

A program is a Zen module string. To compare COMPUTED values, give it an entry
`test* = () i32 { … }` returning an i32 (the harness reads its value from both sides).
Programs with no `test` are still compared on accept/reject.

Usage:
    from _difftest import compare
    d = compare("test* = () i32 { 40 + 2 }")
    # d = {"py": {...}, "self": {...}, "verdict_div": bool, "value_div": bool, "summary": "..."}
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))         # tests/  (for _selfhost)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root (for zen.*)
from _selfhost import emit_c_for, HEAD                       # self-hosted emit (raises on toolchain error)

from zen.main import (load, build_namespace, build_scopes, resolve,
                      fold_comptime, run_emits, check, emit_c)

_CC = ["cc", "-std=gnu11", "-w"]
_RUNNER = "\n#include <stdio.h>\nint main(void){ printf(\"%%lld\", (long long)(%s())); return 0; }\n"   # cast: exact for i32 AND i64 returns


def _cc_run(tmp, cfile, exe):
    r = subprocess.run(_CC + [str(cfile), "-o", str(exe)], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return ("compile_error", r.stderr[:300])
    try:
        out = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return ("timeout", None)
    if out.returncode != 0 and not out.stdout.strip():
        return ("run_error", f"exit {out.returncode}")
    return ("value", out.stdout.strip())


def py_side(src):
    """The Python reference: {verdict: accept|reject|error, value: int|None, note: str}."""
    d = Path(tempfile.mkdtemp()); (d / "m.zen").write_text(src)
    try:
        files = load(d); ns = build_namespace(files); build_scopes(files); resolve(files, ns)
        fold_comptime(files, ns); run_emits(files, ns)
        failing, passing = check(files, ns)
    except Exception as e:
        return {"verdict": "error", "value": None, "note": f"{type(e).__name__}: {e}"[:200]}
    errs = [x for x in failing if not x[1]]
    if errs:
        return {"verdict": "reject", "value": None, "note": str(errs[0][2])[:160]}
    if "m.test" not in {f"{f.ns}.{getattr(x,'name','')}" for f in files.values() for x in f.decls}:
        return {"verdict": "accept", "value": None, "note": "no test()"}
    try:
        c = emit_c(files, passing, ns, roots={"m.test"})
        (d / "o.c").write_text(c + (_RUNNER % "m_test"))
        kind, payload = _cc_run(d, d / "o.c", d / "o")
    except Exception as e:
        return {"verdict": "accept", "value": None, "note": f"emit: {type(e).__name__}: {e}"[:160]}
    return {"verdict": "accept", "value": (int(payload) if kind == "value" and payload.lstrip("-").isdigit() else None),
            "note": payload if kind != "value" else ""}


def self_side(src):
    """The self-hosted toolchain: {verdict: accept|reject|error, value: int|None, note: str}."""
    from _selfhost import check_errors
    d = Path(tempfile.mkdtemp())
    try:
        n = check_errors(d, src)
    except Exception as e:
        return {"verdict": "error", "value": None, "note": f"check: {type(e).__name__}: {e}"[:200]}
    verdict = "accept" if n == 0 else "reject"
    if "test*" not in src and "test *" not in src:
        return {"verdict": verdict, "value": None, "note": "no test()"}
    try:
        c = emit_c_for(d, src)
    except Exception as e:
        return {"verdict": verdict, "value": None, "note": f"emit: {type(e).__name__}: {e}"[:160]}
    body = c[len(HEAD):] if c.startswith(HEAD) else c
    prog = "#include <stdint.h>\n#include <stdbool.h>\n" + HEAD + "\n" + body + (_RUNNER % "test")
    (d / "g.c").write_text(prog)
    kind, payload = _cc_run(d, d / "g.c", d / "g")
    return {"verdict": verdict, "value": (int(payload) if kind == "value" and payload.lstrip("-").isdigit() else None),
            "note": payload if kind != "value" else ""}


def compare(src):
    py, sf = py_side(src), self_side(src)
    verdict_div = py["verdict"] != sf["verdict"] and "error" not in (py["verdict"], sf["verdict"])
    value_div = (py["value"] is not None and sf["value"] is not None and py["value"] != sf["value"])
    summary = (f"py={py['verdict']}({py['value']}) self={sf['verdict']}({sf['value']})"
               + (" ⚠VERDICT-DIVERGE" if verdict_div else "")
               + (" ⚠VALUE-DIVERGE" if value_div else ""))
    return {"py": py, "self": sf, "verdict_div": verdict_div, "value_div": value_div, "summary": summary}


if __name__ == "__main__":
    # smoke: a handful of programs; print divergences
    for s in ["test* = () i32 { 40 + 2 }",
              "test* = () i32 { 1 + 2 * 3 }",
              "test* = () i32 { (3 < 5).match({ true => 7, false => 0 }) }",
              "P*: { x: i32, y: i32 }\ntest* = () i32 { P{ x: 19, y: 23 }.x + P{ x: 19, y: 23 }.y }"]:
        print(compare(s)["summary"], "::", s[:50])
