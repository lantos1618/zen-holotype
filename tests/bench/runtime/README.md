# Generated-program runtime measurements

Run from the repository root:

```sh
python3 tests/bench/runtime/run.py --zen ./zen \
  --out build/source_health/runtime --scale 4 --enforce-map-budget
```

For the aggregate deterministic gate, add `--quick --enforce-map-budget`.
Quick mode uses 64 and 256 elements, checks all five workloads, and takes one
sample after a warmup. It makes no elapsed-time assertion. The old stdlib fails
this invocation with 40 allocator calls at 64 elements (budget 22).

This local suite emits and builds **user programs**, then times their execution.
It records compiler emission and C compilation separately. Both implementations
use the selected `--cc -O2 -std=c11`, with no LTO. Sizes, checksums, allocator-call
counts, generated C/executable sizes, raw samples, and medians are JSON output.
One warmup precedes seven measurements; execution order alternates. Timings
include process startup and should be interpreted cautiously at small sizes.
Increase `--scale` for steadier observations. These are local measurements, not
a cross-machine performance promise. Keep generated output under ignored build/.

The five workloads exercise integer recurrence/control, growing Vec plus Map
insertion/reverse lookup, decimal String construction and byte traversal, stable
sorting of duplicate keys with input indices, and a generic capturing callback.
An independently calculated Python checksum must agree with every Zen and C
execution. Observable output prevents dead-code removal of the workload; native
optimization of the recurrence/callback is intentionally allowed.

The C programs implement equivalent results, not identical safety or allocation
policies. C Map/Vec preallocates because the input length is known, uses compact
slots, and does not preserve a dense map entry array. Zen grows its public
containers and preserves insertion order. C String uses snprintf, while Zen
uses its specialized decimal writer. C stable merge sort is recursive; Zen's
scratch merge sort is iterative. Therefore these ratios compare these complete
implementations, not an isolated language/backend tax. In particular, beating
snprintf does not establish a general String advantage. Integer and generic
callback cases offer the closest direct lowering comparison.

The counting allocator forwards actual library calls and counts raw/realloc
requests; it does not count bytes, process malloc calls, or peak live memory.
The counter's own setup is outside the observed calls. `--enforce-map-budget`
requires at most `3*ceil(log2(n))+4` calls: two geometrically grown value/entry
vectors and one allocation per geometrically grown slot table. This semantic
cost bound catches repeated growth when initializing a known-length table.
It deliberately does not gate noisy elapsed time. The old implementation fails
this bound (197 calls at 80,000 entries versus a budget of 55); the reserved-table
implementation uses 50. The corpus test also pins this allocation property at
small scale and is part of ordinary aggregate verification.

Remaining coverage includes collision-heavy/string-key maps, allocation failure
under pressure, large element copies, alternate allocators, floating point/SIMD,
I/O, actors/concurrency, prolonged memory retention, other C optimization levels,
and additional host architectures. Existing sort corpus tests additionally
check stability, comparison counts, and unchanged input on allocation failure.
