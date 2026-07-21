# Zen examples

Ten examples run through the C path; `dom_demo.zen` is browser/JavaScript-only.

Build once, then run a C example with:

```sh
make
./zen run examples/hello.zen
```

## Language and data

| Example | What it demonstrates |
|---|---|
| `hello.zen` | Minimal import, output, and exit code. |
| `tour.zen` | Compact tour of the working language surface. |
| `shapes.zen` | Records, a trait, implementations, and receiver dispatch. |
| `stats.zen` | Numeric work over `Vec<i32>`. |
| `str_ops_demo.zen` | Allocator-backed string operations. |
| `json_demo.zen` | Build and print JSON. |

Run any of them as `./zen run examples/<name>.zen`.

## Unix filters

| Example | Run |
|---|---|
| `stdin_echo.zen` | `printf 'hello\nworld\n' \| ./zen run examples/stdin_echo.zen` |
| `wordfreq.zen` | `printf 'the cat sat on the mat the cat\n' \| ./zen run examples/wordfreq.zen` |

`wordfreq.zen` uses `HMap<string_view, i64>` to count input words.

## Concurrency

| Example | Model | Run |
|---|---|---|
| `actor_demo.zen` | Cooperative typed actor; send/request drains inline on the caller. | `./zen run examples/actor_demo.zen` |
| `pool_actor_demo.zen` | Parallel typed actors over OS workers with a concrete trampoline. | `./zen run examples/pool_actor_demo.zen` |

The two actor examples intentionally expose the current split API; see
[../STATUS.md](../STATUS.md#important-current-limits-and-defects).

## Browser JavaScript

`dom_demo.zen` lowers `std.web.dom` calls to browser DOM APIs. It is not a C/Node console program:

```sh
./zen emit-js examples/dom_demo.zen > /tmp/dom-demo.js
```

Load the emitted script in a browser page to exercise `document`, element creation, text content,
append, and event-listener lowering.
