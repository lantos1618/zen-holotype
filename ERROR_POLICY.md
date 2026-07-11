# Zen Result And Error Policy

This is the current stdlib policy for fallible work. It documents what the code
does today, not the final checker-enforced memory model.

## Rule

Allocation, file I/O, parsing, and FFI sentinel checks should expose a value path
when the caller can reasonably recover:

```zen
Result<T, E>: Ok(T) | Err(E)
Opt<T>: Some(T) | None
```

The caller handles the value with `.match`. There are no exceptions and no
unwinding. **`panic` is abort-only** — it is reserved for invariants that cannot
sensibly continue (it prints `zen: panic: <msg>` and aborts; it is not a
recoverable control-flow path). Everything the caller can reasonably recover from
is a `Result`/`Opt` value, propagated with `.or_return()` and branched with
`.match`.

The current runtime/capability source of truth is
[`docs/runtime-design.md`](docs/runtime-design.md). The print/IO spine behind `Writer` returns
`Result<i64, IoError>` (Sys phase 2, shipped — see
[`docs/sys-phase2-print-writer.md`](docs/sys-phase2-print-writer.md)). Ambient `println`/`print`
remain best-effort (`i64`) during the callsite migration.

## Runtime safety (trustworthy execution)

A program that passes `zenc check` must not silently corrupt at runtime. The C backend emits guards so
that undefined behaviour becomes a deterministic, message-bearing `panic` (`zen: panic: <message>` +
newline on stderr, then `abort`; `std.core.result.panic` and the `expect` combinators use the same
framing), never a SIGFPE or a garbage read:

