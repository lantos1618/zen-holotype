# Backend findings, and one ruling

> **The bootstrapper is deleted.** This document is a record, not a map:
> every `bootstrap/*.py` coordinate below resolves only in git history
> (`git show 4d05320a:bootstrap/gen_c.py`), and no gate can re-verify one.
> What is still worth reading is the Zen behaviour each entry describes.

Written by the orchestrator from a read-only audit of `src/gen/`, because two
agents converged on that folder and the one that stood down produced the more
useful artifact: a verification of the other's work against the reference.

Part two below was found by building the backend and running it end to end.
Reproducers run the way `tests/run.py` runs one: a compilation root holding the
program as `main.zen` with `std` and whatever other top-level modules of `src/`
it names beside it, compiled as a **directory** — the root is passed to
`bootstrap` as both the source and `--root`, and to `./zen` positionally with
`--entry main.zen`.

---

## Where this ledger stands

**Re-measured 2026-08-08 against `6ca27423`**, every entry below turned into a
complete program and run through BOTH toolchains. **Fourteen of sixteen are
closed.** §5 closed later the same day; closing it uncovered §5b, which was
added then and closed the same day again. The ONE that remains, §L, is open in
BOTH implementations, so the differential oracle cannot see it: both agree,
and both are wrong.

| # | what it claimed | bootstrap | `./zen` |
|---|---|---|---|
| A | the `#error` overflow fallback must be written | **closed, and verified** | **closed, and verified** |
| B | `.match` on a `str` scrutinee emits a struct/pointer compare | **closed** | **closed** |
| C | the grammar swallows a comment opener inside a string | n/a | **closed** |
| D | `gen_name.comp` writes non-identifier bytes through raw | n/a | **closed** |
| E | two files over `STYLE.md`'s 800-line build-failure cap | n/a | **closed** |
| F | `expr_kind` returns `Unknown` for nine node forms | n/a | **closed** |
| G | `gen.zen:51` exports no backend / the BANNER text differs | n/a | **closed** / **still true, harmless** |
| 1 | `Vec.get` at `T = str` cannot infer its own `Ok` | **closed** | **closed** |
| 2 | a local `Vec<T>` read back loses its type arguments | **closed** | **closed** |
| 3 | two modules declaring `Diag` collide on a method name | **closed** | **closed** |
| 4 | a field named like an unrelated type's field is read-only | **closed** | **closed** |
| 5 | a `.then` closure capturing several parameters is inlined wrong | **closed** | **closed** |
| 5b | an inlined callee's immutable local overwrites the caller's | **closed** | **closed** |
| 6 | binding an enum arm's payload to a local types the match `()` | **closed** | **closed** |
| 7 | a `str` scrutinee against string-literal patterns (= B) | **closed** | **closed** |
| P | `x * 2` in statement position is parsed as a declaration | **closed** | **closed** |
| L | an unannotated integer binding is a literal type, unsettled | **open, and larger** | **open, and larger still** |

A section marked closed keeps its reproducer, because a ledger that deletes
what it fixed cannot be re-run — and re-running is the only reason to keep it.

### The two to read

**§5 was filed as "a `.then` closure capturing several enclosing parameters is
inlined wrong", and it was neither the capture count nor `.then`. It is CLOSED
now; the entry is kept in full because the shape is worth recognising.** The
bootstrapper's inliner was not hygienic: `bool.then` is `<T>(b: bool, f: () T)`,
and a free name `b` or `f` anywhere inside the closure resolved to the caller's
own argument — in any position, at any arity, with no call at all. `(b >
0).then(() { println("printed {}", b) })` printed `true`. It was not about
`bool.then` either: a user-written `apply = <T>(gate: bool, thing: () T)`
corrupted a caller's local named `gate` or `thing` the same way. `./zen` was
correct throughout, which is what made it a one-lane fix.

**§5b is what closing §5 uncovered**, and it is CLOSED now: an inlined callee's
*immutable* local replaced the caller's binding of that name, for the rest of
the caller's body, in both implementations. The frame has a floor now and only
the declaration-or-store decision consults it.

**§L — "a design gap, not a bug" — is a soundness hole in the shipped
compiler, and the entry that was filed too generously.** `sema_trap.check_literal`
is reached from exactly ONE call site in `src/`: `sema_type.check_assign`, on a
`Bind`. So `x: i32 = 3000000000` is refused and **every other position a
literal can meet a narrower integer type is not** — a call argument, a record
field, a return value, a match arm, a fixed-array element. `./zen` truncates
all five silently. `bootstrap` catches four of the five and misses the
fixed-array element, so that one shape is **both implementations wrong the same
way**, which no differential test can see.

