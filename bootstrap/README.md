# bootstrap — the self-hosted Zen compiler, as a Python-free binary

The Zen compiler is written in Zen: `std/lex.zen` (lexer), `std/parse.zen` (parser),
`std/check.zen` (resolver + validator), `std/genc.zen` (C backend). This directory holds
everything needed to build it into a standalone `zenc` binary **without Python**:

| file          | what it is                                                            |
|---------------|-----------------------------------------------------------------------|
| `zenc.gen.c`  | the compiler `.zen` sources, compiled to C by the toolchain itself (generated) |
| `zenrt.h/.c`  | a ~30-line runtime: the growable `String`, `eq`/`is_empty`, `heap`     |
| `main.c`      | the CLI entry — reads Zen source (file/stdin → C on stdout), plus `--build-self` (Python-free regen) |
| `Makefile`    | `zenc:` builds the binary, `regen:` regenerates `zenc.gen.c` with it — NO Python |

## Build & run

```sh
make -f bootstrap/Makefile zenc   # cc -std=gnu11 -w bootstrap/{zenc.gen.c,zenrt.c,main.c} -o zenc
./zenc path/to/source.zen        # or: echo 'add* = (a:i32,b:i32) i32 { a+b }' | ./zenc
```

## The fixpoint 🏁

`zenc` reads Zen and emits C. Fed its **own** four source files, it emits byte-for-byte
the C in `zenc.gen.c` — the compiler reproduces itself. `tests/test_bootstrap.py` builds
the binary from the committed C and checks that reproduction.

## After editing a compiler source

`zenc.gen.c` is generated, so regenerate it whenever you change `std/{genc,lex,parse,check}.zen`.
The regen runs with **zero Python** — the binary regenerates its own source via `--build-self`:

```sh
make -f bootstrap/Makefile regen   # builds zenc, then: ./zenc --build-self bootstrap/zenc.gen.c .
```
