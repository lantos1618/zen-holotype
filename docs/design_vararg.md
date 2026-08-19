# `vararg<T>` — a variadic that is a real type

Written 2026-08-17, and landed the same day. `docs/design_fmt.md` §5 records the
question this answers; that section stays as the record of what was believed
before the code existed, and this document supersedes its pricing.

A separate file rather than a section of `design_fmt.md`, because the format
language is no longer the subject. `...` was born inside the format doors and
`vararg<T>` is not: it is a parameter form, it does not touch those doors, and
the two coexist. Filing it under "the format language" would have made a
language feature read as a formatting detail.

---

## 1. What it is

    sum   = (v: vararg<i32>) i32                // zero or more i32
    label = (tag: str, parts: vararg<str>) usize // a fixed prefix, then the rest
    relay = (tag: str, parts: vararg<str>) usize { label(tag, parts) }   // FORWARDED

A `vararg<T>` is **a borrowed run of `T` and its length** — the same two words
`str` is. At a call site the arguments the pack swallows are materialised into a
run and one value is passed; inside the callee it is an ordinary value that can
be indexed, walked, and **passed on**.

**It is an ordinary declared struct**, `src/std/collections/collections_vararg.zen`:

    vararg*<T> = { data: Ptr<T>, len*: usize, get*, index*, is_empty* }
    vararg.impl(Range<T>, { start: 0, end: self.len, at ::= .. })

That is the whole design, and everything cheap about this lane follows from it:

| what | who does it | cost |
|---|---|---|
| parsing `vararg<T>` | `parse_type.named_type`, unchanged | **nothing** — it is a name applied to arguments |
| resolving it | `sema_type.lookup_named`, unchanged | **nothing** — a nominal like `Vec<i32>` |
| interning it | `Types.declared`, unchanged | **nothing** |
| a C type for it | `gen_c_type.named_ctype`, unchanged | **nothing** — a monomorphised struct |
| copying / forwarding it | C struct assignment | **nothing** |
| `v.loop(..)`, `v.find(..)` | the `Range<T>` impl above | six lines of Zen |

No new `TypeKind`, no new `Ty` variant, no tuple, no boxing, no vtable, no
comptime evaluator. **Nothing structural is introduced**: `vararg<T>` is
declared, so `PLAN.md:371`'s "declared types stay nominal" is untouched, and the
one structural exception (a union) is not involved.

Only two things are special, and both are about the **call**.

---

## 2. The pack's layout

At the call site, `sum(1, 2, 3)` emits (`gen_c_call.write_run`):

    zu_f_sum((zu_t_varargI1_b3i32){ .zu_m4data = (int32_t[]){ 1, 2, 3 },
                                    .zu_m3len  = 3u })

A **C compound literal inside a C compound literal**: the run, and the two words
that describe it. Both have automatic storage in the *calling* block, which is
exactly as long as the call and no longer. `sum()` emits `{ 0 }` — a null run of
length zero, because a zero-length array initialiser is a GNU extension and this
backend is C99.

Consequences worth stating plainly:

- **Nothing is allocated.** `make bench-allocs` is unaffected by a vararg call;
  a pack costs one stack run and two words.
- **The pack borrows.** It does not own the run and it has no allocator field, so
  there is nothing to free and no way to grow.
- **There is no constructor.** `data` carries no `*`, and `collections_vararg.zen`
  exports no `vararg_at`-style builder. The only thing that can build a pack is a
  call site, and the backend is what builds it. A pack cannot be forged.

Each swallowed argument is lowered **at the element type**, so a literal takes
its width from `T` exactly as it would inside `[i32, 3](..)`.

---

## 3. Forwarding — the acceptance test

`...` cannot be forwarded, and the reason is not an implementation gap: its type
is a marker carrying no element type and no arity, so there is no C type to spell
and no value to hand on. `codegen cannot spell the type` is the honest answer.

`vararg<T>` forwards, and it is a struct copy:

    static int32_t forward(vararg_i32 v) { return sum(v); }

**One pack slot has two readings** — a run of `T` values, or exactly one value
that is already a `vararg<T>`. They cannot collide, because **`vararg` does not
nest** (§4): an argument of the pack's own type is never also one of its elements.
Forwarding is checked first, by ordinary assignability, and is not a case of its
own in the type rules.

One implementation each side of the compiler, deliberately:

- **sema**: `sema_cand.pack_sig_fits(c, ps, actuals, off, slot)`, read by the free
  function path (`off = 0`) and the method path (`off = 1`, parameter zero being
  the receiver). Two entry points, one rule — otherwise a call the checker
  accepted at one arity is emitted at another.
- **codegen**: `gen_c_call.write_call_args(be, c, first, ..)`, read by
  `write_call` and by `gen_c_member.write_rest`. A pack built two ways is a pack
  built one way wrongly.

---

## 4. Where a `vararg` may be written, and why the rule is this blunt

**Only as the whole type of a function's last parameter.** Everywhere else is
refused by name:

    f = (v: vararg<i32>, tail: i32)     // refused: not last
    f = (v: vararg<vararg<i32>>)        // refused: element is a pack
    f = () vararg<i32>                  // refused: return type
    Bag = { held: vararg<i32> }         // refused: field
    f = (v: vararg)  /  vararg<A, B>    // refused: one element type, exactly

