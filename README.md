# zen

A self-hosted compiler for the Zen language. 57,392 lines of Zen compile
themselves; the only hand-written C in the build is a 253-line runtime floor
(`bootstrap/zenrt.c` + `zenrt.h`). Everything else that looks like C was emitted
by this compiler — and it re-emits itself byte-for-byte.

## Verify it yourself

Four commands. Have a C compiler.

```sh
git clone https://github.com/lantos1618/zen-holotype && cd zen-holotype
make                     # cc compiles the committed seed (bootstrap/zenc.gen.c) -> ./zen   ~20s
./zen build              # zen compiles zen -> ./zen-next  (dev -O1 -g; `-r` for release -O2)
make regen && git diff --quiet bootstrap/zenc.gen.c && echo fixpoint
```

That last line is the trust story: the compiler, fed its own sources, reproduces
the committed 2,378,142-byte C seed **exactly**. Deterministic. Diffable. No
pipeline behind the curtain.

## One binary

Every verb below was run against this commit before it was written down.

- `./zen run prog.zen` — resolve imports, type-check, emit C, `cc`, run.
  `--time` prints per-stage timings; a directory holding `zen.toml` or
  `build.zen` runs as a project
- `./zen build` — project mode; `-r` for release, `-o <path>` to name the output,
  `--target js <file>` to write a node program instead. In a `zen.toml` project
  name the directory (`./zen build .`); a bare `./zen build` only defaults to the
  current directory when a `build.zen` is present
- `./zen check prog.zen` — types only, no codegen
- `./zen emit prog.zen` — the C this program lowers to, on stdout
- `./zen emit-js prog.zen` — the JavaScript it lowers to, on stdout
- `./zen fmt prog.zen` — rewrite in place; `--check` exits nonzero on drift,
  `--stdout` previews
- `./zen init hello --bin` — new project (`zen.toml` + `src/main.zen`) that runs as-is
- `./zen lsp` — language server over stdio: diagnostics, semantic highlighting,
  go-to-definition, hover, completion (see below)
- `./zen audit prog.zen` — dead-code, unused-import and clone report;
  `--workspace <dir>` unions across every entry point, `--strict` exits 1
- `./zen doc std.sort` — a module's exported surface
- `./zen targets .` — targets registered by `build.zen`
- `./zen profile prog.zen [-- args]` — sampling profile (perf, gprof fallback) as
  a `SELF% CUM% FUNCTION` table with zen-native names ([recipe](docs/profiling.md))

`zen --help` lists all of these: its command list and the dispatcher are generated
from the same table in `driver.zen`, so the two cannot drift apart.

Two backends, one checked AST. The same program, both targets:

