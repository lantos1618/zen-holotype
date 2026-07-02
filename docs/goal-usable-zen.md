# GOAL: Make Zen Usable — close the expressiveness gaps

**Where we are (main d9b0f15, 52 PRs):** Zen is now *trustworthy* (sound checker —
pointer kinds, UAF, no accepts-invalid), *correct* (miscompiles fixed), and *clean*
(one formatter, deduped). The compiler is fixpoint-tight and self-validating. But it's
still ~4.5/10 to **write** in: sound, not expressive. **This goal: make Zen a language
you can write real programs in.**

**Verified gaps (probed live):**
- Closures aren't first-class: `error[lambda-value]: a lambda can only be used directly
  as a call argument`. Can't return, store, or compose functions.
- No higher-order stdlib: `xs.map(f)` → undefined.
- No turbofish `f<i64>(x)`; no `str + str`; floats print ~6 digits.

## KEYSTONE — first-class closures (M1)
The one unlock. A lambda must become a VALUE: returnable, storable, passable. Needs
closure conversion (env struct + fn pointer; capture by value). Today capturing lambdas
work ONLY as direct call args — lift that restriction. This single feature unblocks
map/filter/fold, callbacks, returned functions, builders — the bulk of "real" code.

## Milestones (compiler-core SERIALIZED; each oracle + fixpoint + PR gated)
- **M1 Closures** (keystone): lambda → first-class value. `make_adder = (b: i64) (i64) i64
  { (x: i64) i64 { x + b } }` returns + calls.
- **M2 HOF stdlib**: `map`/`filter`/`fold`/`each`/`find` on slices + Vec, backed by M1.
  Allocator-threaded, no hidden heap.
- **M3 Generics ergonomics**: turbofish `f<T>(x)`; generalize `Map<K,V>` (IntMap exists);
  explicit type-args where inference fails.
- **M4 Strings & numbers**: explicit-allocator `str` concat (`a.cat`/builder, NOT hidden
  `+`); shortest-round-trip float formatting.
- **M5 Polish + census**: remaining low-tier (gen-helper dedup, synonym sprawl, precedence
  doc); re-score usability; tee up the next big swing (type-sets).

## GATES (non-negotiable, hard-won this session)
- Every PR: isolated `make oracle` ALL PASS + seed byte-exact fixpoint + `--build-self`
  (zero over-rejection on the compiler's own source) + examples/demos run unchanged.
- **Ergonomics is a VETO**: no change that worsens the surface or adds hidden heap.
- Serialize compiler-core (check/parse/genc = one writer per file); parallelize
  std/tests/docs. Agents commit INCREMENTALLY (the env kills long agents).
- Adversarially verify (a fix isn't done until the repro flips). **Re-scout after each
  wave** — round 2 found 8 regressions in round 1's own work; this WILL recur.

**Done = you can write a real program** — an HOF data pipeline, callbacks, a small CLI —
in Zen without hitting a wall. ~4.5/10 → 7/10.