`tests/must-fail/traps/literal_too_large_i32` exists and passes under both
toolchains. It uses an annotated binding — the one shape that is checked.

---
---

# Part one: the audit

## A. RULING: the `__builtin_*_overflow` fallback is required, not optional

**CLOSED, and the fallback arm is verified to work — which nothing else in the
tree does.** The ruling and its reasoning are kept because the constraint is
permanent.

`gen_c_runtime.zen` used to emit `#error "this backend needs
__builtin_add_overflow and friends"` under `#else`, documented there as "COST
ACCEPTED KNOWINGLY". It was not accepted, for a reason that is not style but
`PLAN.md`'s central promise:

> **`build`: what a newcomer runs. needs only a C compiler.**

`__builtin_add_overflow` is a GCC/Clang extension, not C99. A seed that
`#error`s without it is a seed only two compilers can build, which removes the
reason the seed is committed at all.

`gen_c_runtime.zen` now emits every checked helper twice —
`__builtin_*_overflow` under `#ifdef ZG_HAS_OVERFLOW_BUILTINS`, and the
reference's hand-written pre-operation range test under `#else`: two-sided for
signed add and subtract, four-quadrant for signed multiply, one-sided for
unsigned (`gen_c_runtime.zen:550-559`, `signed_guard` at 585, `unsigned_guard`
at 647).

### Nothing compiles the `#else` arm

The emitted header is

```c
#if defined(__GNUC__) && (__GNUC__ >= 5)
#define ZG_HAS_OVERFLOW_BUILTINS 1
#elif defined(__has_builtin)
#if __has_builtin(__builtin_add_overflow)
#define ZG_HAS_OVERFLOW_BUILTINS 1
#endif
#endif
```

so on every compiler anyone here runs, the fallback is preprocessed away. The
35 corpus tests under `tests/corpus/traps/` gate the *builtin* arm and say
nothing about the other. The arm was measured by hand instead, by renaming the
macro in the emitted C:

```bash
./zen build $ROOT --entry main.zen --emit-c -o out.c
sed 's/#define ZG_HAS_OVERFLOW_BUILTINS 1/#define ZG_NEVER_DEFINED 1/' out.c > fb.c
cc -O0 -std=c99 -pedantic fb.c -o fb && ./fb; echo $?
```

Run over all 35 programs in `tests/corpus/traps/`: **35 compile clean under
`-std=c99 -pedantic` and 35 exit with the code the test's `.exit` asks for.**
The fallback is correct. It is also unguarded — a change to `signed_guard` that
breaks it would go green everywhere. The cheap gate is the three lines above in
CI over a handful of trap tests.

## B. A `str` scrutinee against string-literal patterns

**CLOSED in both.** The claim was that

```c
if (zg_t2 == "i8")            /* zg_str struct vs char * */
```

was emitted silently, with no diagnostic, which is why `c_prim` was written as
nested `pick` calls rather than the match it wants to be.

```groovy
c_prim = (n: str) str {
    n.match({
        "i8"  => "int8_t",
        "i32" => "int32_t",
        "str" => "zg_str",
        _     => "void",
    });
}

main = (env: Env) Res<i32, AllocError> {
    println("{}", c_prim("i8"));
    println("{}", c_prim("i32"));
    println("{}", c_prim("str"));
    println("{}", c_prim("nope"));
    Ok(0);
}
```

Both toolchains print `int8_t / int32_t / zg_str / void`.
`tests/corpus/sema/match_on_str_literals` is the standing guard.

**Workarounds now load-bearing for nothing**, and both name this ledger in
their own comments:

- `src/gen/gen_c/gen_c_type.zen:188` — `c_prim` is eight nested `pick(..)`
  calls draining into `c_prim_wide`, which is eight more, plus the `pick`
  helper itself. Its comment says *"When that is fixed this becomes the
  seventeen-arm match it wants to be."* It is fixed.
- `src/gen/gen_c/gen_c_runtime.zen:585,647` — `signed_guard`,
  `signed_sub_or_mul`, `unsigned_guard`, `unsigned_sub_or_mul` are `op.eq(..)`
  chains, each a two-arm `.match` on a boolean, for the same reason. Four
  functions collapse to two matches.

