# zen

**zen** is a small, **self-hosted** compiler for a [Zen](https://github.com/lantos1618/zenlang)-flavoured
language. The compiler is written in Zen, compiles itself, and has **two backends** over one
shared AST: **C** (`genc`, the default and the intentional bootstrap target — not a
host-language fallback) and **JavaScript** (`js`, run under `node`). There is **no Python
and no tree-sitter** in the build path: `cc` builds the `zenc` binary from committed C — a
161-line hand-written runtime floor (`bootstrap/zenrt.c`) is the only C not emitted by the
compiler — and `zenc` re-emits that C byte-for-byte (a deterministic **fixpoint**).

It is a real-but-rough compiler: the core (self-hosting, FFI, generics, traits, a memory
model, a multicore actor runtime) is well ahead of the user-facing surface and stdlib
breadth. Treat it as a working language you can read and hack on, not a finished product.

The guiding idea: **pin down what every value _is_ with type structure, and you lock out
everything it isn't.** A type is a closed door; "checking" is confirming the key fits the
lock. The compiler applies this to names, functions, generics, numeric fits, and — now —
pointer direction and nullability.

## A taste

```zen
// hello.zen — imports, output, an exit code.
{ println } = std.text.fmt

main = () i32 {
    println("hello, zen")
    println(6 * 7)
    0
}
```

```sh
$ zenc run examples/hello.zen
hello, zen
42
```

The **same program** emits JavaScript and runs under `node` — the two backends share the
checked AST, so a program that type-checks lowers to either target:

```sh
$ zenc emit-js examples/hello.zen | node
hello, zen
42
```

A little more of the working surface — enums with payloads, traits dispatched by receiver
(UFCS), `.match`-only control flow, generics, and `Result` with early return:

```zen
{ println } = std.text.fmt
{ Result, IoError } = std.core.result

Shape*: Circle(i32) | Rect(RectDims) | Unit
RectDims*: { w: i32, h: i32 }

Area*: { area: (Ptr<Self>) i32 }          // a trait is a record of signatures
Circle*: { r: i32 }
Circle.impl(Area, {                       // an impl is `Type.impl(Trait, { ... })`
    area = (c: Ptr<Circle>) i32 { 3 * c.r * c.r }
})

shape_area = (s: Shape) i32 {
    s.match ({                            // a value-position match IS the conditional
        .Circle(r) => 3 * r * r,
        .Rect(d)   => d.w * d.h,
        .Unit      => 0,
    })
}

checked_div = (n: i32, d: i32) Result<i32, IoError> {
    (d == 0).match ({ true => .Err(.NotFound), false => .Ok(n / d) })
}
half_of = (n: i32) Result<i32, IoError> {
    q := checked_div(n, 2).or_return()    // unwrap .Ok, or propagate the .Err by value
    .Ok(q + 1)
}
```

See **[`examples/`](examples/)** (`hello`, `tour`, `shapes`, `stats`, `str_ops_demo`,
`json_demo`, `store_demo`, `actor_demo`, `pool_actor_demo`, and the stdin filters `stdin_echo` / `wordfreq`) —
every one runs with `zenc run examples/<name>.zen`.

## The language

- **`.match`-only control flow.** No `if`/`while`/`for` and no exceptions or stack
  unwinding. A `.match` on an enum/bool is the conditional; recursion + the `loop` construct
  cover iteration. With literal patterns on `i32`/`bool` and recursion the language is
  Turing-complete (`fact`/`fib` compile and run).
- **Errors are values.** A fallible call returns `Result<T, E>` (`.Ok`/`.Err`); an optional
  is `Opt<T>` (`.Some`/`.None`). `.match` *is* the catch; `.or_return()` / `return .Err(e)`
  propagate by value. `panic` is the explicit, greppable abort — never the default path.
- **Distinct pointer types, checker-enforced.** `Ptr<T>` (read-only, non-null),
  `MutPtr<T>` (writable, non-null), and `RawPtr<T>` (the nullable raw floor). Writing
  through a `Ptr<T>` is a `ptr-write` error; dereferencing a nullable `RawPtr<T>` that
  hasn't been proven non-null is a `null-deref` error (prove it with `assert_nonnull`, which
  yields a `MutPtr<T>`); omitting a non-null pointer field from a struct literal is rejected.
