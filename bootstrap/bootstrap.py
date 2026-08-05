#!/usr/bin/env python3
"""bootstrap.py -- the Zen bootstrapper's command line.

    bootstrap.py <root> --emit-c -o out.c [--repeat N]
    bootstrap.py a.zen b.zen --emit-c -o out.c

`tests/determinism/README.md` calls two of these flags a contract, so they are
implemented as one:

    --emit-c -o <path>   write the generated C and stop.  It is the artifact
                         the fixpoint oracle compares, so it must be reachable
                         without invoking a C compiler.
    --repeat N           run the whole pipeline N times IN ONE PROCESS, run 1
                         to <path> and run i to <path>.<i>, then assert the
                         runs are byte-identical.  Check 1 of check.sh is the
                         only check that can see an address-derived name, and
                         without this flag it cannot be written at all.

An explicit list of `.zen` files is accepted as well as a directory, because
check 3 shuffles the input order and needs a way to specify one.  The order is
never observable: the list is sorted by its path relative to the compilation
root before anything downstream sees it.

`zen build ...` is also accepted -- check.sh invokes the compiler that way --
so a leading `build` word is skipped.

Exit codes, matching what the harness expects of them:

    0   the C was written
    1   the program has diagnostics, or --repeat found the runs differing
    2   the command could not run: bad usage, a missing input, an
        unimplemented pipeline stage.  2 is NOT a pass.
"""

import os
import sys

# ---------------------------------------------------------------------------
# import path
#
# `bootstrap/ast.py` shadows the standard library's `ast` for anything that
# runs with `bootstrap/` on sys.path -- and `dataclasses` imports `inspect`
# imports `ast`, so the shadowing breaks the interpreter's own modules rather
# than merely being untidy.  The repository root goes on the path instead and
# everything is imported as `bootstrap.*`.
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path[:] = [
    p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE
]
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bootstrap import gen_c  # noqa: E402
from bootstrap import modules as zmodules  # noqa: E402

try:
    from bootstrap import sema as zsema  # noqa: E402
except ImportError:  # pragma: no cover - sema arrives with its own agent
    zsema = None

try:
    from bootstrap import own as zown  # noqa: E402
except ImportError:  # pragma: no cover - the ownership checker is stage 3
    zown = None


USAGE = """usage: bootstrap.py <root | file.zen ...> --emit-c -o <out.c> [--repeat N]

  --emit-c        emit C and stop (the only mode; stated for the harness)
  -o <path>       where to write it; `-` is stdout
  --repeat N      run the pipeline N times in one process and compare
  --root <dir>    the compilation root, when it is not the inputs' ancestor
  -h, --help      this text
"""


class Usage(Exception):
    pass


# ---------------------------------------------------------------------------
# arguments
# ---------------------------------------------------------------------------


def parse_args(argv):
    inputs = []
    out = None
    repeat = 1
    root = None
    emit_c = False

    i = 0
    if i < len(argv) and argv[i] == "build":
        i += 1  # `zen build --emit-c -o out.c files...`
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            sys.stdout.write(USAGE)
            raise SystemExit(0)
        elif arg == "--emit-c":
            emit_c = True
        elif arg == "-o":
            i += 1
            if i >= len(argv):
                raise Usage("-o needs a path")
            out = argv[i]
        elif arg.startswith("-o") and len(arg) > 2:
            out = arg[2:]
        elif arg == "--repeat":
            i += 1
            if i >= len(argv):
                raise Usage("--repeat needs a count")
            repeat = int_or_die(argv[i])
        elif arg.startswith("--repeat="):
            repeat = int_or_die(arg.split("=", 1)[1])
        elif arg == "--root":
            i += 1
            if i >= len(argv):
                raise Usage("--root needs a directory")
            root = argv[i]
        elif arg.startswith("--root="):
            root = arg.split("=", 1)[1]
        elif arg == "--":
            inputs.extend(argv[i + 1 :])
            break
        elif arg.startswith("-"):
            raise Usage("unknown flag %s" % arg)
        else:
            inputs.append(arg)
        i += 1

    if not inputs:
        raise Usage("no input: give a directory or a list of .zen files")
    if repeat < 1:
        raise Usage("--repeat needs a count of at least 1")
    return inputs, out, repeat, root, emit_c


