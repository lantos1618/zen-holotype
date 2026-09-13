#!/usr/bin/env python3
"""Replayable expression tests against an independent bounded integer model."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Expr:
    kind: str
    children: tuple[Expr, ...] = ()
    value: int = 0

    def source(self) -> str:
        parts = [child.source() for child in self.children]
        if self.kind == "value":
            return str(self.value)
        if self.kind in ("a", "b"):
            return self.kind
        if self.kind == "tick":
            return f"counter.tick({parts[0]})"
        if self.kind == "identity":
            return f"identity({parts[0]})"
        if self.kind == "choose":
            return f"({parts[0]} < {parts[1]}).match({{ true => {parts[2]}, false => {parts[3]} }})"
        return f"({parts[0]} {self.kind} {parts[1]})"

    def evaluate(self, a: int, b: int, state: list[int]) -> int:
        if self.kind == "value":
            return self.value
        if self.kind in ("a", "b"):
            return a if self.kind == "a" else b
        left = self.children[0].evaluate(a, b, state)
        if self.kind == "tick":
            state[0] += 1
            return left + state[0]
        if self.kind == "identity":
            return left
        right = self.children[1].evaluate(a, b, state)
        if self.kind == "choose":
            return self.children[2 if left < right else 3].evaluate(a, b, state)
        if self.kind == "+":
            return left + right
        if self.kind == "-":
            return left - right
        if self.kind == "*":
            return left * right
        raise ValueError(self.kind)


def expression(rng: random.Random, depth: int) -> Expr:
    if depth == 0:
        kind = rng.choice(("a", "b", "value"))
        return Expr(kind, value=rng.randint(-20, 20))
    kind = rng.choice(("+", "-", "*", "tick", "identity", "choose"))
    left = expression(rng, depth - 1)
    if kind in ("tick", "identity"):
        return Expr(kind, (left,))
    if kind == "*":
        return Expr(kind, (left, Expr("value", value=rng.randint(0, 4))))
    if kind == "choose":
        return Expr(kind, (left, *(expression(rng, depth - 1) for _ in range(3))))
    return Expr(kind, (left, expression(rng, depth - 1)))


def program(seed: int, count: int) -> tuple[str, str]:
    rng = random.Random(seed)
    declarations = ["identity = <T>(value: T) T { value }", """Counter = {
    count :: i32,
    tick = (self :: @Self, value: i32) i32 {
        self.count = self.count + 1;
        value + self.count
    }
}"""]
    main = ["main = () () {"]
    expected = []
    # The first case always distinguishes left-to-right effects. The second
    # always distinguishes lazy arms, regardless of the random distribution.
    controls = [Expr("-", (Expr("tick", (Expr("a"),)), Expr("tick", (Expr("b"),)))),
                Expr("choose", (Expr("value", value=0), Expr("value", value=1),
                                Expr("tick", (Expr("a"),)), Expr("tick", (Expr("tick", (Expr("b"),)),))))]
    for index in range(count):
        node = controls[index] if index < len(controls) else expression(rng, rng.randint(2, 4))
        a, b = rng.randint(-30, 30), rng.randint(-30, 30)
        state = [0]
        value = node.evaluate(a, b, state)
        if not -(2**31) <= value < 2**31:
            raise RuntimeError("generator exceeded the bounded i32 model")
        declarations.append(f"case_{index} = (counter :: Counter, a: i32, b: i32) i32 {{ {node.source()} }}")
        main.extend((f"counter_{index} ::= Counter(count: 0);",
                     f"value_{index} = case_{index}(counter_{index}, {a}, {b});",
                     f'println("{{}} {{}}", value_{index}, counter_{index}.count);'))
        expected.append(f"{value} {state[0]}\n")
    return "\n".join(declarations + main + ["}"]), "".join(expected)


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {shlex.join(command)}\n{result.stdout}{result.stderr}")
    return result


def assert_output(actual: str, expected: str, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label}: output disagrees with independent model\nexpected: {expected!r}\nactual: {actual!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen", default=str(ROOT / "zen"))
    parser.add_argument("--std", default=str(ROOT / "src"))
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--seeds", nargs="+", type=int, default=[1729, 8675309, 314159])
    parser.add_argument("--cases", type=int, default=32)
    parser.add_argument("--out", type=Path, default=ROOT / "build/source_health/randomized")
    args = parser.parse_args()
    if args.cases < 2 or len(set(args.seeds)) != len(args.seeds):
        parser.error("at least two cases and distinct seeds are required")
    zen = str(Path(args.zen).resolve())
    std = str(Path(args.std).resolve())
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for seed in args.seeds:
        work = out / f"seed-{seed}"
        work.mkdir(exist_ok=True)
        source, expected = program(seed, args.cases)
        path = work / "main.zen"
        path.write_text(source)
        (work / "original.zen.txt").write_text(source)
        (work / "expected.txt").write_text(expected)
        for form in ("original", "formatted"):
            if form == "formatted":
                run([zen, "fmt", str(path)], work)
                run([zen, "fmt", "--check", str(path)], work)
            generated = work / f"{form}.c"
            run([zen, "build", str(work), "--entry", "main.zen", "--std", std,
                 "--emit-c", "-o", str(generated)], work)
            for compiler, optimization in ((args.cc, "-O0"), (args.cc, "-O2"), ("clang", "-O2")):
                executable = work / f"{form}-{len(results)}"
                run([*shlex.split(compiler), "-std=c99", optimization, str(generated), "-lm", "-o", str(executable)], work)
                observed = run([str(executable)], work)
                assert_output(observed.stdout, expected, f"seed {seed} {form} {compiler} {optimization}")
                results.append({"seed": seed, "form": form, "cc": compiler, "optimization": optimization,
                                "cases": args.cases, "stdout_sha256": hashlib.sha256(observed.stdout.encode()).hexdigest()})
    # A valid source mutation changes observable receiver effects. It must
    # compile and run, then be refused by the same independent output oracle.
    control = out / "effect-control"
    control.mkdir(exist_ok=True)
    source, expected = program(args.seeds[0], args.cases)
    mutated = source.replace("self.count = self.count + 1;", "self.count = self.count + 2;")
    if source == mutated:
        raise RuntimeError("effect mutation did not change the generated source")
    (control / "main.zen").write_text(mutated)
    generated = control / "control.c"
    executable = control / "control"
    run([zen, "build", str(control), "--std", std, "--emit-c", "-o", str(generated)], control)
    run([*shlex.split(args.cc), "-std=c99", "-O2", str(generated), "-lm", "-o", str(executable)], control)
    observed = run([str(executable)], control)
    (control / "observed.txt").write_text(observed.stdout)
    try:
        assert_output(observed.stdout, expected, "changed receiver effect")
    except RuntimeError:
        pass
    else:
        raise RuntimeError("effect mutation escaped the independent output oracle")
    report = {"compiler_sha256": hashlib.sha256(Path(zen).read_bytes()).hexdigest(), "runs": results,
              "scope": "bounded i32 expressions, generic identity, lazy match, receiver effects; not a full-language oracle"}
    (out / "results.json").write_text(json.dumps(report, indent=2))
    print(f"randomized: {len(args.seeds) * args.cases} modeled cases, {len(results)} native runs, original/format fixedpoint, effect mutation refused")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        print(f"randomized: {exc}", file=sys.stderr)
        raise SystemExit(1)
