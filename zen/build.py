"""The build system — `build.zen` is a real Zen program, run through the comptime
engine with `b` a live host Builder. b.add / b.use / b.config execute as the script
does, so conditionals, helpers and computed values are honoured (nothing is scraped
out of the AST). The accumulated graph becomes the config dict the driver consumes.
Also the foreign-binding loader, the test predicate, and the incremental cc cache.
"""
from __future__ import annotations
import pathlib, subprocess
from .ast import Fn, Prim, PrimT, Let, Assign, Var
from .parser import parse
from .comptime import evaluate, Host
from .resolve import build_namespace, build_scopes

_BINDINGS_DIR = pathlib.Path(__file__).parent / "bindings"


def load_uses(cfg, files):
    """Install each build `use` as an importable namespace —
    `c = b.use("libc")` makes `{ malloc, free } = c` work.

    A foreign binding is a Zen module of decls (the libc bindings are bodyless
    functions in bindings/libc.zen — content lives in Zen, never in this kernel).
    `b.use(name)` loads that bundled module under the chosen namespace; the kernel
    knows only how to load-a-module-as-a-namespace, nothing C-specific. A real
    *generating* adapter (translate-c / wasm / python → [Decl]) is a future Zen
    comptime function run through the same `b.use` seam — built when one exists."""
    for u in cfg.get("uses", []):
        path = _BINDINGS_DIR / f"{u['module']}.zen"
        if not path.exists():
            raise SystemExit(f"build.zen: no binding module '{u['module']}' "
                             f"(looked in {_BINDINGS_DIR})")
        files[u["ns"]] = parse(path.read_text(), u["ns"])
    return files


class _UseToken:
    """The value of `b.use(mod)`. The name it's assigned to becomes the namespace
    the module installs under — `c = b.use("libc")` → namespace `c`, so a program
    then does `{ malloc, free } = c`."""
    def __init__(self, module):
        self.module = module


class _Builder(Host):
    """The build `Builder`. `b.add(Executable/Test)` registers a graph node,
    `b.use(mod)` a foreign-binding module, `b.config()` finalizes to a Result."""
    def __init__(self):
        self.execs, self.tests = [], []

    def invoke(self, method, args):
        if method == "add":
            comp = args[0] if args else None
            ty = getattr(comp, "type_name", None)
            if ty == "Executable":
                self.execs.append(comp)
            elif ty == "Test":
                self.tests.append(comp)
            else:
                raise SystemExit(f"build.zen: b.add expects an Executable or Test, got {ty!r}")
            return self                                    # chainable: b.add(...).add(...)
        if method == "use":
            if not (args and isinstance(args[0], str)):
                raise SystemExit("build.zen: b.use(<module>) needs a string module name")
            return _UseToken(args[0])
        if method == "config":
            return ("@enum", "Ok", None)                   # Result<BuildConfig, BuildError>.Ok
        raise SystemExit(f"build.zen: a Builder has no method '{method}'")


def _build_cfg(b, uses):
    """Read the executed Builder's accumulated graph into the config dict the rest
    of the build pipeline consumes."""
    cfg = {"name": "a.out", "main": "main.zen", "out_dir": ".", "tests": [], "uses": uses,
           "cflags": [], "links": [], "target": "native"}
    if b.execs:
        e = b.execs[0]                                     # one executable per build, today
        cfg["name"] = e.get("name", cfg["name"])
        cfg["main"] = e.get("main", cfg["main"])
        cfg["out_dir"] = e.get("out_dir", cfg["out_dir"])
        cfg["cflags"] = e.get("cflags", []) or []          # ["-O2", "-g"]
        cfg["links"] = e.get("links", []) or []            # ["m"] -> -lm
        cfg["target"] = e.get("target", "native")
    cfg["tests"] = [r for t in b.tests if (r := t.get("root"))]
    return cfg


def interpret_build(bf):
    """Run build() for real and return its config dict. `b` is a host Builder threaded
    through the comptime evaluator; the graph it accumulates *is* the executed result."""
    files = {"build": bf}
    namespace = build_namespace(files)
    build_scopes(files)
    for d in bf.decls:
        if isinstance(d, Fn):
            d.scope = bf.scope                             # comptime _call reads fn.scope
    fn = next((d for d in bf.decls if isinstance(d, Fn) and d.name == "build"), None)
    if fn is None:
        raise SystemExit("build.zen: no build() function")

    b = _Builder()
    env = {fn.params[0].name: b} if fn.params else {}      # bind the `b: Builder` parameter
    uses, final = [], None
    for stmt in fn.body:
        if isinstance(stmt, Let):
            env[stmt.name] = v = evaluate(stmt.value, namespace, fn.scope, env)
            if isinstance(v, _UseToken):                   # c := b.use(...)
                uses.append({"module": v.module, "ns": stmt.name})
        elif isinstance(stmt, Assign) and isinstance(stmt.target, Var):
            env[stmt.target.name] = v = evaluate(stmt.value, namespace, fn.scope, env)
            if isinstance(v, _UseToken):                   # c = b.use(...)
                uses.append({"module": v.module, "ns": stmt.target.name})
        else:
            final = evaluate(stmt, namespace, fn.scope, env)
    if isinstance(final, tuple) and len(final) == 3 and final[:2] == ("@enum", "Err"):
        raise SystemExit(f"build.zen: build() returned an error: {final[2]!r}")
    return _build_cfg(b, uses)


def is_test_fn(d) -> bool:
    """A test is a no-arg function returning bool — true means the test passed."""
    return (isinstance(d, Fn) and not d.params
            and isinstance(d.ret, PrimT) and d.ret.prim is Prim.BOOL)


def compile_if_changed(cpath, bpath, c_text, cc_extra=()):
    """Write `c_text` and compile it to `bpath` with cc, but skip the compile when
    the source we'd write is byte-identical to last time and the binary still
    exists. Sound because codegen is deterministic — same program → same C → same
    binary. A header comment records the exact cc command, so changing cflags or
    links changes the file and busts the cache too. Returns True if it compiled."""
    cc = ["cc", "-Wall", "-Wextra", *cc_extra]
    stamped = f"// built with: {' '.join(cc)} {cpath.name} -o {bpath.name}\n{c_text}"
    if bpath.exists() and cpath.exists() and cpath.read_text() == stamped:
        return False
    cpath.write_text(stamped)
    subprocess.run([*cc, str(cpath), "-o", str(bpath)], check=True)
    return True


# Build targets. Only "native" (compile C with cc) is implemented; the dict is the
# extension point — a wasm backend slots in here as `"wasm": <emitter>` once it exists.
_TARGETS = {"native"}