## C. A claimed bug that was NOT real, and cost real code

`gen_c_runtime.zen` used to state that a Zen string literal containing a
comment opener does not parse, and wrote `comment()` a byte at a time to avoid
it. **That bug was fixed** in `e096260a`, "grammar: a string is one token, so
nothing inside it is syntax", and
`tests/corpus/lex/string_containing_comment_markers.zen` gates it.
`comment()` has since collapsed to one `out.say`.

The general lesson is worth more than the line count: a workaround outlives the
bug unless it names the bug, and re-testing is cheaper than assuming. It is why
this file exists in this shape.

## D. `gen_name.comp` wrote non-identifier bytes through raw

**CLOSED.** `comp` (`gen_name.zen:83`) now tests `is_c_identifier` and routes a
failure to `escaped_comp`, which writes `x` followed by two hex digits per
byte. The specific hazard the entry named is gone twice over: a fixed array is
no longer interned as `named(ARRAY_DECL, "[]", ..)` at all, but mangled by its
own rule — `gen_name.zen:466`, "`[i32, 4]` is `a4_bi32`. THE COUNT IS IN THE
NAME."

The entry said "nothing in the corpus spells a fixed array through the Zen
backend yet, which is the only reason this is latent". That is no longer true
either: `tests/corpus/parse/array_type_applied` builds `[i32, 4](2, 3, 5, 7)`
and indexes it, and `tests/corpus/traps/index_runtime` and
`index_at_len_runtime` trap on one.

## E. Two files over the hard cap

**CLOSED.** `gen_c_type.zen` was 831 lines and `gen_c_expr.zen` 973; both were
split by subject. `python3 scripts/line_cap.py` now reports **41 over 500, 0
over 800**, and `gen_c_type.zen` is 579.

## F. Sema's shape, for whoever finishes the backend

The backend is finished, so these are history rather than instructions — but
one of them was a claim and it is now false.

- **`expr_kind` returns `Unknown` for `Call`, `Access`, `Lambda`, `Record`,
  `Index`, `FixedArray`, `Array`, `Scope`, `Meta`.** **No longer true.**
  `sema_type.zen:387` has no `Unknown` arm left; every form is answered.
- The `block_type`-then-read-back protocol, and "a backend must read
  `Checker.expr_memo` directly and never call `type_of`", still describes the
  code: `expr_memo` is the memo (`sema_check.zen:101`) and `sema_own.zen:691`
  reads it directly with an `UNTYPED` fallback rather than asking `type_of`.
- Sema has no pointer type kind — `Ptr<T>` arrives as an ordinary `Named` — so
  a declarator never binds an asterisk in this subset. Not re-measured.

## G. Housekeeping

**CLOSED.** `src/gen/gen.zen` no longer comments out its own backend exports;
it reads

```groovy
CBackend*, emit_program*, Dest*          = gen.gen_c
ctype*, C_STANDARD*, emit_types*         = gen.gen_c
```

**Still true, and still fine:** the reference `BANNER` / `INCLUDES` text is not
reproduced byte-for-byte, so line 1 of the two backends' output differs
(`/* Generated by the Zen compiler. */` against `/* Generated by the Zen
bootstrapper (bootstrap/gen_c.py). */`). The fixpoint compares stage2 against
stage3 — both from the Zen backend — so it is unaffected; it only means the two
backends' C cannot be diffed directly.

**Never here at all:** `gen_c_mono.zen` and `gen_c_ptr.zen` each carried a
comment warning that `be.check.types.named(..)` DOES NOT INTERN when reached
through TWO field hops, and each cited this file for the emitted C. No such
entry has ever existed in this ledger, and the claim is false in the shipped
compiler: `gen_c_display.zen:249` makes exactly that two-hop mutating call and
emits `&((*zu_l2be).zu_m5check.zu_m5types)` — the address of the real nested
store, with no temporary spilled. Both comments were deleted 2026-08-16. The
`intern_*` forwarders they justified were kept: eight modules call them, and a
named forwarder is worth having on its own.

---
---

# Part two: findings from writing `src/gen/`

## 1. `Vec.get` at `T = str` cannot infer its own `Ok`

**CLOSED in both.** The reproducer prints `hello` under each. It used to be two
diagnostics pointing at `std`, from a program that never mentions
`std.collections`, taking the whole compilation down.