def int_or_die(text):
    try:
        return int(text)
    except ValueError:
        raise Usage("not a number: %s" % text)


def collect(inputs, root=None):
    """(compilation root, sorted relative paths).

    The root is the inputs' common ancestor, so two checkouts of the same tree
    at different absolute paths produce the same relative paths and therefore
    the same bytes -- which is check 4.
    """
    files = []
    dirs = []
    for item in inputs:
        path = os.path.abspath(item)
        if os.path.isdir(path):
            dirs.append(path)
        elif os.path.isfile(path):
            files.append(path)
        else:
            raise Usage("no such file or directory: %s" % item)

    if root is not None:
        base = os.path.abspath(root)
    elif dirs and not files:
        base = dirs[0] if len(dirs) == 1 else os.path.commonpath(dirs)
    else:
        bases = [os.path.dirname(p) for p in files] + dirs
        base = bases[0] if len(bases) == 1 else os.path.commonpath(bases)

    rel = sorted(
        os.path.relpath(p, base).replace(os.sep, "/") for p in files
    )  # byte order, like the harness's `LC_ALL=C sort`
    return base, tuple(rel), bool(dirs)


# ---------------------------------------------------------------------------
# the pipeline
#
# modules.py takes the parser as a parameter precisely so that it never
# reaches down into cst.py; something has to inject it, and the CLI is the
# only layer below both.  It is loaded here by path, in one place, so that
# nothing else in gen_c or modules acquires a dependency on tree-sitter node
# names.
# ---------------------------------------------------------------------------


def parser():
    """`parse(path, text) -> Module | (Module, diags)`, which is what
    `modules.build` asks for.  `path` is already relative to the compilation
    root, and it becomes every `Span.file` -- so this is also the point where
    an absolute path would leak into the emitted C, and it does not."""
    from bootstrap import cst  # noqa: F401

    source_first = getattr(cst, "parse_source", None)
    if callable(source_first):
        return lambda path, text: source_first(text, path)
    generic = getattr(cst, "parse", None)
    if callable(generic):
        return lambda path, text: generic(text, path)
    raise Usage("bootstrap/cst.py exposes no parse entry point")


def analyse(graph, root=""):
    """sema.

    `sema.analyse(graph)` hands back the `Sema` itself as well as its
    diagnostics, because gen_c reads `type_of` / `ast_type_of` off it and
    would otherwise have to redo the inference the checker just did.
    """
    if zsema is None:
        return None, ()
    fn = getattr(zsema, "analyse", None) or getattr(zsema, "analyze", None)
    if fn is not None:
        got = fn(graph, root=root) if root else fn(graph)
        if isinstance(got, tuple) and len(got) == 2:
            return got[0], tuple(got[1] or ())
        return got, tuple(getattr(got, "diags", ()) or ())
    check = getattr(zsema, "check_program", None)
    if check is not None:
        return None, tuple(check(graph, root=root) or ())
    return None, ()


def own(graph, sema, root=""):
    """The ownership checker, `PLAN.md` stage 3.

    After sema, because the receiver rule and `Drop` are both questions about
    types; before gen_c, because a data race is a compile error and never a
    runtime copy.  It runs even when sema already has something to say: a
    `must-fail` test asserts its OWN diagnostic, and suppressing it behind an
    unrelated one is how a gate stops being able to go red.
    """
    if zown is None or sema is None:
        return ()
    return tuple(zown.check(graph, sema=sema, root=root) or ())


