# tests/corpus/errors-variant

The error variant that arrives is the one that was raised. Every test
here raises an error, propagates it across at least one frame boundary,
and reads back WHICH error (member of the set, variant inside the
member, payload) came out -- because a propagation that mistags or raw-
copies compiles, runs, and prints plausible names.

| path | one-line compiler change that breaks it |
|---|---|
| err_runtime_pick_reads_back_by_name | tag every raised Err with member 0 of the callee's set -- both arms print "not found" |
| err_inner_variant_survives_a_hop | renumber the inner enum by declaration order on widening -- Corrupt(str) reads as Short(i32) |
| err_flipped_spelling_retag_with_payloads | copy the union tag instead of re-numbering across `A\|B` -> `B\|A` -- prints "miss 4005", not "hit 45" |
| err_widening_chain_keeps_member_and_payload | make strict widening a raw copy (no canonical re-number) -- C arrives reading as A |
| err_inferred_set_carries_both_members | collapse an inferred `_` set to its first-raised member when consuming with .try() -- B1("bee") becomes A1 |
| err_raise_inside_loop_exits_the_function | stop .try()'s non-local exit at the loop closure's frame -- main sees Ok(-1), not Over |
| err_ok_path_survives_the_same_hops | zero the Ok payload slot while rebuilding Res during a re-tagging hop -- 4000000000 arrives as 0 |
| err_std_write_error_keeps_its_variant | renumber the inner IoError enum when copying WriteError between frames -- Full reads as Closed/Invalid/Interrupted |

## Compiler bugs found while writing this lane (NOT encoded as expected
## output; programs that show them are quoted in the report, kept out of
## the corpus)

1. **`.try()` hops between two flipped spellings of a set containing a
   UNION-typed member copy the raw tag without re-numbering.** Minimal
   program (prints ALLOC; correct output is "closed"):

   ```
   WriteError = std.core
   S_a = WriteError | AllocError
   S_b = AllocError | WriteError

   raise = () Res<i32, S_a> { Err(S_a.WriteError(WriteError.IoError(IoError.Closed))).try(); Ok(-1); }
   top   = () Res<i32, S_b> { raise().try(); Ok(-2); }

   main = (env: Env) Res<i32, AllocError> {
       top().match({
           Ok(v) => println("ok {}", v),
           Err(e) => e.match({
               AllocError(_) => println("ALLOC"),
               WriteError(w) => w.match({
                   AllocError(_) => println("write-alloc"),
                   IoError(io)   => io.match({ Closed => println("closed"), Full => println("full"), Invalid => println("invalid"), Interrupted => println("interrupted") }),
               }),
           }),
       });
       Ok(0);
   }
   ```

   Same-order spellings (`S_c = WriteError | AllocError` on both sides)
   work; plain single-variant enums flip safely. The generated C shows
   the callee's Res returned unmodified: the tag written for S_a lands
   in S_b where it selects the other member. This silently converts an
   IoError into OutOfMemory at any real layer boundary whose sets spell
   their members differently.

2. **`zen` ACCEPTS `Err(<bare enum value>)` as the tail of a function
   declared to return a wider named union, then gen_c emits C that cc
   rejects.** Minimal program (zen accepts; cc: "incompatible types when
   initializing type 'int' using type 'zu_t2_..B'"):

   ```
   A = | AOnly
   B = | BOnly
   Set = B | A

   deep = () Res<i32, Set> { Err(B.BOnly); }

   main = (env: Env) Res<i32, AllocError> {
       deep().match({ Ok(v) => println("ok {}", v), _ => println("an error") });
       Ok(0);
   }
   ```

   The C builds `{ .zg_tag = Res.Err, .zg_data.Err = (zu_t_B){ ... } }`
   -- the whole enum struct stuffed into the union's int-sized member
   slot. Either sema should refuse (no implicit conversion) or gen_c
   must build the union member; today it does neither.

3. **Matching a STRUCTURAL (inline-spelled) union type is refused by
   sema as non-exhaustive even with one arm per member, and enum-level
   patterns against it generate C naming undeclared tags**
   (`zu_e1_4Fault' undeclared`). Named-alias unions match fine, so all
   corpus tests here name their sets. Program:

   ```
   Fault = Bad | Worse
   Snag  = Low | High
   either = (n: i32) Res<i32, Fault | Snag> {
       (n > 0).match({ true => Err(Fault.Worse), false => Err(Snag.High) })
   }
   main = (env: Env) Res<i32, AllocError> {
       either(1).match({
           Ok(v) => println("ok {}", v),
           Err(e) => e.match({ Fault(_) => println("fault"), Snag(_) => println("snag") }),
       });
       Ok(0);
   }
   ```
   -> "match is not exhaustive"; adding `_` instead reaches cc, which
   rejects the emitted `zu_e1_5Fault`.

TESTS: 8