```groovy
pick = (a: Alloc, i: usize) Res<str, AllocError> {
    v ::= a.Vec<str>();
    v.add("hello").try();
    Ok(v.get(i).match({ Ok(s) => s, None => "" }));
}

main = (env: Env) Res<i32, AllocError> {
    alloc ::= env.mem.alloc();
    println("{}", pick(alloc, 0).try());
    Ok(0);
}
```

```
std/collections/collections_vec.zen:39:22: cannot infer the type of `Ok` here
std/collections/collections_vec.zen:40:22: cannot infer the type of `None` here
```

`Vec<bool>` failed the same way, while `Vec<Def>`, `Vec<TyId>`, `Vec<String>`
and `Map<ExprId, TyId>` were fine — so it was never "a generic in a Vec", it
was `Res<T>` at particular `T`s, and `str` is the one a backend reaches for
constantly.

**Workaround, no longer needed:** `gen_c_call.storage_name` counted to the i-th
storage member with two mutable locals rather than collecting names into a
`Vec<str>`. That function no longer exists under that name; whatever replaced
it is free to collect.

## 2. A local `Vec<T>` read back in the same function can lose its type arguments

**CLOSED in both**, and it is the one entry that already had a test written for
it: `tests/corpus/sema/vec_get_in_a_helper_is_not_map_get`.

```groovy
Ty = { index*: usize }

first_named = (a: Alloc, n: usize) Res<Ty, AllocError> {
    found ::= a.Vec<Ty>();
    Range(0, n).loop((h, i) { found.add(Ty(index: i + 1)).try(); });
    Ok(found.get(0).match({ Ok(t) => t, None => Ty(index: 0) }));
}
```

Both toolchains print `1`. It used to emit `Map.get` instantiated at
`Map<q, q>` — `q` is the mangler's *unresolved* tag — for a `Map` the program
does not use, and reported

```
std/collections/collections_map.zen:93:9: cannot infer the type of `Ok` here
```

Resolution had fallen through to a global by-name search for `get`, which is
`LEXER_BOOTSTRAP_FIXES.md` §7 surfacing in a new place.

## 3. Two modules declaring `Diag` collide on a method name, and `cc` reports it

**CLOSED in both, and now gated** —
`tests/corpus/modules/same_type_name_method_and_free`, added by this audit,
because nothing was covering the shape. `corpus/modules/same_name_overload`
covers two modules declaring the same *free function* on two different types;
this covers two modules declaring the same *type*, one with `render` as a free
function and one with `render` as a method.

```groovy
// alpha/alpha.zen
Diag* = { code*: usize }
render* = (self: Diag, tag: usize) usize { self.code + tag }

// beta/beta.zen
Diag* = { note*: usize, render* = (self: @Self) usize { self.note * 10 } }

// gamma/gamma.zen -- sees BETA's Diag
Diag = beta.beta
shout* = (n: usize) usize { d = Diag(note: n); d.render(); }

// main.zen -- sees ALPHA's, and calls gamma
Diag, render = alpha.alpha
shout = gamma.gamma
main = (env: Env) Res<i32, AllocError> {
    a = Diag(code: 5);
    println("{}", render(a, 1));   // 6
    println("{}", a.render(1));    // 6
    println("{}", shout(7));       // 70
    Ok(0);
}
```

It used to be `cc`, not Zen, that reported the collision:

```
error: too many arguments to function 'zu_f4_3gen8gen_diag4Diag6render'
note:  expected 'zu_t3_3gen8gen_diag4Diag' but argument is of type
       'zu_t3_4sema9sema_diag4Diag'
```

**Workaround, no longer load-bearing:** the gen type is `GenDiag` and the
renderer is the free function `render_gen` (`src/gen/gen_diag.zen:66`), whose
comment still says *"A free function rather than a method … a method is
resolved by name across every module and this one has to be reachable without
competing with three other renderers."* Resolution is on the receiver now.
`GenDiag.render` is available if wanted — `python3 scripts/ufcs_collisions.py`
is the arbiter, and it currently reports 0 ambiguous over 2960 UFCS free
functions.

## 4. A struct field whose name matches a field of an unrelated type is read-only

**CLOSED in both.** Both print `42`.

