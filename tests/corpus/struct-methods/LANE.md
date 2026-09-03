# struct-methods

Tests for methods declared in a struct body vs free functions on the type --
one overload set reached through the dot, per DESIGN.md's UFCS rule.

All tests PASS against `./runzen.sh` as of this lane. One line per test:
path -- the one-line compiler change that breaks it.

- associated_fn_and_free_fn_keep_namespaces.zen -- file `make()` and
  `W.make()` in one flat candidate pool: bare call answers 42 (the W-
  building body) or `W.make()` answers 7 / a wrong-typed read.
- dot_and_direct_are_one_call/ -- resolve the imported-binding spelling of
  an exported UFCS function to a different symbol than the dot form (or to
  nothing): "direct 14" rejects or diverges from "dot 14".
- dot_dispatch_projects_the_field_first.zen -- emit the OUTER value as the
  receiver instead of re-basing onto `.inner`: reads Inner's field through
  B's layout and stops answering 12.
- free_fn_extends_the_method_at_another_arity.zen -- key the candidate
  table by NAME without arity: second `mix` overwrites the first, one line
  answers the other's body (5003/512 collapse).
- free_fn_first_param_bound/ -- match first parameters by DECLARED type
  only, so an impl of the bound (`Arena` impls `Alloc`) is not "the type":
  `alloc.boxed(7)` rejects with "no `boxed` on `Arena`".
- free_fn_is_a_dot_candidate_like_a_method.zen -- restrict dot candidates
  to struct-body members: `w.double()` rejects ("no `double` on `W`") even
  though `double(W)` exists beside it.
- free_fn_on_a_generic_instantiation.zen -- lose the type arguments on
  either side of the call (match the generic skeleton, or instantiate the
  callee against the wrong T): dot line rejects or mis-reads the i32 field.
- free_fn_reaches_every_receiver_shape.zen -- require a named local binding
  as receiver: whichever of temporary / match join / loop-closure parameter
  loses its receiver changes that line (18/10/7).
- free_fn_travels_to_a_prelude_primitive.zen -- special-case primitives as
  builtin C types with no member table: `n.halve()` rejects while
  `halve(n)` compiles.
- free_fn_travels_to_a_union.zen -- hold UFCS candidates for nominal
  structs only: unions get `.match` hardcoded but never user functions,
  and both lines reject with "no `name` on `Color`".
- free_fn_travels_with_the_type/ -- gather dot candidates from the CALLING
  module's scope only: `b.perimeter()` rejects ("no `perimeter` on `Box`")
  because main never imported the function.
- generic_free_fn_specialises_per_receiver.zen -- instantiate `<T>(p:
  Pair<T>, x: T)` once (first call wins) or fail to unify T with the
  receiver's instantiation: "str 0" flips to 1, or rejects `"y"` as i32.
- methods_overload_on_a_later_parameter.zen -- stop overload matching at
  the receiver or at C-visible types (i64 vs str collapses): one of
  "300"/"4" answers the other body.
- mutating_free_fn_writes_through_the_dot.zen -- pass a `::` free
  function's receiver BY VALUE: its writes land on a copy, "free 21"
  becomes "free 1"; narrowing the check also breaks it (method twin stops
  compiling).
- same_fn_name_on_two_types/ -- key dot candidates by name across modules
  without binding each to its parameter type: `b.span()` answers P's body
  (34) instead of Box's (13); both types shaped alike so the wrong symbol
  still links.
- paren_wrapped_lambda_keeps_its_arity/ -- punctuation cannot hide a
  closure's arity from method overload filtering.

## CROSS-DOMAIN OVERLOADS

Method and free-function declarations are checked as one overload set when
the free function's first parameter accepts the method's receiver. Exact,
generic-swallowing, and optional-suffix collisions are must-fail tests in the
sema lane. `method_and_free_fn_split_on_later_type.zen` keeps the legal edge:
same name and arity remain valid when a later parameter makes the calls
disjoint.

Also verified while probing (behaviour, not bugs):

- Unexported free functions DO travel by dot across modules: main reaches
  box.zen's private helper through an imported type. Export gates BARE
  names, not the travelled pool; DESIGN.md's "* is the one gate" sentence
  may want a word either way. Not pinned.
- Existing multi-module corpus tests (sema/bound_third_module,
  codegen/mangle_module_collision, sema/ufcs_travels_to_an_impl_of_the_bound)
  are RED under runzen.sh today: their imports fail with "nothing is at
  that path". Single-file runs pass, so runzen.sh stages multi-module roots
  differently than tests/run.py does. Not this lane's area; flagging it.

TESTS: 18
