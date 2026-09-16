#!/usr/bin/env python3
"""Check generic literal boundaries against an independent integer range model."""
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECLARATIONS = """identity = <T>(value: T) T { value }
inferred = <T>(witness: T, value: T) T { value }
apply = <T>(value: T, body: (value: T) T) T { body(value) }
element = <T>(values: [T, 1]) T { values[0] }
nested = <T>(values: [[T, 1], 1]) T { values[0][0] }
Take = { run = <T>(self: @Self, value: T) T { value } }
"""


def expressions(ty: str, value: int) -> dict[str, str]:
    return {
        "explicit": f"identity<{ty}>({value})",
        "receiver": f"({value}).identity<{ty}>()",
        "inferred": f"inferred(witness, {value})",
        "callback": f"apply({value}, (v: {ty}) {{ v }})",
        "method": f"take.run<{ty}>({value})",
        "array_argument": f"element<{ty}>([{value}])",
        "array_receiver": f"[{value}].element<{ty}>()",
        "paren_array_receiver": f"([{value}]).element<{ty}>()",
        "nested_array_receiver": f"[[{value}]].nested<{ty}>()",
        "match_array_receiver": f"(true.match({{ true => [{value}], false => [0] }})).element<{ty}>()",
    }


def body(ty: str, expression: str) -> str:
    return f'witness: {ty} = 0; take = Take(); println("{{}}", {expression});'


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=120)


def require_success(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = run(command, cwd)
    if result.returncode:
        raise RuntimeError(f"command failed: {shlex.join(command)}\n{result.stdout}{result.stderr}")
    return result


def require_rejection(result: subprocess.CompletedProcess[str], ty: str, label: str) -> None:
    diagnostics = result.stdout + result.stderr
    if result.returncode != 1 or f"does not fit {ty}" not in diagnostics:
        raise RuntimeError(f"{label}: expected a positioned {ty} range rejection, got "
                           f"{result.returncode}\n{result.stdout}{result.stderr}")
    if f"main.zen:{DECLARATIONS.count(chr(10)) + 1}:" not in diagnostics:
        raise RuntimeError(f"{label}: range rejection lost the call's source position")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen", default=str(ROOT / "zen"))
    parser.add_argument("--std", default=str(ROOT / "src"))
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--out", type=Path, default=ROOT / "build/source_health/generic-literals")
    args = parser.parse_args()
    zen, std = str(Path(args.zen).resolve()), str(Path(args.std).resolve())
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    functions, calls, expected, results = [], [], [], []
    rejected = 0
    for signed, bits in ((True, 8), (False, 8), (True, 16), (False, 16)):
        ty = f"{'i' if signed else 'u'}{bits}"
        low = -(1 << (bits - 1)) if signed else 0
        high = (1 << (bits - int(signed))) - 1
        for value in (low - 1, low, low + 1, high - 1, high, high + 1):
            for shape, expression in expressions(ty, value).items():
                fits = low <= value <= high
                results.append({"type": ty, "value": value, "shape": shape, "fits": fits})
                if fits:
                    name = f"case_{len(functions)}"
                    functions.append(f"{name} = () {{ {body(ty, expression)} }}")
                    calls.append(f"{name}();")
                    expected.append(f"{value}\n")
                    continue
                work = out / f"{ty}-{value}-{shape}"
                work.mkdir(exist_ok=True)
                (work / "main.zen").write_text(DECLARATIONS + f"main = () {{ {body(ty, expression)} }}\n")
                generated = work / "rejected.c"
                generated.unlink(missing_ok=True)
                for command in ([zen, "check", str(work), "--std", std],
                                [zen, "build", str(work), "--std", std, "--emit-c", "-o", str(generated)]):
                    result = run(command, work)
                    (work / f"{command[1]}.diagnostics.txt").write_text(result.stdout + result.stderr)
                    require_rejection(result, ty, work.name)
                if generated.exists():
                    raise RuntimeError(f"{work.name}: rejected source published C")
                rejected += 1
    work = out / "accepted"
    work.mkdir(exist_ok=True)
    source = DECLARATIONS + "\n".join(functions) + "\nmain = () { " + " ".join(calls) + " }\n"
    (work / "main.zen").write_text(source)
    (work / "expected.txt").write_text("".join(expected))
    generated = work / "accepted.c"
    require_success([zen, "build", str(work), "--std", std, "--emit-c", "-o", str(generated)], work)
    for index, (compiler, optimization) in enumerate(((args.cc, "-O0"), (args.cc, "-O2"), ("clang", "-O2"))):
        executable = work / f"accepted-{index}"
        require_success([*shlex.split(compiler), "-std=c99", optimization, str(generated), "-lm", "-o", str(executable)], work)
        observed = require_success([str(executable)], work)
        if observed.stdout != "".join(expected):
            raise RuntimeError(f"{compiler} {optimization}: generic literals changed value")
    # A wider explicit type makes the formerly rejected source valid. The same
    # rejection oracle must detect that changed classification.
    control = out / "widened-control"
    control.mkdir(exist_ok=True)
    (control / "main.zen").write_text(DECLARATIONS + 'main = () { identity<i32>(256); }\n')
    widened = require_success([zen, "check", str(control), "--std", std], control)
    try:
        require_rejection(widened, "u8", "widened control")
    except RuntimeError:
        pass
    else:
        raise RuntimeError("widened source escaped the rejection oracle")
    report = {"compiler_sha256": hashlib.sha256(Path(zen).read_bytes()).hexdigest(),
              "cases": results, "accepted_native_runs": 3, "rejected": rejected,
              "scope": "8/16-bit signed/unsigned literal boundaries in scalar and aggregate generic call forms"}
    (out / "results.json").write_text(json.dumps(report, indent=2))
    print(f"generic literals: {len(functions)} values preserved in 3 native runs, "
          f"{rejected} inputs rejected by check and build without publication, widened control detected")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        print(f"generic literals: {exc}", file=sys.stderr)
        raise SystemExit(1)
