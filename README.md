# zen

A self-hosted compiler for the Zen language.
53,061 lines of Zen compile themselves; the only hand-written C in the build is a
224-line runtime floor. Everything else that looks like C was emitted by this
compiler — and it re-emits itself byte-for-byte.

## Verify it yourself

Four commands. Have a C compiler.

```sh
git clone https://github.com/lantos1618/zen-holotype && cd zen-holotype
make                     # cc compiles the committed seed (bootstrap/zenc.gen.c) -> ./zen   ~15s
./zen build              # zen compiles zen -> ./zen-next  (dev -O1 -g; `-r` for release -O2)
make regen && git diff --quiet bootstrap/zenc.gen.c && echo fixpoint
```

That last line is the trust story: the compiler, fed its own sources, reproduces
the committed 2.6 MB C seed **exactly**. Deterministic. Diffable. No pipeline
behind the curtain.

## One binary

Every verb below was run before it was written down.

- `./zen run prog.zen` — resolve imports, type-check, emit C, `cc`, run; `--time` prints per-stage compile timings
- `./zen build` — project mode via `build.zen`; `-r` for release, `--target js` writes a node program
- `./zen profile prog.zen [-- args]` — sampling profile (perf, gprof fallback) as a `SELF% CUM% FUNCTION` table with zen-native names ([recipe](docs/profiling.md))
- `./zen check prog.zen` — types only; the whole compiler closure checks warm in 0.05s
- `./zen emit prog.zen` / `./zen emit-js prog.zen | node` — see exactly what lowers
- `./zen fmt prog.zen` — formatter, proven safe (below)
- `./zen init hello --bin` — new project; the generated project runs as-is
- `./zen lsp` — language server, live checker diagnostics over stdio
- `./zen audit driver.zen` — dead-code + unused-import report
- `./zen doc std.text.fmt` — a module's exported surface
- `./zen targets .` — outputs registered by `build.zen`

Two backends, one checked AST. The same program, both targets:

```sh
$ ./zen run examples/hello.zen              # C -> cc -> native
hello, zen
$ ./zen emit-js examples/hello.zen | node   # JS -> node
hello, zen
```

## The language, in code that runs

```zen
{ println } = std.text.fmt
{ Result, IoError } = std.core.result

Point: { x: i64, y: i64 }
eq<T> = (a: T, b: T) bool { a.field_eq(b) }   // derived ==, unrolled at compile time

checked_div = (n: i32, d: i32) Result<i32, IoError> {
    (d == 0).match({ true => .Err(.NotFound), false => .Ok(n / d) })
}
half = (n: i32) Result<i32, IoError> {
    q := checked_div(n, 2).or_return()        // unwrap .Ok, or propagate the .Err
    .Ok(q)
}

main = () i32 {
    half(84).match({
        .Ok(v)  => println(v),                // 42
        .Err(_) => println("division refused"),
    })
    eq(Point(x: 1, y: 2), Point(x: 1, y: 2)).match({
        true  => println("points equal"),
        false => println("points differ"),
    })
    0
}
```

What you just read, and where it's specified ([docs/SPEC.md](docs/SPEC.md)):

- **`.match` is the only conditional.** No `if`, no `while`, no exceptions —
  `if` is a compile error, `error[no-if]`, with a hint that rewrites it for you.
  Recursion and `loop` cover iteration. (§ Structs, Enums, Match)
- **Errors are values.** `Result<T, E>` / `Opt<T>`, `.or_return()` to propagate,
  `panic` only when you write it — and the emitted C guards div-by-zero,
  index-out-of-bounds, and null deref with a clean panic, not UB. (§ Errors And Results)
- **Reflection at compile time.** `each_field` / `zip_fields` / `field_eq` unroll
  per-field at monomorphization — derived equality and JSON serde are ordinary
  library code, no macros. `./zen run examples/json_demo.zen` round-trips typed
  structs through JSON and prints `ROUNDTRIP_EQUAL`. (§ Generics)
- **Generics, traits, UFCS.** Monomorphized generics; a trait is a record of
  signatures, an impl is `Type.impl(Trait, { ... })`, dispatched by receiver:
  `x.area()`. (§ Traits, Impls, Methods)
- **Three pointer types, checker-enforced.** `Ptr<T>` read-only, `MutPtr<T>`
  writable, `RawPtr<T>` the nullable raw floor; writes through `Ptr` and
  unproven null derefs are compile errors. (§ Types)
- **Strings carry provenance.** `string_literal`, `string_cstr`, `string_view`
  for borrows; `String` owns. (§ Types)
- **Memory is explicit.** Allocators are values you thread; no hidden heap; the
  checker rejects use-after-release. ([docs/MEMORY_MODEL.md](docs/MEMORY_MODEL.md))
- **Actors on real threads.** Typed actors on a pthread pool; a send moves
  ownership (checker-enforced), a panic kills one actor, not the pool.
  `./zen run examples/pool_actor_demo.zen` fans 1000 messages across OS cores
  and prints `total=1000`. (§ Concurrency)

All 12 [`examples/`](examples/) compile — 11 run native with `./zen run`,
`dom_demo` is browser-only (`emit-js` verified).

## Numbers

Measured on this commit, one Linux box, no cherry-picking.

| what | measured |
|---|---|
| Zen source | 53,061 lines (compiler 29,631 · stdlib 18,972 · driver 4,458) |
| hand-written C | 224 lines (`bootstrap/zenrt.c`) — plus a 110-line JS floor |
| committed seed | `bootstrap/zenc.gen.c`, 2,601,957 bytes of compiler-emitted C |
| bootstrap `make` | 15 s |
| self-compile | `./zen build` 20 s → 3.8 MB dev · `./zen build -r` 25 s → 1.5 MB release |
| seed regen `make regen` | 12 s, byte-identical to the committed seed |
| check the whole compiler | 8.5 s cold, 0.05 s warm (content-hash cache) |
| test harness `make harness` | 64 suites, 2,563 cases, `ALL PASS` — the harness itself is 11,118 lines of Zen |
| formatter proof | 204-file corpus: `fmt` is idempotent and the formatted file emits **byte-identical C** |

The harness tests its own oracles: a "teeth" suite hand-breaks a formatted file
to prove the byte-comparison actually fails.

## Diagnostics

`file:line:col`, a stable error kind, a caret, a hint:

```
$ ./zen check bad.zen
zenc: bad.zen:4:13: error[arity]: wrong number of arguments: expected 2, found 1
      println(add(1))
              ^~~
hint: check the callee signature and pass exactly the declared parameters
```

The same diagnostics stream through `./zen lsp`:

- **Neovim** — [`editor/nvim/README.md`](editor/nvim/README.md)
- **VS Code** — [`editor/vscode/`](editor/vscode/README.md)
- anything else: command `zen`, args `["lsp"]`, stdio

## Honest limits

- The stdlib is thin and APIs shift; the JS backend is experimental.
- No closures over escaping captures; single-type varargs only.
- [docs/STATUS.md](docs/STATUS.md) is the ledger — every feature area mapped to
  its implementation and its executable proof, boundaries stated.

## Docs

[docs/SPEC.md](docs/SPEC.md) — language behavior ·
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — compiler structure ·
[docs/MEMORY_MODEL.md](docs/MEMORY_MODEL.md) — ownership rules ·
[docs/STATUS.md](docs/STATUS.md) — status ledger.
`make docs-check` keeps this set deliberate; everything else lives in git history.

---

A type is a lock. A program that compiles has already closed every door it was
never supposed to open. Start reading at [`driver.zen`](driver.zen).
