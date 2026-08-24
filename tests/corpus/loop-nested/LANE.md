# tests/corpus/loop-nested

Nested loops, and which loop a break (or next) leaves. One program per
discriminating question; each `.expected` is the exact stdout.

| path | what one-line compiler change breaks it |
|---|---|
| `nested_loops_break_inner_only/` | bind the inner body's handle to the enclosing loop's depth instead of its own — outer stops after one pass |
| `break_from_inner_body_stops_outer/` | rebind every handle to the nearest loop at the exit site — the outer break stops the inner loop, "done" never prints, remaining passes run |
| `nested_folds_break_carries_to_right_loop/` | give the nested folds one shared result slot instead of one per loop — half one prints four "inner ran through" lines, half two's "outer sum" answers with the inner break's value (3) |
| `while_cond_nested_breaks_inner/` | lower break as "jump to the condition test" or conflate the cond form's guard with its break — an always-true guard never lets go, output never reaches `outer 0`'s tail |
| `try_inside_nested_loop_returns_past_both/` | reuse the loop-exit jump with a wrong frame count for `.try()` inside a nest — Err stops at an inner loop, "caught the no-hit" moves past 200 lines or never prints |
| `inner_break_value_not_outer_type/` | type the carried value with the wrong loop's element type or truncate it through the wrong frame's slot — 255 becomes 0 or -1 through i8; 123456789 comes back as 21 through a byte-wide slot |
| `three_deep_middle_break/` | resolve handles only as "nearest" or "outermost" — a three-deep middle handle lands on the wrong one of the three; "inner after"/"middle done" counts move |
| `next_in_inner_break_in_outer_same_nest/` | resolve handles once per BODY closure instead of per handle — two live handles in one body collapse, either `next` jumps to the outer loop (inner 2 vanishes) or `break` stops the inner one ("unreachable tail" prints) |

## What the area pins, in one line

The LoopHandle is "the enclosing loop, as a value": every test here holds
two or more loops in scope at once and makes the program say WHICH one
each exit left, by count and position rather than by any flag.

## Compiler bugs found while writing this lane

None. Every program compiled and printed the answer the semantics claim
on the first run that compiled; nothing had to be excluded.

Two near misses worth recording for whoever owns lowering:

1. The cond-form overload is spelled `loop(() bool { true }, (h) { ... })`
   — a bare `(() true)` cond expression does not parse as the same call,
   and `loop` written as a member-style `.loop` on it is not resolved
   against the free-function overloads. Not a bug: the signature table in
   src/std/core/loop/loop_iter.zen says the family is called, not messaged.
   Recorded because the error messages along that path ("unclosed `(`")
   point at the wrong thing.
2. `println` cannot print a user error-set value (`codegen does not lower
   this yet`), so try_inside_nested_loop_returns_past_both matches on the
   Res and prints a fixed string instead of the error itself.

TESTS: 8
