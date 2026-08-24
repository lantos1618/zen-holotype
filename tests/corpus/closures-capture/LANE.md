tests/corpus/closures-capture/a_mutation_before_defer_is_invisible -- fill_record copies at registration, not block exit; reading the frame slot at thunk time instead prints 99
tests/corpus/closures-capture/b_two_writers_one_snapshot_each -- one shared record cell for two defers (or a single fill-at-exit) makes both prints agree; per-registration fields give 6 then 50
tests/corpus/closures-capture/c_byref_param_capture_aliases_the_caller -- ref_field emits `T *` for a captured `::` param; flipping it to by-value (declarator) prints 5 instead of 2505
tests/corpus/closures-capture/d_capture_walk_descends_nested_bodies -- captures() stops recursing into nested blocks / lambdas / match arms and the record loses `n`; four reads in four shapes all go wrong
tests/corpus/closures-capture/e_shadowing_bind_is_not_a_capture -- write_unpack reuses the record slot for the body's own `v ::= 999` bind instead of fresh storage: shadow prints 22-side values or main's v moves
tests/corpus/closures-capture/f_loop_body_accumulates_through_a_captured_local -- loop-body store into an outer binding lowered as declare-fresh-per-pass: sum prints 16 (last term) not 30
tests/corpus/closures-capture/g_inner_block_snapshot_outer_frame -- inner block registers on the OUTER record or shares its cell: inner/outer prints collapse to one value; live-frame read makes both say 7
tests/corpus/closures-capture/h_lambda_argument_reads_the_live_binding -- run_lambda skips enter_frame(cl.floor) so the inlined lambda reads a stale copy: second call prints 45 again, deferred/live lines converge

NOTES ON WHAT THE PROBING FOUND

1. Locally bound closures cannot be called directly:
       bump = () () { n = n + 5; }
   does not even parse (`expected expression` after the return type --
   `lambda_ahead` refuses a `(` return type in expression position), and
   with the ret type omitted sema accepts it but codegen says "cannot
   resolve `bump`". A closure must flow through a function-typed
   parameter (`apply((x: i64) i64 { .. }, ..)`) to be called. Every test
   here is written through that shape. Whether "a function-typed local
   that is never callable" is intended is a language question, not a
   codegen bug I could pin from stdout alone.

2. `str + str` is rejected by cc, not by zen: `tag = tag + "b";` emits C
   with binary `+` on two zg_str structs ("invalid operands"). Zen has no
   string concatenation method visible in std/text, so this may just be
   unsupported source, but the failure lands in the C compiler rather
   than as a Zen diagnostic -- worth a look.

3. An untyped integer literal binds i64, so `big ::= 18446744073709551615`
   silently becomes -1 inside a deferred print while `body` prints it via
   a u64-typed slot correctly... actually: `big ::= <u64 max>` prints -1
   in BOTH places; only `big: u64 ::= ...` is correct. Untyped literal
   defaults to signed i64 and wraps. Plausible-by-design (literals settle
   i64), recording it here because a capture test tripped over it first.

TESTS: 8
