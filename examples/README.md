# Zen examples

Eleven examples run through the C path; `dom_demo.zen` is browser/JavaScript-only.

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
| `strings_demo.zen` | String ownership in depth: borrow vs copy, aliasing, who frees what. |

Run any of them as `./zen run examples/<name>.zen`.

## Unix filters

| Example | Run |
|---|---|
| `stdin_echo.zen` | `printf 'hello\nworld\n' \| ./zen run examples/stdin_echo.zen` |
| `wordfreq.zen` | `printf 'the cat sat on the mat the cat\n' \| ./zen run examples/wordfreq.zen` |
| `jq.zen` | `./zen run examples/jq.zen '.a.b[0]' file.json` (or pipe JSON on stdin) |
| `textproc.zen` | `./zen run examples/textproc.zen grep cat FILE` (also `re PAT FILE`, or bare for `wc`) |

`wordfreq.zen` uses `HMap<string_view, i64>` to count input words.

`jq.zen` is a mini-`jq`: `std.format.json` parses the document, a `.a.b[0]` path selects a node, and
`json.pretty` renders it; all failures (missing file, bad JSON, bad path) are clean messages with a
non-zero exit, never a crash.

`textproc.zen` is `wc` + `grep`-lite: `wc` counts the raw bytes from `contents_bytes`/`read_all_bytes`
(so an embedded NUL is counted, not treated as end-of-input), `grep`/`re` search with `std.text.str`
and `std.text.regex`, and matching lines go out through a `std.io.bufwriter` sink.

## Network

| Example | Run |
|---|---|
| `http_tool.zen` | `./zen run examples/http_tool.zen -i http://127.0.0.1:8099/` |

`http_tool.zen` is a curl-lite: `std.net.http.http_get` fetches a URL in one call, and the body is
written from `body_bytes` so binary payloads survive. The host must be a dotted-quad or `localhost`
(there is no DNS resolver), and `https://` is rejected (there is no TLS).

## Concurrency

| Example | Model | Run |
|---|---|---|
| `actor_demo.zen` | Cooperative typed actor; send/request drains inline on the caller. | `./zen run examples/actor_demo.zen` |
| `pool_actor_demo.zen` | Parallel typed actors over OS workers with a concrete trampoline. | `./zen run examples/pool_actor_demo.zen` |
| `http_actor_demo.zen` | `std.net.http_actor`'s ready-made client actor: send it a URL, receive the reply as a message. | `./zen run examples/http_actor_demo.zen` |

The two actor examples intentionally expose the current split API; see
[../docs/STATUS.md](../docs/STATUS.md#important-current-limits-and-defects).

## Browser JavaScript

`dom_demo.zen` lowers `std.web.dom` calls to browser DOM APIs. It is not a C/Node console program:

```sh
./zen emit-js examples/dom_demo.zen > /tmp/dom-demo.js
```

Load the emitted script in a browser page to exercise `document`, element creation, text content,
append, and event-listener lowering. Running it under `node` fails with `ReferenceError: document is
not defined` — the lowering is right, the host is not a browser. `./zen build` and `./zen run` refuse
it up front with `error[c-target]`: no C host defines `document`, so there is nothing to link.