- **Generics, traits, enums, structs.** Generic data types (`Box<T>`) and functions
  (`id<T>`) are monomorphized to concrete C; type args are inferred by unification. Traits
  are keyword-free records of signatures with `Type.impl(Trait, { ... })`; a `<T: Trait>`
  bound dispatches to the concrete impl and an unsatisfied bound is a type error. User enums
  are `|`-separated variants with optional payloads, lowered to C tagged unions.
- **Other surface.** Return-type inference (omit the type, inferred from the body across
  calls); UFCS method chains (`x.f(a)`); `*` marks a declaration public; `x := v`
  let-bindings; slices `[T]`; arithmetic/comparison/logical operators, plus bitwise
  `& | ^ << >>`. In a type declaration (`Colour: Red | Green`), `|` separates enum variants;
  in a value expression (`read | create`), the same glyph is bitwise OR.
- **Literals.** Decimal, hex `0x`, binary `0b`, octal `0o`, digit separators
  `1_000_000`, and floats with e-notation `6.022e23`.
- **Capabilities at the entry point.** `main` can take the root capability explicitly —
  `main = (sys: Sys) i32` — and hand out *narrow* capabilities from it: `sys.stdout()` /
  `sys.stderr()` yield a `Writer`, `sys.heap()` an `Allocator`, plus `env`/`clock`/`fs`. A
  library takes the narrowest capability it needs (a `Writer`, not the world). The niladic
  `main = () i32` still works — the compiler feeds it `std.sys.root()` through a trampoline,
  so the C boundary is unchanged. There is no ambient global runtime.
- **Memory is explicit and allocator-threaded.** Heap-backed `String`/`Vec` take an
  allocator from program setup (`m := halloc.gpa()`); there is no hidden heap. The checker
  rejects use-after-`release`/`drop` for `Own`/`Rc`/`Arc`. See **[MEMORY_MODEL.md](docs/MEMORY_MODEL.md)**.
- **Metaprogramming as values.** Build an AST with `std.internal.ast` and emit it with
  `compiler.genc.genModule` — no `@emit` pragma.

## The standard library

Ordinary Zen modules under `src/std/`, imported with `{ name } = std.path`:

| area | modules |
|---|---|
| core | `std.core.{result, ptr, slice, bool}`; `std.sys` (the root capability); `std.platform` (host/target OS, architecture, ABI) |
| collections | `std.collections.{vec, map, hmap, set, iter}` |
| text | `std.text.{str, string, fmt, num, bytes}` — `fmt` includes `println` and `{}`-template `format`/`formatln` |
| memory | `std.mem.{alloc, heap, arena, rc, arc, own, raw}` |
| concurrent | `std.concurrent.{actor, pool_actor, pool, sched, runtime, coroutine, cown, ring}` — cooperative typed actors (`actor`) vs parallel typed actors on the pool (`pool_actor` + trampoline); pool is one global run queue (work-stealing deques are roadmap) |
| io / os | `std.io.{c, file, stdin}`, `std.fs`, `std.os` (argv/env), `std.process`, `std.sync`, `std.atomic`, `std.thread` |
| data / encoding | `std.json`, `std.csv`, `std.encoding` (base64/hex), `std.path` |
| net / web | `std.net` (sockets), `std.web.dom` |
| misc | `std.math`, `std.time`, `std.rand`, `std.log`, `std.testing` |

## Build & run

Have a C compiler → `make` bootstraps once → from then on zen builds zen:

```sh
make                                   # bootstrap: cc bootstrap/{zenc.gen.c,zenrt.c} -> ./zen
./zen build                            # zen builds zen (dev profile: -O1 -g) -> ./zen-next
./zen build -r                         # release profile: -O2 -fno-strict-aliasing -> ./zen-next
mv zen-next zen                        # promote the freshly built compiler
```