```groovy
Function = ast.ast_node      // declares `body*` -- immutable, another module

Backend = { body :: usize }

fill = (be :: Backend) Res<(), AllocError> {
    be.body = 42;
    Ok(());
}

main = (env: Env) Res<i32, AllocError> {
    be ::= Backend(body: 0);
    fill(be).try();
    println("{}", be.body);
    Ok(0);
}
```

It used to say

```
gen_c_decl.zen:187:8: body is not writable outside module ast_node
```

— the assignment checked against `ast.Function.body` instead of the backend's
own field.

**Workaround, no longer needed but keep it:** the field was renamed `buf` and
unexported behind six forwarding methods, which is what DESIGN.md asks for
anyway ("mutation only ever goes through exported methods"). Nothing named
`buf` survives in `gen_c.zen` today, so the code has moved on regardless.

## 5. The bootstrapper's inliner is not hygienic

**CLOSED.** Fixed in `bootstrap/gen_c.py`; pinned by
`tests/corpus/std/bool_then_closure_keeps_its_own_names.zen`, which is the
first corpus test that could name a caller local the callee also binds. The
whole entry below is kept, because a ledger that deletes what it fixed cannot
be re-run — and the reproducers here now agree with the `./zen` column.

The mechanism turned out to be one line, and it was not substitution at all.
`bind_closure` recorded the scope depth by reading `len(self.scopes)` — but
`inline_call` calls it *after* pushing the callee's frame, so the rewind in
`inline_lambda` (`self.scopes = self.scopes[:marker[3]]`) kept that frame
instead of dropping it. The depth is now taken at the call site, before the
push. C names were never the problem: `FnCtx.declare` already numbers them
uniquely, so no renaming pass was needed and none was written.

**Scope of the fix, exactly.** It covers every binding that lives in the frame
`inline_call` pushes: the callee's parameters, the receiver bound under the
first parameter's name, and the callee's own **mutable** locals, which
`block_value` puts in that same frame. It does **not** cover a callee's
immutable local — `held = 77` rather than `held ::= 77` — which still wins over
a caller's binding of that name, and does so in **both** implementations
(§5b below). That is a different bug and it is still open.

The original filing follows.

**FILED AS OPEN IN THE BOOTSTRAPPER ONLY, and far too narrowly.** The entry
said "a `.then` closure capturing several enclosing parameters is inlined
wrong", and pointed at an argument slot. Neither the capture count nor the slot
is the trigger.

`bool.then` is declared `<T>(b: bool, f: () T) Res<T>` (`std/core/bool.zen:21`).
When the bootstrapper inlines it, it substitutes the callee's parameter names
into the body **without renaming what the lambda already binds**. So any free
`b` or `f` inside the closure is replaced by the caller's corresponding
argument — the receiver for `b`, the lambda itself for `f`.

### `b`: a silently wrong value, no diagnostic, valid C

```groovy
Sink = {
    total* :: usize,
    two* = (self :: @Self, x: usize, y: usize) Res<(), AllocError> {
        self.total = x * 100 + y;
        Ok(());
    }
}

b_first = (s :: Sink, b: usize) Res<(), AllocError> {
    (b > 0).then(() { s.two(b, 4).try() });     // 304
    Ok(());
}

n_first = (s :: Sink, n: usize) Res<(), AllocError> {
    (n > 0).then(() { s.two(n, 4).try() });     // 304
    Ok(());
}

b_printed = (b: usize) Res<(), AllocError> {
    (b > 0).then(() { println("printed {}", b) });   // printed 3
    Ok(());
}
```

```
bootstrap   b_first 104     n_first 304     printed true    <- before the fix
./zen       b_first 304     n_first 304     printed 3
bootstrap   b_first 304     n_first 304     printed 3       <- after
```

`b_first` gets `104` because `b` became the receiver `(b > 0)`, which is
`true`, which is `1`. `n_first` — the same program with the parameter renamed —
is correct, which is the whole proof. `b_printed` has no call, no arity and no
argument slot at all, and still prints `true` for `3`.

The emitted C says it plainly. From the original four-parameter case:

```c
zg_t4 = zu_f3_4main4Sink4bump(&(*zu_l1s), zu_l1a, zu_f2_4main3big(zu_l1n));
                                                  ^ the .then receiver, where `b` was
```

A literal in the same position is untouched — `s.two(a, 3)` is correct — so
this is name substitution, not positional.

### `f`: an undeclared identifier in the output

