"""Regression: std.text.num parsing (parse_f64 / parse_i64_checked / parse_i64_radix).

Runs a real program through the shipping `zenc run` (imports resolved from <root>/zen/std), and
asserts BOTH the value path (parsed numbers are correct) and the error-as-value path (garbage /
empty / out-of-range input becomes `.Err`, never a silent 0). This guards the honest-parse contract
that `parse_int`'s never-errors behaviour deliberately does NOT provide.
"""
import subprocess
import tempfile
from pathlib import Path

import _oracle

ROOT = _oracle.ROOT


def _zenc():
    subprocess.run(["make", "-f", "bootstrap/Makefile", "zenc"], cwd=str(ROOT),
                   check=True, capture_output=True)
    return str(ROOT / "zenc")


PROG = r"""
{ put } = std.text.fmt
{ parse_f64, parse_i64_checked, parse_i64_radix } = std.text.num
{ ParseError } = std.text.str

emit_f = (label: str, r: Result<f64, ParseError>) void {
    r.match ({
        .Ok(v)  => { put(label).s("=Ok").f(v).nl()  {} },
        .Err(e) => { put(label).s("=Err").nl()  {} }
    })
}

emit_i = (label: str, r: Result<i64, ParseError>) void {
    r.match ({
        .Ok(v)  => { put(label).s("=Ok").i(v).nl()  {} },
        .Err(e) => { put(label).s("=Err").nl()  {} }
    })
}

main = () i32 {
    emit_f("f_pi|",   parse_f64("3.14"))
    emit_f("f_neg|",  parse_f64("-2.5"))
    emit_f("f_exp|",  parse_f64("1e3"))
    emit_f("f_int|",  parse_f64("42"))
    emit_f("f_bad|",  parse_f64("abc"))
    emit_f("f_mt|",   parse_f64(""))
    emit_f("f_dot2|", parse_f64("1.2.3"))

    emit_i("i_ok|",   parse_i64_checked("123"))
    emit_i("i_bad|",  parse_i64_checked("12x"))
    emit_i("i_mt|",   parse_i64_checked(""))

    emit_i("r_hex|",  parse_i64_radix("ff", 16))
    emit_i("r_bin|",  parse_i64_radix("1010", 2))
    emit_i("r_bad|",  parse_i64_radix("zz", 16))
    0
}
"""


def test_num_parse_values_and_error_path():
    zenc = _zenc()
    d = Path(tempfile.mkdtemp())
    (d / "p.zen").write_text(PROG)
    r = subprocess.run([zenc, "run", str(d / "p.zen")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = r.stdout

    # value path: numbers parse correctly
    assert "f_pi|=Ok3.14\n" in out, out
    assert "f_neg|=Ok-2.5\n" in out, out
    assert "f_exp|=Ok1000.0\n" in out, out
    assert "f_int|=Ok42.0\n" in out, out
    assert "i_ok|=Ok123\n" in out, out
    assert "r_hex|=Ok255\n" in out, out
    assert "r_bin|=Ok10\n" in out, out

    # error-as-value path: garbage / empty / bad-digit is .Err, NOT a silent 0
    assert "f_bad|=Err\n" in out, out
    assert "f_mt|=Err\n" in out, out
    assert "f_dot2|=Err\n" in out, out
    assert "i_bad|=Err\n" in out, out
    assert "i_mt|=Err\n" in out, out
    assert "r_bad|=Err\n" in out, out