def prune(graph, keep):
    """Keep the named modules and what they import, and nothing else.

    Discovery walks the whole root, which is right for `bootstrap.py src/` and
    wrong for one corpus program sitting in a directory of nineteen other
    programs that each declare their own `main`.  An explicit file list means
    exactly those files, plus the closure of what they import.
    """
    wanted = []
    for info in list(graph.modules.values()):
        if getattr(info, "path", None) in keep:
            wanted.append(info.dotted)
    if not wanted:
        return graph
    closure = []
    stack = sorted(wanted)
    while stack:
        dotted = stack.pop()
        if dotted in closure:
            continue
        closure.append(dotted)
        info = graph.modules.get(dotted)
        for dep in getattr(info, "deps", ()) or ():
            if dep not in closure:
                stack.append(dep)
    if getattr(graph, "prelude", None):
        prelude = graph.prelude
        if prelude in graph.modules and prelude not in closure:
            closure.append(prelude)
    keep_set = sorted(set(closure))
    graph.modules = {k: v for k, v in sorted(graph.modules.items()) if k in keep_set}
    graph.order = tuple(d for d in graph.order if d in graph.modules)
    return graph


def compile_once(root, files, whole_tree):
    """One full run: parse, resolve, check, emit.  Holds no state afterwards.

    A program that failed to resolve does not reach codegen.  gen_c lowers a
    program sema has agreed is a program; handing it one with unresolved names
    turns a diagnostic into a second, worse diagnostic -- and a `must-fail`
    test wants the FIRST error, at its own position, not gen_c's opinion of
    the wreckage.
    """
    graph = zmodules.build(root, parse=parser())
    if not whole_tree and files:
        graph = prune(graph, set(files))
    sema, sema_diags = analyse(graph, root)
    diags = list(getattr(graph, "diags", ()) or ()) + list(sema_diags)
    diags += list(own(graph, sema, root))
    if diags:
        return "", diags
    text, gen_diags = gen_c.generate(graph, sema=sema, root=root)
    return text, list(gen_diags)


def render(diag):
    span = getattr(diag, "span", None)
    where = str(span) if span is not None else "<unknown>"
    out = ["%s: %s" % (where, getattr(diag, "message", diag))]
    for note in getattr(diag, "notes", ()) or ():
        if isinstance(note, tuple) and len(note) == 2:
            out.append("  note: %s: %s" % (note[0], note[1]))
        else:
            out.append("  note: %s" % (note,))
    return "\n".join(out)


def write(path, text):
    if path is None or path == "-":
        sys.stdout.write(text)
        return
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def main(argv):
    try:
        inputs, out, repeat, root_arg, _emit_c = parse_args(argv)
        root, files, whole_tree = collect(inputs, root_arg)
    except Usage as exc:
        sys.stderr.write("%s\n" % exc)
        return 2

    try:
        runs = [compile_once(root, files, whole_tree) for _ in range(repeat)]
    except Usage as exc:
        sys.stderr.write("bootstrap: %s\n" % exc)
        return 2
    except ImportError as exc:
        sys.stderr.write("bootstrap: a pipeline stage is missing: %s\n" % exc)
        return 2

    for i, (text, _diags) in enumerate(runs, start=1):
        write(out if i == 1 else "%s.%d" % (out, i), text)

    status = 0
    first = runs[0][0]
    for i, (text, _diags) in enumerate(runs[1:], start=2):
        if text != first:
            at = next(
                (n for n, (a, b) in enumerate(zip(first, text)) if a != b), len(first)
            )
            sys.stderr.write(
                "bootstrap: --repeat run %d differs from run 1 at byte %d\n"
                "bootstrap: gen_c is nondeterministic; see "
                "tests/determinism/README.md\n" % (i, at)
            )
            status = 1

    diags = runs[0][1]
    if diags:
        for diag in diags:
            sys.stderr.write("%s\n" % render(diag))
        sys.stderr.write("bootstrap: %d diagnostic(s)\n" % len(diags))
        status = status or 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
