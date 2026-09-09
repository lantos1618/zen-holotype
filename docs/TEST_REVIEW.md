# Test consolidation review

The starting corpus has 1,178 collected cases (1,177 active and one deferred).
A token-level scan, excluding comments but including expectations, exit codes,
stderr, diagnostic counts, stage, stdin, argv, and environment, found no exact
duplicates. This does not prove every case is necessary; it rules out deleting
identical programs without inspecting their inputs and assertions.

## Consolidated cases

| Removed smoke test | Retained coverage |
| --- | --- |
| `std/loop_over_range_with_index` | `loop-basic/index_and_value_differ_when_the_walk_is_not_zero_based` already runs the identical `Range(10, 13)` case, plus arrays and wide signed Vec values. |
| `std/loop_over_vec` | `loop-basic/vec_walk_hands_out_insertion_order_elements` already covers unindexed strings; its indexed string pass is now retained there alongside wide signed values and pass counts. |
| `std/string_add_appends` | `string-basic/format_and_raw_adds_share_one_buffer` retains raw/formatted appends, byte counts, and now a mixed string/integer format after raw appends. |

These changes eliminate three separate compiler/C/link/process invocations.
The new AST query regression tests an actual changed boundary: computed fields,
method bodies, required hooks, and absent members must remain distinct.

## Deliberately retained

- Four `env/args_*` programs have identical tokens but different argv/environment
  and assert missing fields, invalid numbers, surplus positionals, and unknown
  flags. They protect different diagnostics.
- Vector growth through eight and sixteen elements is not identical coverage:
  one checks range traversal; the other checks indexed access and pointer
  stability across allocator growth. Sanitizer scripts also consume the former.
- String equality tests separately cover length asymmetry/empty strings,
  distinct addresses/slices, NUL bytes, and views across growth.
- Small must-fail programs isolate diagnostic positions and counts. Combining
  independent invalid programs can hide later failures behind the first error.
- Actor refusal, lifetime, and flow-control tests protect asynchronous behavior;
  a short program is not evidence that its interleaving is trivial.

## Future pruning rule

Remove a case when its runtime inputs, semantic/code-generation path, and
assertions are covered elsewhere. Record the surviving case and move any unique
assertion before deleting the old fixture and sidecars. Do not introduce a new
parameterization framework just to deduplicate four short entry programs.
Runtime and failure evidence should guide further pruning, not a target count.