```groovy
f_named = (s :: Sink, f: usize) Res<(), AllocError> {
    (f > 0).then(() { s.two(f, 4).try() });
    Ok(());
}
```

```
error: 'f' undeclared (first use in this function)
    zg_t4 = zu_f3_4main4Sink3two(&(*zu_l1s), f, ((size_t)4ULL));
```

The bare `f` is the closure marker's own first field — `bind_closure` stores
`(name, ("lambda", ..))`, so a `find` that reached the callee's frame handed
the *Zen* name back as if it were a C name. After the fix `f_named` compiles
and prints `304` like the rest.

### It is not about `bool.then`

Any inlined function taking a lambda does it, including a user's own:

```groovy
apply = <T>(gate: bool, thing: () T) Res<T> {
    gate.match({ true => Ok(thing()), false => None });
}

main = (env: Env) Res<i32, AllocError> {
    thing = 7;  apply(true, () { println("thing {}", thing) });   // thing 7
    gate  = 9;  apply(true, () { println("gate {}", gate) });     // gate 9
    other = 5;  apply(true, () { println("other {}", other) });   // other 5
    Ok(0);
}
```

```
bootstrap   main.zen:10:42: cannot print a value of this type
            thing            gate true       other 5         <- before the fix
./zen       thing 7          gate 9          other 5
bootstrap   thing 7          gate 9          other 5         <- after
```

### What was at risk — now nothing

The scan is unchanged and still finds exactly **three sites**, all of one shape:

```
src/std/build/build.zen:151   (in the doc comment on `Builder.module`)
example/build.zen:58          .then(() { tests.add(f).try() })
example/build.zen:70          .then(() { benches.add(f).try() })
```

`f` is the loop's value binding, so these used to break the C compile rather
than silently lie — but they are the language's own showcase of "test discovery
is code, not compiler magic", and the shape `std.build` documented was the shape
the bootstrapper could not compile. `src/` was otherwise clean: every other
`.then` either keeps `b`/`f` in the receiver, where it is fine, or uses another
name. The reduced form of those three — a `.then` closure reading the enclosing
`loop`'s own `f` — now runs correctly under both toolchains.

**The workaround is load-bearing for nothing.** `.match({ true => .., false =>
Ok(()) })` in place of `.then` is now a style preference and not a workaround.
The 129 `false => Ok(())` arms in `src/` are the ordinary spelling of a
one-sided conditional in a `Res<(), E>` position, not evasions of this bug: no
`.then` in `src/` was ever affected, per the scan above.

**Corpus test:** `tests/corpus/std/bool_then_closure_keeps_its_own_names.zen`.
It covers the receiver's name (`b`), the closure parameter's name (`f`), a
user-written callee's two parameter names, and one of that callee's own
locals. Mutation-verified: restoring the one-line defect turns it red.

## 5b. An inlined callee's IMMUTABLE local overwrites the caller's

**CLOSED IN BOTH.** Both now print `before 7 / callee 77 / closure 7 /
after 7`. Pinned by `tests/corpus/codegen/inlined_callee_keeps_its_own_local
.zen`, which asserts the printed values — the only kind of test that could
catch it, since both implementations agreed and the differential oracle
compares them to each other.

**THE CAUSE, and it is the same shape as §5 without being the same bug.**
Zen writes a declaration and a store the same way, so which one `held = 77`
is depends on what is already in scope — "a second `x = ..` on a name already
bound is an assignment". That is a rule about ONE function's body, and
inlining stacks the callee's bindings on top of the caller's without hiding
them. Read across the join, the callee's first line was a store into `main`'s
`held`. §5 was a depth recorded one step too late; this was a lookup that
respected no depth at all.

The frame has a FLOOR now — `CBackend.floor` in `src/`, `FnCtx.floor` in the
bootstrapper — and exactly one decision consults it: declaration-or-store. A
READ still sees the whole stack, because a lambda's free names are resolved
by rewinding the stack rather than by a floor. A `Closure` carries the floor
of the body it was WRITTEN in beside `home`, so `(n == 0).then(() { n = n + 1;
})` on the writer's own local is still the writer's store.

The original filing follows.

**OPEN IN BOTH, found while fixing §5, invisible to the differential oracle
because both implementations agree and both are wrong.** It is a separate bug
from §5 and the §5 fix does not touch it: §5 was the closure's *view* of the
callee frame, this is a binding surviving the frame entirely.

