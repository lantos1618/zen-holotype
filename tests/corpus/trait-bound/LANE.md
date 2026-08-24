LANE: trait-bound -- a bound that must select an implementation

each_type_answers_with_its_own_impl
    -- gen_c emitting one shared symbol for all of a bound's impls (or sema
       dispatching "first impl in the table") prints 37 for every line instead
       of 37 / -9 / 12005.

default_member_inherits_per_impl
    -- lowering a bound's `::=` default once per impl instead of per
       instantiation, or letting Furnace's `label` override leak into
       Iceberg, swaps lines 1-2 and 3-4 ("plain/hot/5/3").

computed_fields_recompute_and_own_storage_wins
    -- freezing impl-supplied field expressions at construction prints 7 and
       280 again after `a.side = 5` instead of 16 and 640; letting the impl's
       `width` shadow Square's own storage turns line 3 into 2.

bound_names_a_generic_trait
    -- substituting the generic trait's T with the RECEIVER'S parameter (or
       with nothing) makes `at` answer the wrong type or leaves it unresolved;
       a start/end mix-up shifts every line off by one pass.

impl_on_a_generic_type_satisfies_the_bound
    -- matching bounds by trait NAME rather than full instantiation rejects
       Vec<i32> against Range<i32>, or accepts anything and answers 0.

bound_survives_a_generic_calling_a_generic
    -- dropping the type parameters when a generic body calls another generic
       (the std.core.eq is_in defect) makes the inner call fall back to
       first-emitted-impl: line 2 answers 95 instead of -39.

method_bound_from_a_third_module
    -- resolving the method in the CALLING module's table rather than the
       declaring module's misses Wheel's impl entirely (`no such member`);
       reading `read` as a free function loses the +3 and line 1 prints 24.

one_parameter_two_bounds_see_both_members
    -- unioning two bounds' member sets badly hides `mass` behind `read`
       (compile error) or lets one overwrite the other; either way 30503
       becomes 30000 or 503 alone.

COMPILER BUGS FOUND (programs under /tmp/zproto/, kept out of the corpus on
purpose -- do not encode wrong answers as expectations):

1. TWO IMPLS SUPPLYING THE SAME METHOD NAME: WHICHEVER IMPL IS DECLARED
   FIRST SERVES EVERY BOUND. DESIGN.md: "When two impls declare the same
   name, the bound in scope selects which is in view" -- that holds for
   FIELDS (sema/impl_collision_bound_in_scope passes via supply_memo) but
   not for METHODS:

       Tile.impl(Boxy,   { score = (self) { self.side * 100 } })
       Tile.impl(Framed, { score = (self) { self.side + 7 } })
       <T: Boxy>(t)   => t.score()   // prints 300 -- right only by luck
       <T: Framed>(t) => t.score()   // prints 300 -- file order won

   Swapping the two impl declarations swaps which answer both callers get.
   Root cause chain: sema_call.zen reachable_call/method_call resolves on
   signature fit only and never consults Checker.bounds or supply_memo
   (sema_member.zen select() does exactly that for fields); gen_c_member
   .zen pick_member/member_that_fits mirrors the same fit-only rule; and
   gen_c_impl.zen mangles the supplied method to target+name+signature --
   no trace of WHICH impl supplied it -- so both bodies emit under ONE C
   symbol and file order decides whose body it is. The no-bound spelling
   also compiles silently (must-fail/sema/impl_collision_no_bound covers
   fields only), so there is no gate anywhere on this for methods. Probe:
   /tmp/zproto/method_collision.zen (both lines 300), arity variant
   /tmp/zproto/method_collision_arity.zen (works -- different symbols),
   no-bound variant /tmp/zproto/method_collision_nobound.zen.

2. A FOLD OVER A BOUND WHOSE RANGE AN IMPL SUPPLIES IS REFUSED IN CODEGEN,
   NOT IN SEMA. `r.loop(0, (h,i,v,acc) ..)` over `<R: Range<i32>>` reaches
   cc-green sema and then dies with "codegen does not lower this yet: a
   fold over a range whose bounds an impl supplies"
   (/tmp/zproto/t7*.zen history). std.core.range says "a bound
   monomorphises instead -- `at` is a direct call", so the plain loop
   works (test impl_on_a_generic_type_satisfies_the_bound pins it) but the
   fold is a hole the compiler only names at the backend.

TESTS: 8
