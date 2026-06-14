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
unwinding. `panic` is reserved for invariants that cannot sensibly continue.

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
| `std.mem.arena` | `new_in`, `Arena.free`, `Arena.free_in` | `try_new_in` | Arena backing storage can come from a caller allocator; namespace binds let arena use allocator-explicit constructor names without colliding with other memory modules. |
| `std.mem.own/rc/arc` | `new_in`, `release_in`, `drop_in` | `try_new_in` | Ownership blocks use caller-provided allocators on construction and release; default-heap `new`/`try_new`/`release`/`drop` wrappers are intentionally absent. |
| `std.mem.trace` | `tracked_in`, `root_in`, `collect_in` | `try_tracked_in`, `try_tracked`, `try_root_in`, `try_root`, `try_collect_in`, `try_collect` | Cycle-tracing blocks, root registration, and scratch reclamation use the caller allocator; fallible variants keep block, root-list, and collection scratch allocation failure in the value flow. |
| `std.core.slice` | `buf`, `dup`, `dupx`, `node`, `concat` plus `_in` aliases | `try_buf`, `try_dup`, `try_dupx`, `try_node`, `try_concat` plus `_in` aliases | Slice storage helpers are allocator-first; the short names take the caller allocator and no default-heap wrappers are exported. |
| `std.text.str` | allocator-first `dup`, `dup_in`, `substr`, `substr_in`, plus `parse_int`, `find` | `try_dup`, `try_dup_in`, `try_substr`, `try_substr_in`, `try_parse_int`, `find_opt` | Borrowed text search/parse does not allocate; owned byte copies and substrings take the caller allocator, with no default-heap wrappers. |
| `std.text.string` | `new_in`, `init`, receiver `push_in`/`append_in`/`finish_in`/`free_in` methods | `try_new_in`, `try_init`, `try_push`, `try_append`, `try_finish`, plus receiver `try_*_in` methods | `String` construction is allocator-explicit; fallible variants keep allocation failure explicit. |
| `std.text.num` | allocator-first `integer`, `integer_in`, `float`, `float_in` | `try_integer`, `try_integer_in`, `try_float`, `try_float_in` | Numeric formatting allocates owned `String` buffers through the caller allocator; no default-heap wrappers are exported. |
| `std.text.fmt` | `print`, `println`, direct numeric writers, plus `write_int_in`, `write_float_in` | `try_write_int_in`, `try_write_float_in` | Default numeric printing streams bytes directly and does not allocate; allocator-backed helpers remain available when callers want the owned-String formatting path. |
| `std.collections` | `Vec.push`, `vec.of`, `Map.put`, `maps.of`, `iter.map_in`, `iter.filter_in` | `Vec.try_push`, `vec.try_of`, `Map.try_put`, `maps.try_of`, `iter.try_map_in`, `iter.try_filter_in` | Vec, Map, and allocating iter helpers keep fast allocator paths plus `Result` paths for recoverable allocation failure. Namespace binds let collection modules export natural constructor names. |
| `std.concurrent.actor` | `cell`, `engine`, `spawn`, `cell.reply` | `try_cell`, `try_engine`, `try_spawn`, `cell.try_reply` | Actor queues, handles, state blocks, and reply channels allocate through the caller allocator; draining checkpoints internally and does not require the allocator to double as a runtime; `try_*` variants release partially acquired storage before returning `.Err`. |
| `std.concurrent.coroutine/sched` | `spawn`, `spawn_in`, `destroy`, `destroy_in`, `run`, `run_in` | `try_spawn`, `try_spawn_in`, `try_run`, `try_run_in` | Coroutine stack, context, link context, state blocks, and scheduler flag buffers allocate through the caller allocator; `try_spawn*` releases any partial stack/context allocation before returning `.Err`, and `try_run*` returns `.Err` before resuming tasks when flag allocation fails. |
| `std.concurrent.cown` | `cown.buf`, `Buf.free` | `cown.try_buf`, `cown.file`, `cown.file_in` | Buffers allocate through the caller allocator; `try_buf` lifts allocation failure into `Result`. File wrappers convert `open` failure into `IoError` and close the descriptor if wrapping it in `Own<File>` fails. |
| `std.io` | POSIX descriptor calls and `file.shell` | `file.contents`, `file.contents_in`, `file.save` | File helpers convert open/read/write failure into `IoError`. Raw descriptor calls stay low-level. |
| `std.internal.resolve` | `import_edges`, `provided_symbols_in`, `module_graph_in` | `try_import_edges` | Scanner-only import edges can use any allocator and expose a fallible path. Parser-backed symbol/graph APIs still need `Malloc` scratch for parser boundary checks, but kept result slices and normalized strings can be backed by a caller allocator. |

## Test Requirements

Each area should have tests for the value path and the fast path where both
exist:

- `std.mem`: raw/allocator null sentinels become `.Err`; arena, ownership, and trace constructors expose `Result` paths; ownership/trace fast paths route through explicit allocators.
- `std.core.slice`: fallible buffer, copy, node, and concat helpers return `Result`.
- `std.text`: allocation failure, parse failure, and numeric-formatting allocation failure are matched as values.
- `std.collections`: Vec/Map fallible allocation preserves existing values on failure; iter map/filter allocation failure returns `.Err`.
- `std.concurrent.actor`: actor cell, stateful actor spawn, and cell-scoped reply allocation return `Result`, and partial allocation failure releases already acquired storage.
- `std.concurrent.coroutine/sched`: failed `try_spawn` returns `.Err` and releases any stack/context blocks already acquired; failed `try_run` returns `.Err` before resuming any coroutine.
- `std.internal.resolve`: scanner-only import-edge loading works with heap and arena allocators, and `try_import_edges` reports edge slice, module-string, and alias-string allocation failure.
- `std.concurrent.cown`: buffer allocation failure returns `.Err`, and file descriptor wrapping closes the descriptor on allocation failure.
- `std.io`: missing files, denied writes, successful writes, and successful reads
  return `Result` values.

The long-term goal is to move this from convention to checker-backed effects and
ownership rules. Until then, this policy is the contract std modules should
follow when adding new APIs.
