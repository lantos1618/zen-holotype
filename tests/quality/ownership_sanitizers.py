#!/usr/bin/env python3
"""Exercise generated ownership code with ASan and a failing lifetime control."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CASES = (
    "helpers_preserve_caller_owned_storage",
    "transferred_arena_view_stored_through_parameter",
)


def run(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=120,
                          env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0"})


def require(args):
    result = run(args)
    if result.returncode:
        raise RuntimeError(f"{shlex.join(args)}\n{result.stdout}{result.stderr}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen", type=Path, default=ROOT / "zen")
    parser.add_argument("--cc", default="cc")
    args = parser.parse_args()
    work = ROOT / "build/source_health/ownership-sanitizers"
    work.mkdir(parents=True, exist_ok=True)
    compiler = [*shlex.split(args.cc), "-std=c99", "-O1", "-g",
                "-fsanitize=address", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]
    control = work / "control.c"
    control.write_text("#include <stdlib.h>\n"
                       "int main(void) { volatile char *p = malloc(1); "
                       "if (!p) return 2; *p = 7; free((void *)p); return *p; }\n")
    require([*compiler, str(control), "-o", str(work / "control")])
    result = run([str(work / "control")])
    (work / "control.log").write_text(result.stdout + result.stderr)
    if result.returncode == 0 or "heap-use-after-free" not in result.stderr:
        raise RuntimeError("ASan did not detect the deliberate lifetime violation")
    for name in CASES:
        source = ROOT / "tests/corpus/own" / f"{name}.zen"
        generated = work / f"{name}.c"
        require([str(args.zen.resolve()), "build", str(source.parent),
                 "--entry", source.name, "--std", str(ROOT / "src"),
                 "--emit-c", "-o", str(generated)])
        binary = work / name
        require([*compiler, str(generated), "-lm", "-o", str(binary)])
        result = require([str(binary)])
        (work / f"{name}.log").write_text(result.stdout + result.stderr)
        if result.stdout != source.with_suffix(".expected").read_text():
            raise RuntimeError(f"{name}: generated ownership behavior changed")
    print(f"ownership-sanitizers: {len(CASES)} generated programs passed; UAF control detected")


if __name__ == "__main__":
    main()
