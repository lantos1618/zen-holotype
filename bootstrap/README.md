# bootstrap — the self-hosted Zen compiler, as a Python-free binary

The Zen compiler is written in Zen: `zen/compiler/lex.zen` (lexer),
`zen/compiler/parse.zen` (parser), `zen/compiler/check.zen` (resolver + validator),
and `zen/compiler/genc.zen` (C backend). This directory holds everything needed to build
it into a standalone `zenc` binary **without Python**:

| file          | what it is                                                            |
|---------------|-----------------------------------------------------------------------|
| `zenc.gen.c`  | the compiler `.zen` sources, compiled to C by the toolchain itself (generated) |
| `zenrt.h/.c`  | the ~200-line C runtime floor: growable `String`, `eq`/`is_empty`, `heap`, OS shims, actor panic isolation |
| `sources.txt` | the graph/SCC-checked manifest of Zen sources used to regenerate `zenc.gen.c` |
| `Makefile`    | `zenc:` builds the binary, `regen:` regenerates `zenc.gen.c` with it — NO Python |

There is no separate `main.c` — the CLI is `driver.zen`, compiled into `zenc.gen.c`.
The binary is `cc bootstrap/{zenc.gen.c,zenrt.c}`.

## Build & run

```sh
make -f bootstrap/Makefile zenc   # cc bootstrap/{zenc.gen.c,zenrt.c} -o zenc
./zenc path/to/flat.zen > out.c  # plain emit mode; see ../README.md for check/build/run
```

## The fixpoint

`zenc` reads Zen and emits C. Fed its **own** graph-listed Zen sources, it emits
byte-for-byte the C in `zenc.gen.c` — the compiler reproduces itself. The Zen-native
oracle (`tests/harness.zen`, `fixpoint` suite) builds the binary from the committed C
and checks that reproduction. The modules oracle checks that `sources.txt` matches the
resolver graph's SCC order.

## After editing a compiler source

`zenc.gen.c` is generated, so regenerate it whenever you change a source listed in
`bootstrap/sources.txt`, including
`zen/compiler/{genc*,lex,parse*,check*}.zen`, `zen/compiler/check_validate.zen`,
`driver.zen`, or std modules the compiler imports.
The regen runs with **zero Python** — the binary regenerates its own source via `--build-self`:

```sh
make -f bootstrap/Makefile regen   # builds zenc, then: ./zenc --build-self bootstrap/zenc.gen.c .
```