| Operation | Policy | Mechanism |
|-----------|--------|-----------|
| integer `/` and `%` | **panic** on divide-by-zero and on the `INT_MIN / -1` overflow | `zen__divz`/`zen__modz` helpers (emitted preamble); integer operands only — `_Generic` keeps float `x/0.0 == inf` with native C semantics |
| slice index `xs[i]` (read and write) | **panic** on `i < 0 || i >= len` | `zen__idx(z, i, esz)` helper bounds-checks against the slice's `.len` |
| signed integer overflow (`+ - *`) | **documented: wraps** (two's complement), never UB | compiled with `-fwrapv`, so the compiler cannot miscompile on an assumed-no-overflow basis |

Guards live in the emitted C preamble (`genc_emit.zen` `genModuleIn`) and so apply to every built
program and to the compiler itself.

## Naming

| Shape | Meaning |
|---|---|
| `x` / `x_in` | Fast path. May return raw sentinels or assume allocation succeeds. |
| `try_x` / `try_x_in` | Fallible value path. Returns `Result<..., E>`. |
| `*_in` | Caller provides the allocator explicitly. |
| no `_in` | Non-allocating, ambient-resource, or namespace-friendly short name. Allocating std APIs should still show the allocator in the signature unless a table row explicitly says otherwise. |

`std.mem.alloc` is the boundary between raw C allocation and allocator-shaped
Zen APIs. Raw `malloc`/`realloc`/`free` remain exported for bootstrap and FFI
floor code, but library APIs that allocate should prefer an explicit allocator
parameter plus a `try_*` variant when failure is recoverable.
The primitive-boundary tests enforce this shape: direct raw allocation calls are
allowed only in `std.mem.alloc`, `std.mem.raw`, and the compiler bootstrap
allocation shim.

## Current Std Surface

| Area | Fast path | Fallible path | Notes |
|---|---|---|---|
| `std.mem.raw` | `alloc`, `zeroed`, `copy`, `release`, `of` | `try_alloc`, `try_zeroed`, `try_of` | Raw heap helpers stay the FFI/bootstrap floor, but nullable allocation can now be lifted into `Result` when callers want a value-shaped failure path. |
| `std.mem.alloc` | `a.acquire`, `a.resize`, `a.release`, namespace-bound `alloc.default` | `try_acquire`, `try_resize`, `try_malloc`, `try_realloc` | `try_*` lifts null pointers into `Result` through `ok_ptr`; heap construction itself is infallible because `Heap` is stateless. |
| `std.mem.arena` | `Arena.free`, `Arena.free_in`, `Arena.reset` (non-allocating) | `make_in` returns `Result<Arena, IoError>` directly — no `try_*` doubling | Arena backing storage comes from a caller allocator; the type-unique constructor name avoids colliding with other memory modules. |
| `std.mem.own/rc/arc` | `release_in`, `drop_in` (non-allocating) | `new_in` returns `Result` directly — no `try_*` doubling | Ownership blocks use caller-provided allocators on construction and release; default-heap `new`/`release`/`drop` wrappers are intentionally absent. |
| `std.mem.trace` | `set_kid`, `child` (non-allocating) | `tracked`/`tracked_in`, `root`/`root_in`, `collect`/`collect_in` return `Result` directly — no `try_*` doubling | Cycle-tracing blocks, root registration, and scratch reclamation use the caller allocator; block, root-list, and collection scratch allocation failure stays in the value flow. |
| `std.core.slice` | non-allocating views/searches | `buf`, `dup`, `dupx`, `node`, `concat`, `reverse` (plus `_in` aliases) return `Result` directly — no `try_*` doubling | Slice storage helpers are allocator-first; the short names take the caller allocator and no default-heap wrappers are exported. |
| `std.text.str` | borrowed `find`, `contains`, `at`, `parse_int` (sentinel) | `dup_bytes`/`dup_bytes_in`, `substr`/`substr_in` return `Result` directly — no `try_*` doubling; `try_parse_int`/`find_opt` are the value-shaped parse/search paths | Borrowed text search/parse does not allocate; owned byte copies and substrings take the caller allocator, with no default-heap wrappers. |
| `std.text.string` | receiver `free_in` (non-allocating) | `init`, `new_in`, receiver `push_in`/`append_in`/`finish_in` return `Result` directly — no `try_*` doubling | `String` construction is allocator-explicit; allocation failure is a value at every growth point. |
| `std.text.num` | `parse_i64_checked`, `parse_f64`, `parse_i64_radix` (non-allocating parses) | `integer`/`integer_in`, `uinteger`/`uinteger_in`, `float`/`float_in` return `Result<String, IoError>` directly — no `try_*` doubling | Numeric formatting allocates owned `String` buffers through the caller allocator; no default-heap wrappers are exported. |
| `std.text.fmt` | `print`, `println`, direct numeric writers | `write_int_in`, `write_float_in` return `Result` directly — no `try_*` doubling | Default numeric printing streams bytes directly and does not allocate; allocator-backed helpers remain available when callers want the owned-String formatting path. |
| `std.collections` | `get`/`has`/`len`/`view`/`free` (non-allocating) | `Vec.push`/`vec.of`, `Map.put`/`maps.of`, `IntMap.put`/`maps.int_of`, `iter.map_in`/`iter.filter_in` return `Result` directly — no `try_*` doubling | Vec, Map, IntMap, and allocating iter helpers surface allocation failure as a value; on `.Err` existing contents are preserved. Namespace binds let collection modules export natural constructor names. |
| `std.concurrent.actor` | `tell`, `run`, `free` (non-allocating sends, drains, teardown) | `cell`, `engine`, `spawn`, `cell.reply`, `request`, `ask` — every allocating entry point returns `Result` directly; no `try_*` doubling | Actor queues, handles, state blocks, and reply channels allocate through the caller allocator; draining checkpoints internally and does not require the allocator to double as a runtime; constructors release partially acquired storage before returning `.Err`. |
| `std.concurrent.coroutine/sched` | `destroy`, `destroy_in` (non-allocating teardown) | `spawn`/`spawn_in` and scheduler `run`/`run_in` return `Result` directly — no `try_*` doubling | Coroutine stack, context, link context, state blocks, and scheduler flag buffers allocate through the caller allocator; `spawn*` releases any partial stack/context allocation before returning `.Err`, and `run*` returns `.Err` before resuming tasks when flag allocation fails. |
| `std.concurrent.cown` | `Buf.free` (non-allocating) | `cown.buf`, `cown.file`, `cown.new_in` return `Result` directly — no `try_*` doubling | Buffers allocate through the caller allocator; allocation failure is a value. File wrappers convert `open` failure into `IoError` and close the descriptor if wrapping it in `Own<File>` fails. |
| `std.io` | POSIX descriptor calls and `file.shell` | `file.contents`, `file.contents_in`, `file.save` | File helpers convert open/read/write failure into `IoError`. Raw descriptor calls stay low-level. |
| `std.internal.resolve` | `module_graph`/`module_graph_in` (fail-fast graph assembly via explicit `.expect`) | `import_edges`, `provided_symbols`/`provided_symbols_in`, `symbol_key_in` return `Result` directly — no `try_*` doubling | Scanner-only import edges can use any allocator. Parser-backed symbol/graph APIs still need `Malloc` scratch for parser boundary checks, but kept result slices and normalized strings can be backed by a caller allocator. |

## Test Requirements

Each area should have tests for the value path and the fast path where both
exist:

- `std.mem`: raw/allocator null sentinels become `.Err`; arena, ownership, and trace constructors expose `Result` paths; ownership/trace fast paths route through explicit allocators.
- `std.core.slice`: fallible buffer, copy, node, and concat helpers return `Result`.
- `std.text`: allocation failure, parse failure, and numeric-formatting allocation failure are matched as values.
- `std.collections`: Vec/Map fallible allocation preserves existing values on failure; iter map/filter allocation failure returns `.Err`.
- `std.concurrent.actor`: actor cell, stateful actor spawn, and cell-scoped reply allocation return `Result`, and partial allocation failure releases already acquired storage.
- `std.concurrent.coroutine/sched`: failed `spawn` returns `.Err` and releases any stack/context blocks already acquired; failed `run` returns `.Err` before resuming any coroutine.
- `std.internal.resolve`: scanner-only import-edge loading works with heap and arena allocators, and `import_edges` reports edge slice, module-string, and alias-string allocation failure as `.Err`.
- `std.concurrent.cown`: buffer allocation failure returns `.Err`, and file descriptor wrapping closes the descriptor on allocation failure.
- `std.io`: missing files, denied writes, successful writes, and successful reads
  return `Result` values.

The long-term goal is to move this from convention to checker-backed effects and
ownership rules. Until then, this policy is the contract std modules should
follow when adding new APIs.