```groovy
apply = <T>(gate: bool, thing: () T) Res<T> {
    held = 77;
    println("callee held {}", held);
    gate.match({ true => Ok(thing()), false => None });
}

main = (env: Env) Res<i32, AllocError> {
    held = 7;
    println("caller held before {}", held);
    apply(true, () { println("closure held {}", held) });
    println("caller held after {}", held);
    Ok(0);
}
```

```
bootstrap   before 7   callee 77   closure 77   after 77
./zen       before 7   callee 77   closure 77   after 77
```

`after 77` is the tell, and it has nothing to do with the closure: the caller's
own next statement reads the callee's binding. Spelling **both** locals `::=`
instead of `=` gives `before 7 / callee 77 / closure 7 / after 7` under both,
which is correct — so it is the immutable form specifically. The corpus test
for §5 therefore used `::=` for its callee-local case; the `=` shape is now
asserted by `tests/corpus/codegen/inlined_callee_keeps_its_own_local.zen`.

## 6. Binding an enum arm's payload to a local types the match as `()`

**CLOSED in both.** Both print `nope / gone / plain`.

```groovy
Fault = Unsupported(str) | Unresolved(str) | Plain

describe = (f: Fault) str {
    what = f.match({
        Unsupported(w) => w,
        Unresolved(w)  => w,
        Plain          => "plain",
    });
    what;
}
```

It used to emit `void zu_l4what = 0;`. Every arm was `str` and the first one
was too, so it was never `LEXER_BOOTSTRAP_FIXES.md` §2's first-arm rule — it
was a payload binder reaching a local.

**Workaround now load-bearing for nothing:** `src/gen/gen_diag.zen:95-105`,
`detail`, writes the payload straight into the sink in each of five arms, and
its comment names this entry as the reason. It can be one `fault.match({..})`
bound to a local and one `out.add_bytes(w)`.

## 7. A `str` scrutinee against string-literal patterns — confirmed again

Same as §B above; the two workarounds it left behind are listed there.

## P. A parser finding: `x * 2` in statement position

**CLOSED in both.** Both print `12`.

```groovy
double = (n: i64) i64 { x = n; x * 2 }
```

The block used to emit `return;` with "a declaration inside a body" reported at
the `x`, because the `*` was read as the export marker. `x + 2` was fine and
`(x * 2)` was fine, which is what made it a parser finding rather than a
backend one.

## L. An unannotated integer literal is unsettled — and that is the smallest part of it

**OPEN IN BOTH, and this entry was the generous one.** It was filed as "a design
gap, not a bug": `x = 6` gives `x` sema's `int`, a use of `x` in an `i32`
context narrows at the call, and settling a literal's type from its context is
bidirectional inference and sema's job. All true. What it does not say is that
**the check which does exist runs in exactly one place.**

`src/sema/sema_trap.zen:169` declares `check_literal`. `grep` finds one call
site in the whole tree: `sema_type.zen:763`, inside `check_assign`, which
`bind_stmt` calls. So the rule covers `x: i32 = <literal>` and nothing else.

```groovy
Holder = { n: i32 }
narrow = (n: i32) i32 { n }
ret = () i32 { 3000000000 }

main = (env: Env) Res<i32, AllocError> {
    println("param  {}", narrow(3000000000));
    println("field  {}", Holder(n: 3000000000).n);
    println("return {}", ret());
    arr = [i32, 2](1, 3000000000);
    println("elem   {}", arr[1]);
    m: i32 = true.match({ true => 3000000000, false => 0 });
    println("arm    {}", m);
    Ok(0);
}
```

| position | bootstrap | `./zen` |
|---|---|---|
| annotated binding `a: i32 = ..` | rejects | rejects |
| call argument | rejects | **`-1294967296`** |
| record field | rejects | **`-1294967296`** |
| return value | rejects | **`-1294967296`** |
| match arm at an annotated binding | rejects | **`-1294967296`** |
| fixed-array element | **`-1294967296`** | **`-1294967296`** |
| through an unannotated binding | **`-1294967296`** | **`-1294967296`** |

```
bootstrap  main.zen:6:16:  literal 3000000000 does not fit i32: i32 holds
                           -2147483648..2147483647, so the value is out of range
           main.zen:9:33:  (the same, at the call argument)
           main.zen:10:36: (the same, at the field)
           main.zen:14:35: (the same, at the match arm)
           bootstrap: 4 diagnostic(s)
./zen      param -1294967296   field -1294967296   return -1294967296
           elem  -1294967296   arm   -1294967296   (exit 0)
```

