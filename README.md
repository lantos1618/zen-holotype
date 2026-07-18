# Zen

Zen is a small self-hosted language and compiler. The compiler is written in Zen, emits C or
JavaScript from one checked AST, and can reproduce its committed C bootstrap byte-for-byte.

It is usable, but not finished. The C path, core type system, formatter, diagnostics, project
initializer, standard library, and actor pool all work. Packages, the JavaScript backend, ownership
analysis, and the runtime surface still have explicit limits. [STATUS.md](STATUS.md) is the honest
feature and roadmap ledger.

## Start here

The C toolchain needs a POSIX-like host, `make`, and `cc`. Node is optional for the JavaScript
backend.

```sh
make
./zenc run examples/hello.zen
```

Output:

```text
hello, zen
42
```

Create a project with the initializer embedded in the compiler binary:

```sh
./zenc init hello --bin
./zenc run hello

./zenc init arithmetic --lib
./zenc check arithmetic
```

Omit `--bin`/`--lib` to choose interactively. `init` creates missing directories but never
overwrites its manifest, build file, or generated source.

## A small program

```zen
{ println } = std.text.fmt
classify = (n: i32) string_view { (n > 10).match ({ true => "large", false => "small" }) }
main = () i32 {
    println(classify(42))
    0
}
```

Zen has no ordinary `if` statement. Branch on a value with `.match`; writing `if (...)` produces an
`error[if-statement]` diagnostic that points to `.match`. The current parser still accepts
`pattern if guard => ...` inside match arms. That remaining use of `if` is tracked as a language
consistency issue in [STATUS.md](STATUS.md).

The core surface is deliberately compact:

- records are product types: `Point: { x: i32, y: i32 }`;
- enums are sum types: `Opt<T>: Some(T) | None`;
- functions and declarations use `name = value`; `*` marks a public declaration;
- `.match` handles bools, literals, and enums;
- `x.f(a)` is UFCS for `f(x, a)` and also drives receiver-aware method lookup;
- generics are monomorphized and traits are records of required method signatures;
- fallible operations return `Result<T, E>`; `.or_return()` propagates `.Err` by value;
- `Ptr<T>`, `MutPtr<T>`, and `RawPtr<T>` preserve read/write/nullability distinctions in the
  checker while lowering to ordinary target pointers;
- heap-backed values take an allocator explicitly, although a still-live legacy `std.rt` ambient
  allocator surface has not yet been retired.

See [SPEC.md](SPEC.md) for current syntax and [MEMORY_MODEL.md](MEMORY_MODEL.md) for the exact safety
guarantees and their boundaries.

## Commands

| Command | Behavior |
|---|---|
| `zenc init [path] [--bin\|--lib]` | Create an executable or check-only library project. |
| `zenc check <file-or-project>` | Resolve imports and type-check; no `main` required. |
| `zenc run <file-or-project> [args...]` | Check, emit C, compile, and run. |
| `zenc build <file-or-project> [-o path]` | Check, emit C, and link an executable. |
| `zenc emit <file>` | Check and write generated C to stdout. |
| `zenc emit-js <file>` | Check and write the JS runtime floor plus program to stdout. |
| `zenc build --target js <file> [-o path]` | Write a JavaScript program; default output is `a.js`. |
| `zenc fmt [--check] <file>` | Format in place, or fail if formatting is needed. |
| `zenc fmt --stdout <file>` | Format to stdout without changing the file. |
| `zenc doc <std.module\|file.zen>` | Print public declaration heads and adjacent line docs. |
| `zenc --version` | Print the compiler version. |

`cat flat.zen | zenc` and `zenc flat.zen` are low-level source-to-C filters. They do not load imports
or run the checked CLI pipeline; use `emit`, `check`, `build`, or `run` for normal source files.

The binary locates `zen/std`, `zen/compiler`, and `bootstrap` relative to itself. Set `ZEN_ROOT` to a
checkout root when running a relocated binary.

## Projects and imports

`zenc init` writes a `zen.toml` project:

```toml
package = "hello"
kind = "executable"
root = "src"
main = "main.zen"
out = "hello"
```

`root` and `main` are required. `kind` is `executable` by default or `library`; library projects can
currently be checked but not archived or linked. `out`, `ccflags`, and one `link` library are
optional. `package` is metadata today; resolution does not consume it.

A `build.zen` beside the manifest takes precedence and computes an executable target in Zen:

```zen
{ Build, Target, exe } = std.build
build = (b: Build) Target { exe("hello").root("src").main("main.zen").out("hello") }
```

Imports expose public declarations from standard, compiler, or local modules:

```zen
{ println } = std.text.fmt
fmt = std.text.fmt
{ double } = helper
helper_ns = helper
```

`std.*` and `compiler.*` use dotted paths. A local import names one sibling file next to the entry
source: `helper` loads `helper.zen`. Nested local paths such as `some.package` and registered package
roots are not implemented yet. Namespace binds such as `helper_ns = helper` permit
`helper_ns.double(21)`, but the shipping CLI still has a compatibility flattening boundary rather
than a finished package/symbol-table linker.

## Build, test, and bootstrap

```sh
make                 # build ./zenc from committed C
make docs-check      # enforce the canonical doc set and validate local links
make harness-fast    # inner-loop value/verdict subset
make harness         # full Zen-native harness
make regen           # regenerate bootstrap/zenc.gen.c after compiler changes
```

`make regen` must leave a byte fixpoint:

```sh
make regen
cp bootstrap/zenc.gen.c /tmp/zenc.before.c
make regen
cmp /tmp/zenc.before.c bootstrap/zenc.gen.c
```

The full harness covers compilation, runtime values, rejects, diagnostics, modules, projects,
formatting, both backends, stdlib behavior, fuzzing, architectural boundaries, and the bootstrap
fixpoint. It is broad but structurally overgrown; the measured test assessment and simplification
plan are in [STATUS.md](STATUS.md).

## Repository map

| Path | Role |
|---|---|
| `driver.zen` | CLI, project handling, diagnostics, compilation, `fmt`, `doc`, and `init`. |
| `zen/compiler/` | Lexer, parser, semantic passes, shared AST, formatter, C and JS emitters. |
| `zen/std/` | Standard library, runtime surfaces, collections, IO, memory, and concurrency. |
| `bootstrap/` | Committed generated C, C/JS runtime floors, source manifest, and build rules. |
| `examples/` | Runnable C examples plus the browser-only DOM example. |
| `tests/` | Zen-native harness and fixtures. |

The maintained documents are intentionally few:

- [SPEC.md](SPEC.md): current language and module contract;
- [MEMORY_MODEL.md](MEMORY_MODEL.md): enforced memory, pointer, escape, and send rules;
- [ARCHITECTURE.md](ARCHITECTURE.md): compiler, bootstrap, runtime, and test architecture;
- [STATUS.md](STATUS.md): goals, feature/test coverage, live limits, and ordered next work;
- [bootstrap/README.md](bootstrap/README.md): local bootstrap operations;
- [examples/README.md](examples/README.md): example catalog.

Historical plans, judge reports, research dumps, completed repro essays, and duplicated feature
inventories were removed from the live tree. Git history remains their archive.