The Makefile is bootstrap-only — the one step that cannot go through `build.zen` is compiling the
committed C seed when no `zen` binary exists yet (plus the seed-regen fixpoint below). Everything
else, including the compiler itself, builds through the compiler's own project mode: the repo-root
`build.zen` registers the `zen` target (entry `driver.zen`, runtime `bootstrap/zenrt.c`).
Optimization comes from cargo-style build profiles: `zen build` is the dev profile (`-O1 -g` —
fast compile, debuggable; never -O0, which would drop the sibling-call elimination the compiler's
recursion-only code needs), `zen build -r`/`--release` is the optimized profile
(`-O2 -fno-strict-aliasing`). A target's `.cflags(...)` still wins over the profile (cc's
last-flag-wins). `zen run` always uses the dev profile. `make build` is an alias for `./zen build`.
(The top-level `Makefile` forwards to `bootstrap/Makefile`; `make -f bootstrap/Makefile zen`
works too and is what CI invokes.)

CLI surface:

```sh
zenc init hello --bin          # create an executable project (omit flags for prompts)
zenc init math --lib           # create a checkable library project
zenc run prog.zen              # resolve std imports, type-check, emit C, link, run
zenc build prog.zen -o p       # same, but stop at the linked binary
zenc build --target js prog.zen -o p.js   # JS backend: write the JS floor + module to p.js
zenc targets project/          # list outputs registered by build.zen
zenc build --target app project/  # build one registered output
zenc build project/            # build every output explicitly installed by build.zen
zenc build -r project/         # same, release profile (-O2); default is dev (-O1 -g)
zenc build                     # no argument: use ./build.zen (so `./zen build` rebuilds the compiler)
zenc emit-js prog.zen          # JS backend: print the JS to stdout (`| node` to run)
zenc check prog.zen            # resolve + type-check only, no binary (accepts library modules)
zenc emit prog.zen             # print the generated C
zenc doc std.text.fmt          # render a module's doc surface
zenc fmt prog.zen              # format a source file in place
zenc lsp                       # diagnostics-only Language Server (JSON-RPC over stdio)
zenc --version                 # zenc 0.2.0-dev (self-hosted; zen driver)
cat prog.zen | zenc            # low-level filter: one already-flat module -> C on stdout
```

`run`/`build`/`emit-js` require `main` (either `main = () i32` or `main = (sys: Sys) i32`);
`check` accepts modules without `main`. The
checked modes (`run`/`build`/`check`/`emit`) run the self-hosted module loader
(`src/std/internal/resolve.zen`) first, so `{ ... } = std.X` imports resolve from disk and
the program is flattened before parsing. The bare-filter form (`cat file.zen | zenc`)
expects already-flat source and does no import loading or checking — use `zenc emit` for
real files with imports.

`init` is built into the standalone compiler; its templates do not depend on files from the
compiler checkout. `zenc init` prompts for a path and for executable versus library, while
`--bin`/`--lib` make it non-interactive. It can initialize an existing directory without touching
unrelated files, but never overwrites `zen.toml`, `build.zen`, or the generated entry source.

`check`/`build`/`run` also accept a project directory containing `zen.toml`:

```toml
package = "hello"
kind    = "executable"  # optional; "executable" (default) or "library"
root    = "src"
main    = "main.zen"
out     = "hello"
ccflags = "native.c"     # passed through to cc (extra sources / flags)
```

Library projects are source projects in this first version: `zenc check my_library` validates one,
but `zenc` does not yet emit a library archive. `build`/`run` reject a manifest whose
`kind = "library"` rather than silently producing the runtime's empty fallback executable.

