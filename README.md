# zen

**zen** is a small, **self-hosted** compiler for a [Zen](https://github.com/lantos1618/zenlang)-flavoured
language. The compiler is written in Zen, compiles itself, and has **two backends** over one
shared AST: **C** (`genc`, the default and the intentional bootstrap target — not a
host-language fallback) and **JavaScript** (`genjs`, run under `node`). There is **no Python
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
  let-bindings; slices `[T]`; the full operator set (`+ - * / %  == < > <= >=  && || !`).
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
  rejects use-after-`release`/`drop` for `Own`/`Rc`/`Arc`. See **[MEMORY_MODEL.md](MEMORY_MODEL.md)**.
- **Metaprogramming as values.** Build an AST with `std.internal.ast` and emit it with
  `compiler.genc.genModule` — no `@emit` pragma.

## The standard library

Ordinary Zen modules under `zen/std/`, imported with `{ name } = std.path`:

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

The compiler is the `zenc` binary; `cc` builds it from committed C, nothing else needed.

```sh
make                                   # cc bootstrap/{zenc.gen.c,zenrt.c} -> ./zenc
```

(The top-level `Makefile` forwards to `bootstrap/Makefile`; `make -f bootstrap/Makefile zenc`
works too and is what CI invokes.)

CLI surface:

```sh
zenc run prog.zen              # resolve std imports, type-check, emit C, link, run
zenc build prog.zen -o p       # same, but stop at the linked binary
zenc build --target js prog.zen -o p.js   # JS backend: write the JS floor + module to p.js
zenc targets project/          # list the named outputs in a build.zen Plan
zenc build --target app project/  # build one named output from the Plan
zenc build project/            # build every output explicitly returned by its Plan
zenc emit-js prog.zen          # JS backend: print the JS to stdout (`| node` to run)
zenc check prog.zen            # resolve + type-check only, no binary (accepts library modules)
zenc emit prog.zen             # print the generated C
zenc doc std.text.fmt          # render a module's doc surface
zenc fmt prog.zen              # format a source file in place
zenc --version                 # zenc 0.2.0-dev (self-hosted; zen driver)
cat prog.zen | zenc            # low-level filter: one already-flat module -> C on stdout
```

`run`/`build`/`emit-js` require `main` (either `main = () i32` or `main = (sys: Sys) i32`);
`check` accepts modules without `main`. The
checked modes (`run`/`build`/`check`/`emit`) run the self-hosted module loader
(`zen/std/internal/resolve.zen`) first, so `{ ... } = std.X` imports resolve from disk and
the program is flattened before parsing. The bare-filter form (`cat file.zen | zenc`)
expects already-flat source and does no import loading or checking — use `zenc emit` for
real files with imports.

`check`/`build`/`run` also accept a project directory containing `zen.toml`:

```toml
package = "hello"
root    = "src"
main    = "main.zen"
out     = "hello"
ccflags = "native.c"     # passed through to cc (extra sources / flags)
```

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

## How it works

```
                                                    ┌─ genc_emit.zen ─► C  ─► cc   (default)
 lex.zen ─tokens─► parse_*.zen ─► genc AST ─► check.zen ─┤
                                                    └─ genjs.zen     ─► JS ─► node
 (every compiler stage is ordinary Zen, in zen/compiler/)
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
| `zen/compiler/lex.zen` | the lexer — `scan(src, pos)` over a `string_view` |
| `zen/compiler/parse*.zen` | recursive-descent parser → `compiler.genc` AST |
| `zen/compiler/check.zen` + `check_validate.zen` + `diagnostic.zen` | resolver, `fits()` validator, positioned diagnostics |
| `zen/compiler/genc.zen` + `mono.zen` + `genc_emit.zen` | shared AST, monomorphization, C backend |
| `zen/compiler/genjs.zen` | the JavaScript backend — a second walk over the same checked AST |
| `zen/compiler/pretty.zen` | the `zenc fmt` formatter over the same AST |
| `zen/std/` | the stdlib (`core`, `collections`, `text`, `mem`, `concurrent`, `io`, ...) |
| `zen/std/internal/{resolve,ast}.zen` | the self-hosted module loader and AST-builder |
| `bootstrap/` | `zenc.gen.c` (committed emitted C) + `sources.txt` (graph/SCC-checked manifest) + `zenrt.c` (161-line C floor) + `zenrt.js` (JS floor) + `Makefile` |
| `examples/` | runnable single-file programs |
| `tests/` | the Zen-native harness (`harness.zen`) + fixtures |

## More docs

**[SPEC.md](SPEC.md)** (language behavior) ·
**[FEATURES.md](FEATURES.md)** (full inventory) ·
**[MEMORY_MODEL.md](MEMORY_MODEL.md)** (ownership / allocator rules) ·
**[ERROR_POLICY.md](ERROR_POLICY.md)** (Result/error contract) ·
**[ARCHITECTURE.md](ARCHITECTURE.md)** (compiler structure) ·
**[VISION.md](VISION.md)** (the why) · **[CHANGELOG.md](CHANGELOG.md)** (history).

Inspired by treeform's [jsony](https://github.com/treeform/jsony) (parse straight into typed
objects) and the syntax of [zenlang](https://github.com/lantos1618/zenlang).