This is not a simplification pending something better. **It is what makes the
pack sound with no lifetime machinery at all.** A pack borrows the calling frame,
so any position it could outlive the call from would dangle — and the shape is
one line:

    g = () vararg<i32> { f(1, 2, 3) }   // the run dies with g's block

Refusing every other position costs one scan and is exact, where an escape
analysis would be neither. Two faults say so:

- `SemaFault.VarargNotLast` — "a vararg is only ever a function's last parameter:
  the pack borrows the caller's frame, so anywhere it could outlive the call it
  would dangle"
- `SemaFault.VarargElement` — "a vararg writes exactly one element type, and it is
  never itself a vararg: `vararg<T>` is a run of T, and no call site could build
  a run of runs"

`vararg<vararg<i32>>` in a last parameter reports **both**, and that is right: the
outer says the element may not be a pack, the inner says a pack is a last
parameter's type. Both sentences are true of it and both halves have to go.

### How the rule is reached

The rule is about a written type's **position**, and a type node carries its span
but not its parent. So the two halves name themselves separately:

- `src/sema/sema_vararg.check_varargs` gathers every `vararg` mention in the
  compilation (`Ast.types_where`, one match per type node — it finds nothing in a
  tree with no varargs), then collects every function's last-parameter type id
  and reports the difference. Whole-program, beside `check_layout` and
  `check_depth` in `check_all`.
- `bootstrap/sema.py` reaches the same rule from the other end: the check sits in
  `resolve_named`, where every type node the compilation resolves passes, keyed on
  `id(node)` against the same collected set (`_pack_positions`).

Both are whole-program and both report the same two sentences at the same
positions. The wordings are shared deliberately, because a `must-fail`
expectation is read by both compilers.

### A consequence worth naming

Because a `vararg<T>` may not be a field, a return type, or a type argument, **a
value of pack type can only ever be a parameter binding.** That is what lets
`bootstrap`'s forwarding recognition be "one swallowed argument that is a NAME
bound to this pack type" — complete, and needing no typing pass. The self-hosted
backend asks the more general question (`ty_of` equals the pack type), which is a
superset that in practice can only match a name.

---

## 5. `...` stays, and why

`...` is **not** deprecated, **not** sugar for `vararg<T>`, and **not** touched.

| | `args: ...` | `v: vararg<T>` |
|---|---|---|
| type | a marker (`c.types.prim("...")`) | a nominal, `vararg<T>` |
| element types | none — heterogeneous | one, homogeneous |
| arity at the call | a minimum | a minimum |
| a value in the callee | **there is none** — the compiler is the body | an ordinary value |
| forwardable | no | **yes** |
| declared with a body | no — bodyless by necessity | yes, ordinarily |

The three format doors — `alloc.String(fmt, ..)`, `<sink>.add(fmt, ..)`,
`<recv>.fmt(fmt, ..)` (`DESIGN.md:536`, `:749`) — are **heterogeneous**:
`fmt("{} {}", "str", 42)` mixes types in one argument list, which a homogeneous
pack cannot type. Tier 1 therefore cannot replace them and does not try. They stay
bodyless and compiler-expanded for exactly the reason `gen_c_sink.zen`'s header
gives.

That coexistence has a sharp edge, and it is handled rather than hoped:
`last_is_variadic` (`gen_c_sink.zen`) and `_is_variadic` (`bootstrap/gen_c.py`)
are the **format door's shape** and still mean exactly `...`. Widening them would
let a bodyless three-parameter `add` ending in a typed pack be lowered as that
door. The **arity** question — which both spellings answer identically — is asked
separately: `tail_is_pack` / `_written_pack` beside them, and `tail_swallows` for
the resolved-signature form.

---

## 6. What works, measured

All of the following run identically under both toolchains
(`tests/corpus/sema/vararg_pack_forwards.zen`, `..._is_a_range.zen`):

- a free function: `sum(1, 2, 3)`, `sum()`
- a fixed prefix then a pack: `label("ab", "cde", "f")`, `label("ab")`
- **forwarding**: `relay("ab", "cde", "f")` passing its own pack to `label`
- a **method**: `b.widest(1, 9, 4)`, `b.widest()`
- a pack of `str`, and iteration through the `Range<T>` impl
- a **generic struct's** method, `Bag<T>.take(vs: vararg<T>)` — `T` from the
  receiver
- a **generic function**, `count = <T>(v: vararg<T>)` — `T` inferred from the
  swallowed arguments (`gen_c_infer.unify_swallowed`,
  `bootstrap/gen_c.infer_fn_targs`)

### Known limits, stated rather than discovered later

- **A wrong element type is rejected by both compilers with different words.**
  `sum(1, "two")` is `no overload matches` from `src` and `expected i32, found
  str` from `bootstrap`. That is the pre-existing single-candidate diagnostic
  asymmetry (`src` has exactly one `NoOverload` site and no
  one-candidate-wrong-argument path), not something this lane introduced, and it
  is why no `must-fail` test asserts that message.
