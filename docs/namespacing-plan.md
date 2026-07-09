# Namespacing plan (#68 wave 2)

Zen has **one flat symbol namespace**. `zenc` builds a program by *textually flattening* every
imported module (transitively) into a single translation unit: `zen/std/internal/resolve.zen` strips
import lines and concatenates the module sources, then the checker (`zen/compiler/check.zen`) builds a
`DeclIndex` (name → decl array index) over the concatenated decls. There is no per-module scope: after
flattening, every top-level name — user helpers, every `*`-exported std fn, **and every generic
function's type-parameter name** — lives in one global pool keyed by a bare identifier.

Three user-visible symptoms all fall out of that single design fact. This document reproduces each,
diagnoses the shared root, decides whether a full per-module-scoped-resolution redesign is required (it
is **not** — the three are separately, surgically fixable), sequences the fixes, and records the one
slice implemented in this PR.

---

## The three symptoms (all reproduced on `origin/main`)

### Symptom 1 — `T`/`A` stdlib-poisoning (zero attribution)

```
$ cat t.zen
{ println } = std.text.fmt
T: { x: i32 }
main = () i32 { v := T(x: 5)  println("hi")  v.x }

$ zenc check t.zen
zenc: ./zen/std/text/fmt.zen:107:28: error[trait-bound]: type `T` does not implement trait
      `Display` (which declares `fmt_print`) …
  print*<T> = (x: T) i64 { x.fmt_print() }
```

A user type named `T` makes an error point **into `fmt.zen`**, with no attribution to the user's file.
`A` does the same into `alloc.zen`/`str.zen`. A type named `Zqxw` compiles fine.

**Diagnosis.** `T` is the *tparam name* of `print*<T>` (and `A` of `try_acquire*<A>`, etc.). Generic
tparam names are fn-local, but in the flat namespace they are **not scoped to their function** — so a
user's global type `T` and the tparam `T` are the same identifier. In `check_validate.zen`,
`unknown_ty(Named("T"))` calls `env_named_declared("T")`; normally `T` is not a declared type →
"unknown" → the `x.fmt_print()` call is correctly **deferred** to monomorphization. Once the user
defines a global struct `T`, `env_named_declared("T")` returns true → `T` looks *concrete* →
`trait_recv_missing` fires and rejects the abstract tparam as if it were the user's struct. The tparam
is not shadowing the global type inside its own function's body, because the checker's `Env`
(`vars/decls/didx/exp/a`) carries **no notion of the enclosing function's tparams** at the deep call
sites where `unknown_ty` runs.

### Symptom 2 — UFCS resolves to the wrong receiver type

```
$ cat t2.zen
{ println } = std.text.fmt
main = () i32 { xs: [i32] := [1,2,3]  r := xs.find(2)  println("done")  0 }

$ zenc check t2.zen
zenc: t2.zen:5:10: error[arg-type]: expected `str`, got `[i32]`
  r := xs.find(2)
```

`xs.find(2)` on a `[i32]` silently binds to `std.text.str.find(s: str, needle: str)` — the wrong
receiver type — because `find` is a single flat entry.

