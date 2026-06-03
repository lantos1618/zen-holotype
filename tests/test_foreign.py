"""Foreign declarations — `name = (params) RetType` with NO body, a binding to a function
defined elsewhere (libc, another TU). The self-hosted parser must emit each as a C *prototype*
(not grab the following decl's brace), and the checker must know its full signature.

The bug this guards against: two consecutive bodyless decls used to mis-parse — `skip_to_brace`
walked past the first decl's (absent) body into the SECOND decl's `{`, fusing them into one
malformed function and silently dropping everything after.
"""
from _selfhost import emit_c_for, check_errors, run_value


def test_single_foreign_emits_prototype(tmp_path):
    c = emit_c_for(tmp_path, "sq = (n: i32) i32\ntest* = () i32 { 7 }")
    assert "int32_t sq(int32_t n);" in c           # a prototype, no body
    assert "int32_t test(" in c                    # the real fn survives intact
    assert "{ return 7" in c


def test_consecutive_foreign_decls(tmp_path):
    # the original bug: two bodyless decls in a row, then a real function.
    src = ("malloc = (n: i64) i64\n"
           "calloc = (n: i64, sz: i64) i64\n"
           "test* = () i32 { 42 }")
    c = emit_c_for(tmp_path, src)
    assert "int64_t malloc(int64_t n);" in c
    assert "int64_t calloc(int64_t n, int64_t sz);" in c
    assert "{ return 42" in c                       # test() not swallowed into a foreign body


def test_foreign_call_typechecks(tmp_path):
    # the checker knows the foreign signature: a wrong-arity call is rejected, a right one is not.
    ok  = check_errors(tmp_path, "sq = (n: i32) i32\nt* = () i32 { sq(3) }")
    bad = check_errors(tmp_path, "sq = (n: i32) i32\nt* = () i32 { sq(3, 4) }")
    assert ok == 0
    assert bad > 0


def test_foreign_defined_elsewhere_runs(tmp_path):
    # a foreign decl whose definition is supplied by a following real function with the same name's
    # body — here we just prove the prototype + a hand-written caller compile and run together.
    src = ("dbl = (n: i32) i32\n"
           "test* = () i32 { dbl(20) + 2 }")
    c = emit_c_for(tmp_path, src)
    assert "int32_t dbl(int32_t n);" in c
    # supply the missing definition and run.
    prog = ("#include <stdint.h>\n#include <stdbool.h>\n"
            "typedef struct { void* ptr; int64_t len; } zslice; \n"
            + c[len("typedef struct { void* ptr; int64_t len; } zslice; "):]
            + "\nint32_t dbl(int32_t n){ return n * 2; }\n"
            + "int main(void){ return test() == 42 ? 0 : 1; }\n")
    p = tmp_path / "f.c"; p.write_text(prog)
    import subprocess
    assert subprocess.run(["cc", "-std=gnu11", "-w", str(p), "-o", str(tmp_path / "f")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "f")]).returncode == 0
