# Bootstrap

The frozen stage-0 compiler. Everything here is an artifact — there is no compiler source in this
tree to regenerate it from.

| File | Role |
|---|---|
| `zenc.gen.c` | Committed C, emitted from the compiler source graph plus `driver.zen` as they stood at `main`. Supplies `zen_main`; there is no separate C driver. |
| `zenrt.h` / `zenrt.c` | Hand-written C process, OS, thread, and panic-isolation floor. |
| `zenrt.js` | JavaScript runtime floor for the retired `emit-js` target. Kept only because stage-0 still advertises the flag. |
| `sources.txt` | Provenance: the graph/SCC-ordered file list `zenc.gen.c` was generated from. Those files live on `main`, not here. |
| `Makefile` | Retains every target; only `zen` and `clean` can run without the deleted sources. |

## Build

From the repository root:

```sh
make
```

or directly:

```sh
make -f bootstrap/Makefile zen
```

The output is `./zen`; an unchanged build is an mtime no-op. If `ccache` is available it is used for
the large generated translation unit, unless `CC` is explicitly set.

## Regenerating

Not possible from this tree, by design. A new compiler must be written in Zen, compiled by stage-0,
and then made to emit its own seed — at which point `zenc.gen.c` is replaced and this directory stops
being frozen. Until then, treat stage-0 as a binary blob: do not edit the generated C.
