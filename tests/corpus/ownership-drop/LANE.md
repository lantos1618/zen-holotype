tests/corpus/ownership-drop/reverse_order_over_drop_bindings_only/main.zen -- flipping `drop_range`'s `end - 1 - k` to `mark + k` (forward walk) prints drop 1 2 3; so does registering bindings in the list in reverse.
tests/corpus/ownership-drop/consume_clears_the_live_flag/main.zen -- deleting the flag write in `clear_if_named`/`release_binding` double-drops 1; dropping by value identity instead of live binding reorders g's drop to last.
tests/corpus/ownership-drop/inner_block_drops_at_its_own_brace/main.zen -- making `leave_block` skip `run_frame` for nested blocks (or hoisting all drops to function exit) moves the inner drops after "mid".
tests/corpus/ownership-drop/try_unwinds_frame_by_frame/main.zen -- hoisting defers out of per-frame `run_cleanup` into one global pass (all-defers-then-all-drops across frames) reorders to inner defer, outer defer, drop 2, drop 1; skipping unwind on `.try()` drops nothing before "propagated".
tests/corpus/ownership-drop/loop_bindings_drop_each_pass/main.zen -- not running the frame at a loop body's closing brace (drops hoisted to function exit) prints all three `iter` lines consecutively first; forward order within a pass prints drop 0 1 10 11 20 21.
tests/corpus/ownership-drop/break_unwinds_only_the_current_pass/main.zen -- skipping `unwind_to` at `h.break()` (leak) prints no drops for pass 1; unwinding every pass's leftovers instead of just the current frame double-drops 0 and 1.
tests/corpus/ownership-drop/arm_constructs_value_lives_to_scope_end/main.zen -- dropping an arm-constructed temporary when the arm ends (treating arms as owners) prints "drop 20" before "picked"; suppressing the binding registration for match-valued binds leaks it entirely.
tests/corpus/ownership-drop/statement_temporary_is_never_dropped/main.zen -- registering statement-position temporaries in the drop list (breaking "never a temporary") makes "drop 99" appear after "end"; any mis-ordering of the two real bindings shows up as 1 before 2.

COMPILER BUGS FOUND: none. Every program behaved per docs/DESIGN.md and
src/gen/gen_c/gen_c_own.zen (defers LIFO then drops reverse-declaration,
per-frame on every exit path, live-flag cleared at consume, bindings only).
One near-miss while writing expectations: a value moved into a later
binding drops under that binding's declaration position, not its origin's
-- correct per the law, easy to mis-expect.

TESTS: 8
