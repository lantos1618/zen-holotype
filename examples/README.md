# Zen examples

Runnable, self-contained Zen programs. Each one compiles and runs with the
self-hosted compiler and exits 0. Build `zenc` first (`make -f bootstrap/Makefile zenc`),
then run any example with:

```
./zenc run examples/<name>.zen
```

## Start here

| Example | What it shows | Run |
| --- | --- | --- |
| `hello.zen` | The smallest real program: import, print, exit code. | `./zenc run examples/hello.zen` |
| `tour.zen` | One-file tour of Zen's working surface. | `./zenc run examples/tour.zen` |

## Reading input (unix filters)

These read **stdin**, so pipe input in:

| Example | What it shows | Run |
| --- | --- | --- |
| `stdin_echo.zen` | Read stdin line by line; number + upper-case each line. | `printf 'hello\nworld\n' \| ./zenc run examples/stdin_echo.zen` |
| `wordfreq.zen` | stdin → split into words → count in an `HMap<str, i64>` → print. | `printf 'the cat sat on the mat the cat\n' \| ./zenc run examples/wordfreq.zen` |

Expected output:

```
$ printf 'hello\nworld\n' | ./zenc run examples/stdin_echo.zen
1: HELLO
2: WORLD

$ printf 'the cat sat on the mat the cat\n' | ./zenc run examples/wordfreq.zen
the: 3
cat: 2
sat: 1
on: 1
mat: 1
5 distinct words
```

## Data & collections

| Example | What it shows | Run |
| --- | --- | --- |
| `stats.zen` | List statistics over a `Vec<i32>`. | `./zenc run examples/stats.zen` |
| `json_demo.zen` | Build and print JSON with `std.json`. | `./zenc run examples/json_demo.zen` |
| `str_ops_demo.zen` | String ops: join/replace/to_upper/to_lower/repeat/pad/trim. | `./zenc run examples/str_ops_demo.zen` |

## Types, traits, and state

| Example | What it shows | Run |
| --- | --- | --- |
| `shapes.zen` | A trait with two impls, dispatched by receiver type (UFCS). | `./zenc run examples/shapes.zen` |
| `store_demo.zen` | A Redux-style store with a pure reducer. | `./zenc run examples/store_demo.zen` |

## Concurrency

| Example | What it shows | Run |
| --- | --- | --- |
| `actor_demo.zen` | Cooperative typed actor: `send` + `request` drained inline on the caller thread. | `./zenc run examples/actor_demo.zen` |
| `pool_actor_demo.zen` | Parallel typed actors on the pool (concrete trampoline + workers). | `./zenc run examples/pool_actor_demo.zen` |

Expected output:

```
$ ./zenc run examples/actor_demo.zen
after alice joined:   online=1 posted=0
after bob + a message: online=2 posted=1
ok

$ ./zenc run examples/pool_actor_demo.zen
total=1000
ok
```
