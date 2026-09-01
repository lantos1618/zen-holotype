// tests/corpus/ownership-consume -- the `consume` lane.
//
// one line per test: path -- what one-line compiler change breaks it.
// findings (suspected bugs) follow, each with a program that shows it.

consume_chain_drops_once/ -- in gen_c_own.zen, make release_binding clear every DropEntry instead of only the moved name's: three drops print instead of one.

consume_swaps_two_values/ -- in gen_c_expr.zen, lower_consume: emit a reference rename (alias) instead of copying bytes and clearing the source's live flag: the body line prints "a b" un-swapped.

consume_clears_only_moved_flag/ -- same clear-site as above but the opposite break: clear ALL entries on any consume and "drop b" doubles; clear none and m double-frees. Also broken by dropping per-binding rather than per-live-value at scope exit (drops come out c, b, a or with duplicates).

consume_at_call_site_round_trips/ -- in gen_c_stmt.zen, declare_local: register parameters for drop like bindings ("note_drop" in bind_param): the returned value drops twice (caller flag still live + callee param drop). The inverse break -- stop clearing the caller's flag in lower_consume -- leaks it instead.

consume_breaks_with_its_value/ -- in gen_c_loop.zen, close_pass/run_body: emit the per-pass drops AFTER spilling the break value into the result temp: "drop 22" moves before "kept 22". Or: bind h.break's value to the loop index/item instead of the consumed operand: kept prints 2 (the counter) instead of 22.

consume_in_every_arm_joins_alive/ -- in sema_join.zen/sema_own.zen arm-join: treat arms as sequential statements (join = intersection of live sets): second consume f rejected as double move. Backend half: drop the arm-local t/u inside its own block before the join reads it: "after v" prints garbage or crashes.

consume_of_handle_still_works/ -- in gen_c_own.zen note_drop: treat Alloc as Drop (register h): arena freed while v's data lives inside it. Sema half: exempt non-Drop targets from use-after-move and `alloc` stays usable after the move, which contradicts must-fail/own/use_after_send.zen's premise.

short_circuit_keeps_an_unmoved_value/ -- a skipped `consume` must not clear the source binding's live flag before the short-circuit branch runs.

// ---------------------------------------------------------------
// FINDINGS -- things I believe are COMPILER BUGS, each with the
// program that shows it. None is encoded as an expectation above;
// every test avoids the affected shapes.
//
// All four share a shape: SEMA models the situation correctly and
// GEN_C never emits the matching code, so the failure is silent --
// exit 0, plausible stdout, no diagnostic anywhere.
//
// 1. OVERWRITE LOSES THE DISPLACED VALUE'S DROP.
//
//      m ::= Noisy(env: env, tag: "m");
//      v = Noisy(env: env, tag: "v");
//      m = consume v;
//      println("body {}", m.tag);   // body v
//                                   // drop v        <- "drop m" NEVER RUNS
//
//    assign_target (gen_c_stmt.zen) emits only the store; declare_local
//    registers the drop once at declaration and nothing re-arms or
//    fires it when a new value lands on the binding. sema's own_bind/
//    revive explicitly models writes as revival ("A write fills the
//    hole"), so the checker side believes this is fine. An Arena, file
//    or lock held by the displaced value leaks at exit 0.
//    NOTE: ISSUES.md already records this for plain shadow-rebinding
//    (`x = Noisy(id: 1); x = Noisy(id: 2)`); these probes show
//    `x = consume y` loses it too, so the fix cannot be "drop at
//    rebind of a constructed RHS" alone.
//
// 2. CONSUME INTO A CALL ARGUMENT LEAKS WHEN THE CALLEE KEEPS IT.
//
//      retag = (env: Env, n :: Noisy) Noisy { ...fresh value... }
//      r = retag(env, consume s);   // s's flag cleared by lower_consume
//                                   // retag returns a NEW value
//      // "drop w" runs; "drop v" NEVER RUNS
//
//    Two halves combine: lower_consume clears the caller's live flag,
//    and bind_params/gen_c_decl never registers a drop for parameters
//    (gen_c_stmt.zen's own comment says "never a parameter", but that
//    sentence is about BORROWS -- a parameter that receives ownership
//    via consume is exactly the case that needs one). The callee frame
//    ends without destroying n. Fix shape: either register params of
//    Drop type for drop (callee-side destruction), or don't clear the
//    caller's flag until the call returns and prove the value left the
//    frame -- today it is neither.
//
// 3. A LOOP WHOSE BREAK VALUE IS A STRUCT COMPILES TO WRONG C.
//
//      loop((h) { ... h.break(f) ... }).match({ Ok(b) => .. })   // f: Buf
//
//    lower_settled (gen_c_loop.zen) forces the loop's Res<T> element to
//    usize ("a range that supplies no `at` walks its own index space"),
//    but the while-form loop has no range and no element: sema leaves T
//    open, the backend interns Res<usize>, and h.break(f) initialises
//    the Ok payload from a Buf -- cc rejects:
//      error: incompatible types when initializing type 'long unsigned int'
//             using type 'zu_t2_4main3Buf'
//    Any non-primitive break value hits it (str repro'd too; bool/f64/i32
//    work because they fit usize-ish slots). Worse, SEMA ALSO types the
//    Ok binder as usize for the RANGE forms (lower_settled's answer is
//    what settle_res hands back), so `Ok(b) => println("{}", b.id)` on a
//    Range loop is refused with "no `id` on `usize`" -- the break value
//    is unreachable through the type system there. My break test works
//    around both by breaking with an i32 field.
//
// 4. STRUCT FIELDS ARE NEVER DROPPED, EVEN FROM A TYPE WITH AN IMPL OF DROP.
//
//      p ::= Pair(left: Buf(..), right: Buf(..));  // Pair.impl(Drop) exists
//      // prints only "drop pair"; "drop 1"/"drop 2" NEVER RUN
//      // with NO Pair.impl(Drop), nothing drops at all
//
//    A Drop impl's body is whatever the user wrote; nothing composes
//    member drops into it, and an impl-less struct registers no drop at
//    all. So sema's partial-move diagnostic -- "p is partially moved, so
//    the drop has a hole: move the whole value or none of it"
//    (must-fail/own/partial_move_at_scope_exit.zen) -- describes a drop
//    that would not run even if p were whole. Field-level consume
//    (must-fail/own/consume_field_then_use.zen) is checked against a
//    fiction. Every Drop-holding struct in std (Vec holds alloc: Alloc
//    -- a handle, so benign TODAY) is one field away from leaking.

TESTS: 7
