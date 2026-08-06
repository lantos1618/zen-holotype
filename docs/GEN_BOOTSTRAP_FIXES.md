# Backend findings, and one ruling

Written by the orchestrator from a read-only audit of `src/gen/`, because two
agents converged on that folder and the one that stood down produced the more
useful artifact: a verification of the other's work against the reference.

---

## RULING: the `__builtin_*_overflow` fallback is required, not optional

`gen_c_runtime.zen` emits `#error "this backend needs __builtin_add_overflow
and friends"` under `#else`, in place of the reference's hand-written
pre-check. It is documented there as "COST ACCEPTED KNOWINGLY". **It is not
accepted. Write the fallback.**

The reason is not style, it is `PLAN.md`'s central promise. The seed exists so
that

> **`build`: what a newcomer runs. needs only a C compiler.**

`__builtin_add_overflow` is a GCC/Clang extension, not C99. A seed that
`#error`s without it is a seed that only two compilers can build, which
removes the reason the seed is committed at all. `DESIGN.md` says the backend
emits C99; an `#error` on a missing extension is that promise failing loudly
rather than being kept.

The cost of the fallback is real and small: a few more lines per `(op, int
type)` pair, emitted only for pairs a program actually uses. The cost of the
`#error` is that `cc -std=c99` on a conforming compiler cannot build Zen.

`bootstrap/gen_c.py:5596-5698` has the fallback already written and tested by
~34 corpus tests under `tests/corpus/traps/`. Port it.

---

## Confirmed bug in the bootstrapper

**A `.match` on a `str` scrutinee against string-literal patterns emits a
struct/pointer comparison.** The generated C reads

```c
if (zg_t2 == "i8")            /* zg_str struct vs char * */
```

which is invalid, and it is emitted silently — there is no diagnostic. This is
why `c_prim` is written as nested `pick` calls rather than the match it wants
to be. Reported here rather than worked around further; the workaround is
correct in the meantime.

---

## A claimed bug that is NOT real, and cost real code

`gen_c_runtime.zen:45-62` states that

> a Zen string literal containing a comment opener does not parse — the
> grammar reads it as a real comment and swallows the closing quote

and writes `comment()` a byte at a time to avoid it. **That bug was fixed** in
commit `e096260a`, "grammar: a string is one token, so nothing inside it is
syntax". `string_literal` was a `seq`, and a `seq` lets `extras` — whitespace
and both comment forms — match between its elements; it is now a single token
with no seam for an extra to enter, and `tests/corpus/lex/string_containing_comment_markers.zen`
gates it.

Verified against real `std`: all three of

```groovy
println("/* ---- types ---- */");
println("// a line comment inside a string");
println("a \"quote\" and a /* opener");
```

parse and emit correctly. **The byte-at-a-time `comment()` can collapse to one
`out.say`.**

The general lesson is worth more than the line count: a workaround outlives
the bug unless it names the bug, and re-testing is cheaper than assuming.

---

## Latent bug in `gen_name`, which will bite the moment anything spells a fixed array

`gen_name.comp` does not encode non-identifier bytes. The reference's `comp()`
hex-escapes anything failing `^[A-Za-z_][A-Za-z0-9_]*$`; this one writes the
bytes through raw. `sema_type.array_type` interns a fixed array as
`named(ARRAY_DECL, "[]", "[]", args)`, so `[u8, 4]` mangles to

```
zu_t1_2[]I1_b2u8
```

which is not a legal C identifier. Nothing in the corpus spells a fixed array
through the Zen backend yet, which is the only reason this is latent.

---

## Two files are over the hard cap

`gen_c_type.zen` (831 lines) and `gen_c_expr.zen` (973) both exceed
`STYLE.md`'s 800-line **build failure** threshold. Split by subject, never by
size — and note `STYLE.md` allows an exception only if the path is listed in
`build.zen` with a written reason.

---

## Sema's shape, for whoever finishes the backend

- `expr_kind` returns `Unknown` for `Call`, `Access`, `Lambda`, `Record`,
  `Index`, `FixedArray`, `Array`, `Scope`, `Meta`. **`Match` is handled** now,
  via `sema_match` / `sema_case`.
- The `block_type`-then-read-back protocol is mandatory, and stricter than it
  first appeared: after the walk, `type_of` on a memo **miss** re-reports
  `undefined name` into sema's diagnostics. A backend must read
  `Checker.expr_memo` directly and never call `type_of`.
- Sema has no pointer type kind — `Ptr<T>` arrives as an ordinary `Named` — so
  a declarator never binds an asterisk in this subset.

---

## Housekeeping

`src/gen/gen.zen:51` currently reads

```groovy
// CBackend*, emit_program*, ctype*         = gen.gen_c
```

commented out to unblock module resolution while the backend is written.
**It must be restored when the folder root lands**, or the `gen` module
exports no backend and `src/zen.zen` has nothing to call.

The reference `BANNER` / `INCLUDES` text is not reproduced byte-for-byte, so
line 1 of the Zen backend's output will differ from `bootstrap/gen_c.py`'s.
That is fine for the fixpoint, which compares stage2 against stage3 — both
from the Zen backend — but it means the two backends' output cannot be
diffed directly during the differential-oracle stage.
