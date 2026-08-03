# Zen

A reset. This tree is the frozen stage-0 compiler and the std floor it needs — nothing else.

## Why

The compiler tripled in five weeks (14.5k → 44.9k LOC, 12 → 73 files) while the language did not
grow. The July decomposition split god files without breaking dependencies: `src/compiler/validate/`
was eight files with eleven mutual import cycles, only linkable because `--build-self` concatenates
every compiler source into one flat translation unit. That is not a module system, it is a build flag
hiding a cycle. The full history is on `main`.

## What is here

| Path | Role |
|---|---|
| `bootstrap/zenc.gen.c` | The frozen stage-0 compiler: 4.4 MB of generated C. The only thing that can compile Zen. |
| `bootstrap/zenrt.{c,h}` | Hand-written C process, OS, thread, and panic floor. |
| `src/std/` | 13 files, 1,892 LOC — the std floor stage-0 reads from disk. |

## Build

```sh
make          # cc bootstrap/zenc.gen.c -> ./zen
./zen run f.zen
```

Stage-0 is a binary artifact with no source in this tree. It cannot be regenerated here; that is the
point. `make regen`, the harness, and every other target are gone with the sources they consumed.
`bootstrap/sources.txt` is kept as provenance — it lists the files stage-0 was generated from, all of
which now live only on `main`.

## The rule for what comes back

A split is real only if the new files form a DAG. Anything that reintroduces a mutual import cycle,
or that needs whole-program concatenation to link, is not a module boundary.

Recover any deleted file with `git checkout main -- <path>`.