### Why nothing catches it

`tests/must-fail/traps/literal_too_large_i32` is the only test of the rule, and
it writes `too_big: i32 = 2147483648` — **the one position that is checked.**
It passes under both toolchains, so the suite is green and the rule looks
covered.

The fixed-array-element row is the dangerous one: the two implementations agree
and are both wrong, so the differential oracle is blind to it and only a test
asserting a value — or a rejection — can see it. The unannotated-binding row is
the same, and is the shape the original entry described.

### The tests that should exist, and why they are not here

Neither can be landed today without reddening a gate that four other lanes are
standing on. Written out so they can be added the moment the fix is:

**`tests/must-fail/traps/literal_too_large_at_a_call/`** — a literal out of
range for a narrower parameter. Green under `make test` (bootstrap rejects it),
**red under `make test-zen`**, which is at 430/0 today.

```groovy
Error = Overflow | DivideByZero | OutOfBounds
narrow = (n: i32) i32 { n }
main = (env: Env) Res<i32, Error> { println("{}", narrow(2147483648)); Ok(0); }
```

expected diagnostic, at the literal's own position:

```
literal 2147483648 does not fit i32
```

**`tests/must-fail/traps/literal_too_large_in_an_array/`** — the same value as
a fixed-array element. **Red under both.**

```groovy
Error = Overflow | DivideByZero | OutOfBounds
main = (env: Env) Res<i32, Error> {
    arr = [i32, 2](1, 2147483648);
    println("{}", arr[1]);
    Ok(0);
}
```

---

## What this ledger asks for next

In the order the work would pay off:

1. **Reach `check_literal` from every position a literal meets a type** (§L),
   starting with a call argument and a record field. `./zen` accepts an
   out-of-range literal in five of six positions and truncates it silently;
   this is the shipped compiler, and the one test of the rule covers the one
   position that works. The fixed-array-element case is wrong in *both*
   implementations, so it can only be fixed by deciding, not by diffing.
2. **Make the bootstrapper's inliner hygienic** (§5). Rename the callee's
   parameters, or refuse to substitute into a name the lambda's own scope
   binds. Until then `bool.then` silently corrupts any closure mentioning a
   `b`, `example/build.zen` does not compile through `bootstrap`, and no
   corpus test can be written in the shape the shipped compiler already gets
   right.
3. **Put the §B/§6 workarounds back into their natural form.** *Mostly done
   2026-08-16*: `gen_c_type.zen`'s `c_prim` + `c_prim_wide` + `pick` are one
   seventeen-arm `.match`, and `gen_c_runtime.zen`'s `unsigned_of` /
   `max_macro` / `min_macro` / `c_symbol` are four more. Every comment naming
   this file for a bug that is closed went with them, and the old and new
   compilers emit byte-identical C for the same input. What is left:
   - `gen_c_runtime.zen:623,708` `signed_guard` / `signed_sub_or_mul` /
     `unsigned_guard` / `unsigned_sub_or_mul` → two `.match`es on `op`. Same
     shape, same cause, and the only one of these still contorted — though it
     carries no comment blaming this file, so it reads as a choice.
   - `gen_diag.zen:86` `detail` → NOT REACHABLE as asked. Binding the payload
     to one local needs the five `str` arms to share one arm body, and the
     grammar has neither or-patterns nor a `return` inside an
     expression-position arm; both were tried and both are parse errors. §6 is
     genuinely closed — a bound `str` payload emits `zg_str zu_l4what;` and
     runs — so the false comment is gone, but the six-arm dispatch stays and is
     the shorter of the two anyway.
   - `gen_diag.zen:62` `render_gen` → `GenDiag.render` is unblocked
     (`scripts/ufcs_collisions.py` reads 0 ambiguous over 3210). The `GenDiag`
     NAME stays regardless: STYLE.md's grep test asks for it on its own, with
     no reference to §3.
4. **Gate the no-`__builtin` arm of the checked helpers** (§A). It is correct
   today — 35 of 35 trap programs compile under `-std=c99 -pedantic` and trap
   as expected with the macro renamed — and nothing anywhere would notice if it
   stopped being. Three lines of `sed` and `cc` over a handful of trap tests is
   the whole gate, and PLAN.md's "needs only a C compiler" is what it protects.
