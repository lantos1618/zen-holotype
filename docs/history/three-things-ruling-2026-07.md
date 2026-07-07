# rt v2 + error sugar + enum syntax — 5-elite-judge ruling (2026-07)

## Q1 — rt v2: verdict (mean score, is it nicer than Pony/Zig?)

**Tally:** 8, 8, 8, 7.5, 8 — **mean 7.9/10**. Nicer than both Pony and Zig: **4× yes, 1× mixed** (the Swift-surface judge scores Pony a trade, not a win: Pony's zero-memory-concepts is easier on day 1, but its 6-refcap tax loses on day 1000).

**Consensus ruling:** rt v2 is the sweet spot and all five would write programs in it. Unanimous reasoning: it beats Zig 0.16 by moving capability honesty from per-signature noise to the build.zen/behavior boundary (ambient-in-scope containers, swap-in-tests preserved), and beats Pony by making its per-actor-heap + refcap model explicit, static, and pluggable — "the BEAM memory model made static", "Pony with the refcap tax repealed". The 3 send shapes (copy | frozen Arc | iso move) are unanimously named the best single decision.

**The ONE convergent improvement (3/5 judges — Rust, Swift, Pony):** make the scratch-escape checker *teach the fix*. Default everything to scratch; when a value escapes, the error names the exact one-token remedy via two blessed promotion verbs — `v.share(rt)` (freeze → Arc) and `v.give(rt)` (iso move, sender's binding killed). The first region error a user hits decides whether the checker feels like a colleague or Pony's recover-block hazing.

**Real dissent:**
- **Zig judge:** loses grep-ability (`v.push(x)` allocates invisibly; "which region" is runtime state, not text); wants `rt.region((r) {...})` because non-actor CLI code makes scratch leak-by-default.
- **Erlang judge:** actors should get `self.rt` (attenuated) implicitly, or nested spawn reinvents Zig's threading noise; also flags zero links/monitors/supervision story.
- **All five agree on the risk:** the escape checker is now load-bearing for the entire ambient-memory pitch — its precision is execution risk, and the off-actor/library-convention story (who takes rt vs rt.mem vs nothing) must be decided before users invent five bad ones.

## Q2 — error handling: THE surface to ship

Verified against the live tree: **`.or_return()` already exists and is compiler-lowered** (check.zen:1342-1428, demoed in examples/tour.zen:45) but only in let-position; `std/core/result.zen` has no combinators; the raw/try_ doubling is live (actor.zen:275 `try_spawn`, plus the coroutine.zen `try_*` family). So Q2 is "generalize shipped sugar", not "design from scratch".

**THE surface (final):**

1. **`.or_return()`** — propagation. Postfix compiler sugar; on `.Ok(v)` yields `v`, on `.Err(e)` early-returns `.Err(e)` from the enclosing fn. Enclosing return type must be `Result<_,E>` with the **same E** — no From/Into magic in v1; bridge with `.map_err(f)`. Extended from let-position to **any expression position, including mid-chain**. *Name pick over the 4-judge `.try()` majority: it's already shipped and corpus-live, and the name states the control flow verbatim — the honest spelling in a no-hidden-anything language; renaming working sugar is pure churn.*
2. **`.expect(msg: str)`** — T or `panic(msg)` printing the Err value. Msg is **mandatory**; there is deliberately **no bare `.unwrap()`** (5/5 unanimous: panic-explicit-only means every panic site carries its invariant in words). *Picked `.expect` over `.or_panic` 4–1: cross-language familiarity, and the required message already makes the panic explicit.*
3. **`.or(default)`, `.or_else(f)`, `.map_err(f)`** — plain generic fns in std/core/result.zen, zero compiler support.
4. **`.match` stays THE primitive** for genuine multi-way decisions; sugar only compresses "no decision here, pass it up". Rejected unanimously: bare `?` sigil, and "match-only pain as honesty" — the pain isn't load-bearing, it's what caused the raw/try_ API rot and `.Err(e) => return 1` reason-erasure.
5. Iterator chains: no monadic magic; later add `.collect_ok()` (`Vec<Result<T,E>> → Result<Vec<T>,E>`, first Err wins).

**Canonical example:**

```zen
main = (rt: Rt) Result<i64, IoError> {
    c := rt.spawn(Counter()).or_return()     // Err propagates to caller
    c.send(.Inc(3))
    cfg := rt.read_file("app.cfg").or("")    // policy at the callsite: default
    n := c.ask(.Get).or_return()
    ok(n)
}
```

**Spawn ruling — unanimous 5/5:** `spawn` returns `Result<ActorHandle<M>, IoError>` **always**. Delete `try_spawn` (actor.zen:275) and the entire `try_*` family in coroutine.zen in the same PR that lands expression-position `.or_return()`. Raw spawn is a hidden OOM panic; the doubling existed only because propagation was painful, and at one token of cost it has no remaining excuse. Root callers write `rt.spawn(a).expect("root actor")` and own the panic in the diff.

## Q3 — enums: THE ruling

**Tally: keep-dotted 5/5, bare 0/5.** Not close.

**Final call:** dotted stays, permanently. Bare `Inc(3)` in a flat value namespace with no overloading and no module paths makes every variant a de-facto reserved global (`err` is already exported by result.zen); Swift and Zig ship dotted-with-expected-type at scale and it's loved, not tolerated; the corpus is 100% dotted (1667 line-initial `.Capital` occurrences) so bare is total-rewrite churn for negative value. Hybrid rejected as two spellings of one concept. The readability complaint was always the glue bug, and **two judges verified live that the glue is ~90% already fixed** by `is_variant_break` (parse_expr.zen:337-341) — newline + `.Upper` after normal statements parses correctly today.

**The concrete fix (converged by the 3 judges who read the parser):** delete the **uppercase-subject carve-out** in `is_variant_break` (parse_expr.zen:340 — the `is_upper_byte(subj_name(base.expr).at(0))` clause), making the rule total: **newline before `.Uppercase` ALWAYS ends the previous statement**. This kills the one remaining *silent* hole (`x := Res` ⏎ `.Okv(y)` currently glues into `Res.Okv(y)`). Consequence: qualified ctors `Type.Variant(...)` must keep the dot on the type's line — same same-line gate the parser already applies to `[index]` and qualified struct literals, so the grammar gets more uniform. Plus: formatter enforces same-line qualified ctors; a checker hint for the same-line glue case (`t := tick()  .Ok(t)`); codify Uppercase-variant / lowercase-method as grammar, not convention; delete the stale dodges (build.zen trailing `b.config()`, runtime.zen sig_go) as the regression proof; add fixtures for statement-initial `.Ok(x)`. Gate: rebuild, oracle green, fmt fixpoint byte-exact.

## Ship list

One release, not three — rt v2 presents as a 6 until the sugar lands (unanimous judge note).

1. **[S] Glue-fix:** delete the uppercase-subject carve-out at parse_expr.zen:340; formatter rule (qualified ctor same-line); retire build.zen `b.config()` + runtime.zen sig_go dodges; regression fixtures. Prerequisite — sugar-heavy fns end in statement-initial `.Ok(...)` constantly.
2. **[S] Result combinators:** `.expect(msg)`, `.or`, `.or_else`, `.map_err` as plain generics in std/core/result.zen. No bare `.unwrap()`.
3. **[M] Expression-position `.or_return()`:** extend the existing lowering (check.zen:1342+) from let-only to any expression position incl. mid-chain; same-E rule; check-error outside Result-returning fns.
4. **[M] Spawn-always-Result sweep:** delete `try_spawn` (actor.zen:275) + coroutine.zen `try_*` family; migrate all callsites to `.or_return()`/`.expect(msg)`; oracle green.
5. **[M] Prescriptive escape-checker + promotion verbs:** ship `.share(rt)` / `.give(rt)` and make every escape rejection print the one-token fix verbatim. This is the entire teaching surface of the two-memory model; keep the checker adversarially tested — it is load-bearing.
6. **[L] rt ergonomics decisions (design doc before code):** attenuated `self.rt` inside behaviors (nested spawn), `rt.region((r){...})` for non-actor scratch, and the official library convention for "fn needs shared memory" — decide before users improvise.