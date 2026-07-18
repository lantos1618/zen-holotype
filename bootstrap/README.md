# Bootstrap

The compiler is Zen source. This directory contains the generated artifacts and small target floors
needed to build it with a host C compiler and no Python.

| File | Role |
|---|---|
| `zenc.gen.c` | Committed C emitted from the compiler source graph plus `driver.zen`. |
| `zenrt.h` / `zenrt.c` | Hand-written C process, OS, thread, and panic-isolation floor. |
| `zenrt.js` | JavaScript runtime floor used by `emit-js`/the JS build target. |
| `sources.txt` | Graph/SCC-checked source order for self-regeneration. |
| `Makefile` | Build, regenerate, harness, and seed-merge helpers. |

There is no separate C driver. `driver.zen` is emitted into `zenc.gen.c` and supplies `zen_main`.

## Build

From the repository root:

```sh
make
```

or directly:

```sh
make -f bootstrap/Makefile zenc
```

The real output target is `./zenc`; an unchanged build is an mtime no-op. If `ccache` is available it
is used for the large generated translation unit, unless `CC` is explicitly set.

## Regenerate and prove the fixpoint

After changing `driver.zen`, `zen/compiler/*`, or a std module in `sources.txt`:

```sh
make regen
cp bootstrap/zenc.gen.c /tmp/zenc.fixpoint.c
make regen
cmp /tmp/zenc.fixpoint.c bootstrap/zenc.gen.c
```

`regen` writes a PID-specific temporary and replaces `zenc.gen.c` only when bytes changed. A second
run must be identical. The full harness also contains a fixpoint suite and verifies that
`sources.txt` agrees with the resolver graph order. `make docs-check` verifies the deliberate
seven-file documentation inventory and every local Markdown link.

Generated C is an artifact, not a merge authority. Register the local merge driver with
`make setup-git`; after resolving source changes, `make resolve-seed` regenerates and stages the seed.

See [../ARCHITECTURE.md](../ARCHITECTURE.md) for the pipeline and [../STATUS.md](../STATUS.md) for
current limits.