**Diagnosis.** UFCS lowering (`MethodCall → Call`) resolves `x.m(...)` to the *bare name* `m` in the
flat namespace. `find` has exactly one flat binding (`str.find`), so the receiver type `[i32]` is
ignored: there is no per-receiver-type method table, only a global name → decl index. When a slice
method and a `str` method share a name, the flat entry wins regardless of receiver. (This is the same
family as #13/#15: the flat namespace cannot hold two same-named methods distinguished by receiver.)

### Symptom 3 — O(n²) compile (50k trivial fns never finish)

Valid before/after wall-clock (`zenc check`, N trivial top-level fns, both binaries co-located with
`zen/std` so module resolution is identical):

| N      | origin/main | this PR | note                         |
|--------|-------------|---------|------------------------------|
| 4 000  | 4.0 s       | 2.5 s   |                              |
| 8 000  | 11.7 s      | 5.9 s   |                              |
| 16 000 | 34.4 s      | 10.4 s  | origin/main ≈ 2.9×/doubling  |
| 50 000 | never finishes (>4 min, then stack-overflows) | ~linear tail | |

origin/main scales at ≈2.9× per doubling (quadratic). gprof (real workload) attributes the dominant
cost to **`shadow_rename_set`** in `resolve.zen`:

```
shadow_rename_set → seen_name → seen_scan   4.28 s / 4.92 s  (57 037 of 65 660 seen_name calls)
                    snext_line              171 M calls
```

**Diagnosis.** The flat-namespace **shadow-rename pass** (the #1 newcomer-collision fix: auto-rename a
user helper whose name collides with an *unimported, transitively-pulled-in* std export to
`zshadow__name`) builds several **newline-delimited `String` "seen sets"** (`mainseen`, `nonmain`,
`allnames`, `imported`, `maindup`) and tests membership with `seen_name`, which **linearly scans the
whole set string** (`snext_line` walks byte-by-byte). Over N flattened symbols it does N membership
tests against O(N) sets → **O(n²)**. This is the direct consequence of the flat namespace: the pass
exists only because there is one global pool, and it was written with linear String sets.

---

## Shared root, and whether a full redesign is required

**Shared root:** the flat single-identifier namespace with no per-scope resolution — user names, all std
exports, and generic tparam names collide in one pool; and the pool is queried/deduped by linear scans.

**Is a full per-module-scoped-resolution redesign required?** **No.** A big-bang rewrite of
`resolve.zen`/`DeclIndex` into true per-module scopes is high-risk (the resolver is load-bearing for
`--build-self`) and unnecessary — the three symptoms decouple cleanly:

- **Symptom 3 is purely algorithmic** and fully fixable *inside the existing flat design* by swapping
  the linear-scan `String` sets for O(1) hash sets. No scoping semantics change. **(Done here.)**
- **Symptom 1 is a scoping bug with a contained fix**: give a generic function's tparams a *local
  scope* that shadows global type names, by threading the enclosing fn's tparam names to the
  `unknown_ty`/`env_named_declared` decision (either an `Env` field or a reserved-key marker in the
  `VList`, mirroring the existing `"0return"` trick). No change to the flat model for ordinary names.
- **Symptom 2 needs receiver-typed method dispatch**, i.e. UFCS candidate selection must key on the
  receiver type, not just the bare name. The infrastructure already exists for *alias*-based UFCS
  (`alias_ufcs_candidates`, `dispatch_recv`, `tparam_names_have`); the gap is that a **plain flat
  method** is chosen by name alone. This is the largest of the three but is still a localized change to
  UFCS lowering + a per-receiver candidate filter — not a namespace redesign.

So: **keep the flat namespace; fix the three symptoms surgically.** A future per-module scope would
*subsume* all three, but is not on the critical path and carries far more `--build-self` risk.

---

## Sequenced plan

1. **[DONE, this PR] Symptom 3 — hash-set the shadow-rename pass.** Replace the five newline-delimited
   `String` seen-sets in `shadow_rename_set` (+ its two builders) with `Map<i64>` presence sets
   (`rset_*` helpers). Removes the dominant O(n²). Lowest risk, biggest scalability win, zero semantic
   change (byte-exact seed fixpoint + full oracle).

2. **Symptom 3, follow-up — the remaining resolver/checker O(n²) scans.** After (1), gprof shows the
   cost spread across several *separate* linear scans, each its own contained slice:
   - `dedup_symbols` (`resolve.zen`) — same `seen_name` newline-`String` pattern; reuse `rset_*`.
   - `fn_dup_before` (`check_validate.zen`, 3 call sites) — per-decl "scan all earlier decls for a
     same name" duplicate check; replace the scan with a `Map<i64>` count/first-index built once.
   - `find_genenum` / `the_func` (`check.zen`) — linear decls scans that survive for the few
     Env-less callers; index them like `DeclIndex`.
   - `dispatch_recv` — linear impl scan; key on `impl_idx`.
   These are independent and can be fanned out; none is a namespace change.

3. **Symptom 1 — scope generic tparams to their function.** Thread the enclosing fn's tparam names into
   the checker so `unknown_ty(Named(n))` treats `n` as abstract when `n` is a current tparam, even if a
   global type of that name exists (a tparam shadows a global type *inside its own fn body* — correct
   language semantics). Preferred mechanism: a reserved-key marker in the body `Env`'s `VList` (like
   `bind_fnret`'s `"0return"`), set where function-body envs are built (`check_func`,
   `kv_check_func_kind`, and the `resolve_module` inference env), consulted in `env_named_declared`.
   Contained to the checker; must be validated against every std generic (full oracle + fixpoint).

4. **Symptom 2 — receiver-typed UFCS dispatch.** Extend UFCS lowering so `x.m(...)` selects among *all*
   flat `m` candidates by receiver-type fit (the `fits`/`dispatch_recv_name` machinery already used for
   alias-UFCS), falling back to the current single-binding behavior when exactly one candidate exists.
   Largest blast radius; do last, behind the two cheaper wins.

5. **(Optional, long-horizon) True per-module scopes.** Would subsume 1–4 but is a load-bearing rewrite
   of `resolve.zen`; only justified if flat-namespace collisions keep recurring after 1–4.

---

## Slice implemented in this PR

**Symptom 3, step 1: `shadow_rename_set` O(n²) → O(n).** Chosen over symptom 1 because it is the
genuinely *most contained, lowest-risk, highest-value* slice:

- **Contained** to one function + two builders in `resolve.zen`; symptom 1's fix touches the checker's
  core `Env` (29 `Env(...)` construction sites) and the type-checking of *every* std generic — a much
  broader blast radius against a strict fixpoint/oracle gate.
- **Purely algorithmic, zero semantic change.** The seen-sets are pure membership tests over *clean,
  NUL-terminated identifier keys* (minted by `symbol_key_in`/`symbol_name_alloc`), so a content-hashed
  `Map<i64>` matches the old explicit-length `String` comparison byte-for-byte. `out` (the rename list
  the rewrite consumes) stays a newline-delimited `String`; only its membership *checks* become O(1)
  via a parallel `outset` mirror.
- **Verified fix:** 16k-fn compile 34.4 s → 10.4 s; the dominant `shadow_rename→seen_scan` (was 4.28 s
  of 4.92 s) is gone. Shadow-rename behavior preserved: a user `len` colliding with std's transitive
  `len*` still auto-shadows and runs; a user-vs-user dup and an explicitly-imported collision still
  raise `dup-fn`. Byte-exact seed fixpoint; full oracle green; whole-tree fmt clean.

Symptoms 1 and 2 are diagnosed and repro-confirmed above and sequenced as steps 3 and 4; they are left
unimplemented here to keep this PR a single low-risk slice against the load-bearing resolver.