```
$ ./zen run examples/hello.zen              # C -> cc -> native
hello, zen
42
$ ./zen emit-js examples/hello.zen | node   # JS -> node
hello, zen
42
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

What you just read, and where it is specified ([docs/SPEC.md](docs/SPEC.md)):

- **`.match` is the only conditional.** `.then({ a }, { b })` is its expression
  form; `.loop` and recursion cover iteration. `if` and `?:` are not merely
  absent — the parser rejects them by name, with a hint that rewrites them:

  ```
  $ ./zen check noif.zen
  zenc: noif.zen:3:5: error[no-if]: `if` is not part of Zen; conditional control flow uses `.match`
        if (1 == 1) { println("yes") }
        ^~
  hint: in expression position write `cond.then({ yes }, { no })`; for statement-position control flow replace `if (cond) { yes } else { no }` with `cond.match ({ true => yes, false => no })`; inside an enum arm, nest a boolean `.match` in the arm body
  ```

  `while` and `as` have no such dedicated guard — they are simply undefined
  names, and you get `error[undefined-name]`.
- **No cast keyword.** Conversions are ordinary methods: `x.to_i64()` on an `f64`
  truncates (`3.7` becomes `3`).
- **Errors are values.** `Result<T, E>` / `Opt<T>`, `.or_return()` to propagate,
  `panic` only when you write it. The emitted C guards the rest: `10 / d` with
  `d == 0` prints `zen: panic: integer divide by zero` and aborts; an
  out-of-range index prints `zen: panic: slice index out of bounds`. Not UB.
- **Reflection at compile time.** `each_field` / `zip_fields` / `field_eq` unroll
  per-field at monomorphization, and `e.variant_name()` expands to a literal switch
  over an enum's variants — derived equality and JSON serde are ordinary
  library code, no macros — see `std.format.serde`.
- **Generics, traits, UFCS.** Monomorphized generics; a trait is a record of
  signatures, an impl is `Type.impl(Trait, { ... })`, dispatched by receiver
  (`examples/tour.zen`).
- **Three pointer types, checker-enforced.** `Ptr<T>` read-only, `MutPtr<T>`
  writable, `RawPtr<T>` the nullable raw floor. A write through `Ptr<T>` is
  `error[ptr-write]` at compile time.
- **Raw strings.** `"""…"""` spans lines and takes bytes literally — a `\n`
  inside one stays two characters.
- **Memory is explicit.** Allocators are values you thread; no hidden heap;
  touching a pointer after `free` is `error[ownership]` at compile time.
  ([docs/MEMORY_MODEL.md](docs/MEMORY_MODEL.md))
- **Actors on real threads.** Typed actors on a pthread pool; a send moves
  ownership (checker-enforced), a panic kills one actor, not the pool.
  `./zen run examples/pool_actor_demo.zen` fans 1000 messages across OS cores
  and prints `total=1000`.

12 [`examples/`](examples/): 11 compile and run natively, `dom_demo` is
browser-only — `emit-js` lowers it to real DOM calls, but it needs a browser
page, not `node` (there is no `document` there). Several are Unix filters that
want stdin or an argument — [`examples/README.md`](examples/README.md) gives the
invocation for each.

## The stdlib

69 modules under [`src/std`](src/std), every one of them import-probed by the
harness:

`argparse` `build` `hash` `log` `math` `rand` `rt` `scope` `sort` `testing` ·
**c** `libc` · **collections** `btree` `hashidx` `hmap` `iter` `map` `set` `vec` ·
**concurrent** `actor` `atomic` `coroutine` `cown` `pool` `pool_actor` `ring`
`runtime` `sched` `sync` `thread` · **core** `bool` `ptr` `result` `slice` ·
**format** `csv` `encoding` `json` `serde` · **io** `bufwriter` `c` `file` `stdin` ·
**mem** `alloc` `arc` `arena` `heap` `own` `raw` `rc` `trace` ·
**net** `http` `http_actor` `socket` · **sys** `fs` `os` `path` `platform`
`process` `root` · **text** `ascii` `fmt` `num` `regex` `sb` `str` `string` ·
**time** `clock` `datetime` · **web** `dom` · **internal** `ast`

`./zen doc <module>` prints any of their exported signatures.

## Numbers

Measured on this commit: one 16-core AMD EPYC-Milan box, Linux 6.8, gcc 13.3.
No cherry-picking.

| what | measured |
|---|---|
| Zen source | 57,392 lines (compiler 38,718 · stdlib 15,631 · driver 3,043) |
| hand-written C | 253 lines (`bootstrap/zenrt.c` 224 + `zenrt.h` 29) — plus a 140-line JS floor |
| committed seed | `bootstrap/zenc.gen.c`, 2,359,007 bytes of compiler-emitted C |
| bootstrap `make` | 20 s |
| self-compile | `./zen build` 17 s → 4.10 MB dev · `./zen build -r` 25 s → 1.72 MB release |
| seed regen `make regen` | 3.7 s, byte-identical to the committed seed |
| check the whole compiler | `./zen check driver.zen` 2.2 s cold, 0.01 s warm (content-hash cache in `/tmp/zenc-cache`) |
| test harness `make harness` | 23 s — 73 suite blocks, 3,069 cases, `ALL PASS` |
| harness source | 12,642 lines of Zen over 310 fixture programs |
| formatter proof | 217-file corpus: `fmt` is idempotent and the formatted file emits **byte-identical C** |

The harness tests its own oracles: a `fmt_roundtrip teeth` suite hand-breaks a
formatted file to prove the byte-comparison actually fails, and a `fixpoint`
suite re-derives the seed. `make harness-fast` runs the quick subset.

## Diagnostics

`file:line:col`, a stable error kind, a caret, a hint:

```
$ ./zen check bad.zen
zenc: bad.zen:4:13: error[arity]: wrong number of arguments: expected 2, found 1
      println(add(1))
              ^~~