- **A pack is not indexable by `v[i]`** through the trap form unless the receiver
  is a place; `v.get(i)` and `v.loop(..)` are the walked forms and are what the
  corpus exercises.
- **`vararg` is not a keyword.** A module declaring its own `vararg` shadows the
  prelude's, and then `vararg<T>` in that module is that declaration — which is
  the same rule every prelude name follows. The recognition is a name compare, as
  `Res` and `Ptr` already are.

---

## 7. The first `src/` use, verified and held for a staged seed

The feature landed without `src/` using it, **deliberately**, and the reason is
mechanical rather than cautious: `make build` compiles the committed
`seed/zen.c`, and that compiler predates the pack's call convention. Measured,
not assumed — with the use applied and the committed seed in place:

    gen/gen_c/gen_c_runtime.zen:536:5: codegen cannot resolve `bytes`
    gen/gen_c/gen_c_runtime.zen:537:5: codegen cannot resolve `bytes`

So the first `src/` use needs a **staged seed**: land the feature (done),
regenerate the seed, then land the use. (It was called a staged *bootstrap*
when the Python implementation still existed; the constraint was always the
committed seed, and now it is only that.) Nothing about the use itself is
uncertain — the whole of it was built and gated against a locally staged seed:
`zen` from the feature commit compiled the modified tree, that binary compiled
it again **byte-identically** (the fixpoint property), and both suites came back
**517 passed / 0 failed / 4 deferred**, `fmt` and `style` clean.

### The use

`Emit.bytes` and `Emit.say` (`src/gen/gen_emit.zen`) take a `vararg<str>`
instead of one `str`. Two signature lines, and **no call site in the tree
changes**, because a pack's arity is a minimum — every existing one-piece call
still means exactly what it meant.

    bytes* = (self :: @Self, pieces: vararg<str>) Res<(), AllocError> {
        pieces.loop((h, s) { self.piece(s).try() });
        Ok(());
    }

    say* = (self :: @Self, pieces: vararg<str>) Res<(), AllocError> {
        self.bytes(pieces).try();       // FORWARDED — a struct copy
        self.line()
    }

`say` forwards its own pack to `bytes` rather than looping again, which is the
feature's acceptance test appearing in the compiler's own code.

### Before / after

`gen_c_runtime.open_helper`, which emits one C function header:

    // before — eleven calls, one token each
    out.bytes("static ").try();
    out.bytes(ct).try();
    out.bytes(" zg_").try();
    out.bytes(op).try();
    out.bytes("_").try();
    out.bytes(prim).try();
    out.bytes("(").try();
    out.bytes(ct).try();
    out.bytes(" a, ").try();
    out.bytes(ct).try();
    out.bytes(" b").try();

    // after — two
    out.bytes("static ", ct, " zg_", op, "_", prim, "(").try();
    out.bytes(ct, " a, ", ct, " b").try();

### Why this one, and what it unblocks

Measured over `src/gen` and `src/lsp`: **257 runs of consecutive one-piece emit
calls, 798 source lines**, plus about fourteen places that allocate a whole
throwaway `String` purely to join two to four known pieces and hand the view to
`writeln`. Both shapes exist because the sink took exactly one `str`. This
change removes the reason, without a heap allocation and without touching a
single caller — which is the strongest available evidence that `vararg<T>`
carries weight rather than only compiling.

It is also the honest scope for one lane. Converting the 257 runs is a
mechanical campaign over files two agents must not share, and it should follow
the seed regeneration, not ride it.

---

## 8. What tier 2 will need

`f = (v: vararg<A | B | C>)` — a heterogeneous pack — is now "the same thing where
`T` happens to be a union", and that is the point of doing tier 1 first.

`DESIGN.md:137-162` already gives it most of what it needs: a union is
**structural** (`:284` — "an anonymous enum of two variants … not a new kind of
type"), its identity is its member set regardless of order or spelling (`:158`),
and its tags are numbered canonically so widening is a copy (`:160`).

So what tier 2 adds is not a type and not a layout. It is one rule at the call
site: **each swallowed argument is widened into the union before it is written
into the run.** `write_run` already lowers each argument at the element type; for
a union element that lowering has to build the tagged value, which
`gen_c_widen.zen` does today at an assignment. Nothing in §2 or §4 changes: the
run is still a run, the pack is still two words, the position rule is still the
position rule.

Two things tier 1 deliberately did **not** decide, and tier 2 must:

- **How an arm reads a member back out.** A `vararg<A | B | C>` is only useful if
  the callee can ask which member each element is, which is a `.match` over a
  structural union — already expressible, but not yet through a pack element.
- **Whether `...` then retires.** With a heterogeneous pack that carries its
  member set, the format doors could in principle be declared
  `(fmt: str, args: vararg<i64 | u64 | bool | str | ..>)`. That is a real
  possibility rather than a plan: the door's expansion is driven by the *format
  string* at the call site, not by the argument list, and `@meta` (Stage 5) is what
  moves that expansion into Zen. Tier 2 makes the parameter honest; it does not by
  itself make the door library code.