**Regenerate the committed C** after editing any bootstrap compiler source (the manifest is
`bootstrap/sources.txt`, checked against the resolver graph's SCC order):

```sh
make -f bootstrap/Makefile regen       # zenc --build-self bootstrap/zenc.gen.c .
git diff --quiet bootstrap/zenc.gen.c  # the fixpoint: regenerated C must be byte-identical
```

**Tests.** The Zen-native harness (no Python — the repo has zero `.py` files):

```sh
make harness            # the Zen-native harness (tests/harness.zen); exit code = failing-case count
make harness-fast       # value + verdict smoke subset (~20s) for the inner loop
```

## Diagnostics

Checked-mode errors carry `file:line:col`, a stable error kind, a source-line caret, and a
hint:

```
$ zenc check prog.zen
zenc: prog.zen:4:13: error[arity]: wrong number of arguments
      println(add(1))
              ^~~
hint: check the callee signature and pass exactly the declared parameters
```

## Editor setup

`zen lsp` is a language server (JSON-RPC over stdio) that pushes the checker's full
diagnostics — same errors as `zen check`, live, with proper LSP positions. Wiring:

- **Neovim**: native `vim.lsp.start` config in [`editor/nvim/README.md`](editor/nvim/README.md)
- **VS Code**: minimal client extension in [`editor/vscode/`](editor/vscode/README.md)
- **Vim (syntax only)**: filetype + highlighting in [`editor/vim/`](editor/vim/)
- **Anything else**: generic LSP client → command `zen`, args `["lsp"]`, stdio transport

## How it works

```
                                                    ┌─ backend/c/c_emit.zen ─► C  ─► cc   (default)
 lex.zen ─tokens─► parse_*.zen ─► genc AST ─► check.zen ─┤
                                                    └─ backend/js/js.zen     ─► JS ─► node
 (every compiler stage is ordinary Zen, in src/compiler/)
```

The loader inserts every declaration at its path into one namespace, then the checker
resolves references, infers each body, and runs `fits(given, want)` at each call — the one
relation behind name resolution, numeric widening, structural type equality, pointer
direction/nullability, and trait-bound satisfaction. Checked structure then lowers to a
backend: C (pointers erase to plain C pointers) or JavaScript — the two are walks over the
*same* checked AST, so neither re-checks. Fed its **own** sources, `zenc` re-emits the
committed `bootstrap/zenc.gen.c` byte-for-byte.

## Caveats

This is rough around the edges. Known limits worth flagging up front:

- The stdlib is thin and uneven; APIs shift.
- Heterogeneous varargs don't exist (`...T` is single-type) — `format`/`formatln` take an
  explicit `[Arg]` slice (`arg_int`, `arg_str`, ...) rather than printf-style varargs.
- No closures and no source-level `if`/loop sugar by design (`.match` + `loop` + recursion).
- The bare-filter mode is intentionally minimal (no import loading, no checking).
- Identity is **nominal**: a type *is* its path, and you write each pointer's direction and
  nullability down.

## Layout

| path | role |
|---|---|
| `src/compiler/lex.zen` | the lexer — `scan(src, pos)` over a `string_view` |
| `src/compiler/parse*.zen` | recursive-descent parser → `compiler.genc` AST |
| `src/compiler/check.zen` + `check_validate.zen` + `diagnostic.zen` | resolver, `fits()` validator, positioned diagnostics |
| `src/compiler/genc.zen` + `mono.zen` + `backend/c/c_emit.zen` | shared AST, monomorphization, C backend |
| `src/compiler/backend/js/js.zen` | the JavaScript backend — a second walk over the same checked AST |
| `src/compiler/pretty.zen` | the `zenc fmt` formatter over the same AST |
| `src/std/` | the stdlib (`core`, `collections`, `text`, `mem`, `concurrent`, `io`, ...) |
| `src/std/internal/{resolve,ast}.zen` | the self-hosted module loader and AST-builder |
| `bootstrap/` | `zenc.gen.c` (committed emitted C) + `sources.txt` (graph/SCC-checked manifest) + `zenrt.c` (161-line C floor) + `zenrt.js` (JS floor) + `Makefile` |
| `examples/` | runnable single-file programs |
| `tests/` | the Zen-native harness (`harness.zen`) + fixtures |

## More docs

**[SPEC.md](docs/SPEC.md)** (language behavior) ·
**[STATUS.md](docs/STATUS.md)** (feature/roadmap ledger) ·
**[MEMORY_MODEL.md](docs/MEMORY_MODEL.md)** (ownership / allocator rules) ·
**[ARCHITECTURE.md](docs/ARCHITECTURE.md)** (compiler structure).
Everything else lives in Git history; `make docs-check` keeps this set deliberate.

Inspired by treeform's [jsony](https://github.com/treeform/jsony) (parse straight into typed
objects) and the syntax of [zenlang](https://github.com/lantos1618/zenlang).