hint: check the callee signature and pass exactly the declared parameters
```

## Editor

`./zen lsp` speaks JSON-RPC over stdio and advertises exactly what it implements:

```
$ printf 'Content-Length: 58\r\n\r\n{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | ./zen lsp
Content-Length: 409

{"jsonrpc":"2.0","id":1,"result":{"capabilities":{"textDocumentSync":1,"definitionProvider":true,"hoverProvider":true,"completionProvider":{"resolveProvider":false},"semanticTokensProvider":{"legend":{"tokenTypes":["keyword","function","type","variable","property","string","number","comment","operator","enumMember"],"tokenModifiers":[]},"full":true}},"serverInfo":{"name":"zenc-lsp","version":"0.2.0-dev"}}}
```

Diagnostics — the same errors `zen check` prints, including ones surfaced from
imported sibling modules — plus go-to-definition, hover, completion and
full-document semantic tokens. Positions are 0-based UTF-16, so non-ASCII lines
squiggle in the right place. The server checks the buffer the client sent, not
the file on disk: open a file that has never been saved and it still gets
diagnostics and `gd`. Anything else — `textDocument/references` and the rest —
gets a clean `method not found` (`-32601`).

- **Neovim** — [`editor/nvim/README.md`](editor/nvim/README.md). Three symlinks,
  `ftplugin/` included, or `gc` and the indent width silently do nothing.
- **VS Code** — [`editor/vscode`](editor/vscode/README.md)
- anything else: command `zen`, args `["lsp"]`, stdio

## What is not there yet

Each of these was reproduced on this commit.

- **No TLS and no DNS.** `std.net.http` rejects `https://` outright
  (`http: https is not supported (no TLS)`), and `std.net.socket` parses hosts as
  IPv4 dotted-quads or `localhost` — nothing resolves a name, so
  `http_get("http://example.com/")` fails with a `Connect` error.
- **JSON numbers are `f64`, full stop.** `std.format.json`'s `Value` has one
  numeric arm, `Num(f64)`. `{"small":42}` stringifies back as `{"small":42.0}`,
  and `9007199254740993` returns as `9.00719925474099e+15`. The module header
  claims integral values print without a decimal point; they do not.
- **Text search has no byte-slice side.** `std.io.file.contents_bytes` gives you a
  binary-safe `[u8]`, but `find` / `contains` / `starts_with` / `split` in
  `std.text.str` all take a NUL-terminated `string_view`. Searching what you just
  read is `error[arg-type]: expected string_view, got [u8]`.
- **Allocated strings have no release verb.** `std.text.str`'s `cat` / `join` /
  `replace` / `to_lower` return allocator-owned `string_view`s, and nothing in
  the module hands one back. Freeing one means reaching past the API for
  `free(s.view().ptr)` yourself; the intended pattern is to back them with an
  arena and reset it.
- **An escaping closure is not diagnosed.** Capturing lambdas work while they
  stay within the frame, but returning one compiles to C that does not link, and
  you get `zenc: internal: generated C failed to compile` instead of a type error.
- **A variadic param mis-lays-out untyped literals.** With `xs: ...i64`, the
  call `total("sum", 1, 2, 3)` reads its slice back as `8589934593, 3, 0` — the
  literals were packed as `i32`. Explicitly-typed `i64` arguments work, and
  `...i32` works; the failure is a silent wrong answer, not a crash.
- **The JS backend emits further than it runs.** `emit-js` produces
  syntactically valid JavaScript for all 15 examples, but only 5 of the 14
  native-runnable ones print the same thing under `node`. The rest reach missing
  runtime pieces — `argv`, the allocator, actors — at run time, not at emit time.

[docs/STATUS.md](docs/STATUS.md) is the fuller ledger — every feature area mapped
to its implementation and its executable proof.

## Docs

[docs/SPEC.md](docs/SPEC.md) — language behavior ·
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — compiler structure ·
[docs/MEMORY_MODEL.md](docs/MEMORY_MODEL.md) — ownership rules ·
[docs/STATUS.md](docs/STATUS.md) — status ledger ·
[docs/profiling.md](docs/profiling.md) — profiling recipe.
`make docs-check` keeps this set deliberate; everything else lives in git history.

---

A type is a lock. A program that compiles has already closed every door it was
never supposed to open. Start reading at [`driver.zen`](driver.zen).
