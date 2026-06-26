# Resolver Namespacing — Design

> **STATUS: implemented.** The resolver namespacing described here has since landed. This doc is kept
> for design history / rationale.

*Status (at time of writing): design only, read-only investigation. Author: design agent, 2026-06-22.*
*Target file for the real doc: `docs/namespacing-design.md`.*

## Executive summary

Zen's resolver is a **source-text concatenator**, not a symbol-table linker. Any
import — `{ a, b } = std.x` *or* `x = std.x` — causes the resolver to read the
ENTIRE source of `std/x.zen` (and, transitively, every module it imports),
strip the import lines, and **append the whole module body** into one flat
translation unit. The `{ a, b }` list only *validates* that `x` exports `a` and
`b`; it does **not** filter what gets pulled in. The backend then emits every
top-level function with its name *verbatim* (`c_func_name` is identity except
`main`→`zen_main`), so the flat TU lives in C's single global namespace.
Consequently every top-level name in a module's *entire transitive closure*
becomes a global, and a user definition that happens to share a name with any of
them (`at`, `len`, `words`, `get`, `sum`) is rejected as `dup-fn`. The
namespace-qualified form `x = std.x` only prefixes `x`'s *own* directly-declared
names (`alias__name`), **not** the names it pulls in transitively — so it does
*not* currently fix the collision either (verified: `t = std.text.fmt` + a user
`at` still errors, because `at` is `std.text.str`'s export flattened in through
fmt). **Recommendation: extend the existing namespace-prefix rewrite to cover a
module's full transitive closure, and make `{ a }`-named imports lower to the
same prefixed closure with the named symbols additionally aliased into the
caller's scope.** This is a resolver-layer (source-text) change — the backend
needs no new mangling — but it is byte-exact-seed-HIGH-risk because it renames
nearly every symbol in the seed.

---

## 1. Current mechanism — exactly how import + flattening works

### 1.1 The model: text in, flat text out

The whole resolver (`zen/std/internal/resolve.zen`, ~2080 lines) operates on raw
source **strings**, before parsing. The public entry is
`resolve_program_data(a, root, progdir, inpath, mainsrc)` → `ResolvedProgram {
table, flat, body_start, body_end }`. `flat` is a single concatenated source
string that is then handed to `parse_module` / the checker / genc. There is no
per-module symbol table at emit time; correctness depends entirely on the `flat`
string having globally-unique top-level names.

### 1.2 Two import line shapes

`module_graph(src)` scans the source for two kinds of top-of-file lines
(`ImportEdge { module, alias, namespace, start, next }`):

- **Named import** — `{ println, print } = std.text.fmt`
  Detected by `is_import_line` (an `opens_import` `{` followed by a real
  `} = std./compiler./<user>` marker). `namespace = false`, `alias = ""`.
  The brace list is parsed into `ProvidedSymbol{ imported: true }` head symbols.
- **Namespace import** — `t = std.text.fmt`
  Detected by `is_ns_line` (bare ident `=` then a module marker).
  `namespace = true`, `alias = "t"`.

### 1.3 How `{ println } = std.text.fmt` makes `println` callable

It does **not** do anything targeted. `load_import_graph` →
`load_import_edges` → for each *non-namespace* edge → `load_closure(id)`:

```
load_closure(id):
  src   = read_module("zen/std/text/fmt.zen")
  graph = module_graph(src)                 # fmt's own imports + provided symbols
  c3    = load_import_graph(... )            # RECURSE into fmt's imports first
  ns    = collect_ns_graph(...)             # handle fmt's own namespace binds
  body  = strip_ns_into(src, ...)           # fmt source MINUS its import/ns lines
  out  += body                               # <-- APPEND WHOLE fmt BODY
```

So the *entire* body of `fmt.zen` (every top-level decl, not just `println`) is
concatenated into `out`. `println` becomes callable because it is now a global
function in the flat TU. The named list `{ println }` is consumed **only** by
`check_head` / `check_import_names` (line ~1535): it asserts `fmt` actually
*provides* `println` (else `fail_unknown_name`), and registers it for the
user-shadow dup check (`user_decls_from_symbols` → `fail_dup_user`). It performs
no filtering of fmt's other exports.

### 1.4 Why the WHOLE module's exports become top-level

Because `load_closure` appends the full stripped body and recurses into fmt's
own imports first (depth-first), the flat program ends up containing the full
**transitive closure**: fmt's body + str's body + bytes's body + string's body +
num's body + result's body + everything they import. `dedup_decls_mode`
(line 1684) then walks the flat text and, per top-level name, keeps the first
definition and drops later duplicates (so a diamond dependency pulled in twice
appears once). `internal_source_path` / `allow_main_shadow` lets the *entry*
module's own definition win over a dependency's (used so std/compiler entry
modules can own a natural export name over their dependency closure).

### 1.5 Why `at` collides even when not imported

User writes `{ println } = std.text.fmt` and defines a top-level `at`.
`fmt.zen` line 7 is `{ view, at } = std.text.str`, and `at*` is exported by
`std/text/str.zen` (and `std/text/bytes.zen`). Loading fmt's closure flattens
`str.zen`'s entire body — including `at` — into the global namespace,
*unprefixed*. The user's `at` is then the second top-level definition of that
name → `fail_dup_user` / `error[dup-fn]`. The user never typed `at`; it leaked
in through fmt's transitive dependency. **Verified** against the live binary
(`zenc build /tmp/coll.zen`): `error[dup-fn]: duplicate top-level definition`.

### 1.6 What the namespace form already does (the existing prefix machinery)

The `t = std.text.fmt` path is richer and is the seed of the fix. In
`load_ns_edge` / `alias_module_body` / `rewrite_alias_names` / `rewrite_quals`:

- The bound module's **own declared names** (`graph.decl_names_in` =
  non-imported decls) are rewritten in its body to `t__name`
  (`alias_name` → `alias` + `"__"` + `name`).
- Call sites `t.foo()` are rewritten to `t__foo()` (`rewrite_quals`,
  gated on `is_qual_access`: a `.` followed by `(` so only *member-call*
  qualifications rewrite). Bare type/qualifier references can be stripped
  (`strip_qnames` / `strip_all_quals`; e.g. `std.io.c` aliases get fully
  elided).

So Zen **already mangles** module-bound names as `alias__name` in the source
text. **Critically, the backend does NOT mangle** — `c_func_name` in
`genc_emit.zen` emits the name verbatim. All uniqueness is manufactured in the
resolver's text layer.

**The gap:** `load_ns_edge` prefixes only fmt's *direct* decls. It still calls
`load_ns_closure_graph` → `load_import_graph`, which flattens fmt's transitive
imports (str, bytes, …) **unprefixed**. Verified: `t = std.text.fmt` + user
`at` *still* errors `dup-fn`, because `at` belongs to `str`, not `fmt`, and
arrives flat. So namespacing today is shallow — one level deep.

---

## 2. The rule we propose

**Goal:** an import brings ONLY the named symbols into the caller's top-level
namespace; every other name in the module (and its closure) stays
module-qualified and cannot collide.

### 2.1 Semantics

- `{ a, b } = std.x` — `a` and `b` are usable bare in the caller. Everything
  else `x` (and `x`'s closure) defines is **not** visible bare; it exists in the
  flat TU under a mangled name and is reachable only through the module's
  internal cross-references.
- `x = std.x` — nothing is bare. `x.foo()` reaches `foo`; `foo` exists under its
  mangled name.
- A user top-level `at`/`len`/`words` collides **only** with another *bare*
  name the user actually imported or defined — never with a transitive
  dependency's internals.

### 2.2 How a module's internal cross-references still resolve

Today they resolve because everything is flat and unprefixed. Under prefixing,
each module M is rewritten as a unit: every top-level name M *declares* becomes
`M__name`, and every *reference* inside M to one of its own declared names (or
to a name it imported) is rewritten to the same mangled form. This is exactly
what `rewrite_alias_names` already does for the one-level namespace case — it
walks M's body, and for each identifier that is in M's `decl_names` (or the
relevant imported set) emits the prefixed form, while skipping comments and
string literals. The change is to apply this rewrite to **every** module in the
closure (keyed by the module's canonical id, e.g. `std__text__str`), not just
the directly-bound one, and to rewrite cross-*module* references (M calls N's
export `f`) to N's prefix `std__text__N__f`.

### 2.3 How UFCS methods still dispatch (the hard part)

UFCS lowers `b.op(args)` to a free call `op(b, args)` (check.zen ~845; trait
dispatch `method_in` / `impl_cname_in` ~335). So `op` must be findable by the
name written at the call site. Two sub-cases:

1. **`op` is a named-imported symbol** (`{ op } = std.x`): the caller wrote
   `b.op(...)`; `op` is aliased bare into the caller, so it resolves — its alias
   points at `std__x__op`. Fine.
2. **`op` is an *unimported* method of a namespace-qualified module**
   (`x = std.x`, user writes `b.op(...)` expecting x's UFCS method): `op` is now
   `std__x__op` and is *not* bare. Today this "works" only because everything is
   flat. Under strict prefixing, `b.op()` would fail to resolve.

This is the central correctness constraint. Options:

- **(A) UFCS resolves against the union of bare names + all closure methods.**
  Keep a method index (receiver-type-keyed) that the checker can consult even
  for non-bare names, so `b.op()` finds `std__x__op` by `(typeof b, "op")`. This
  preserves today's "any visible impl method dispatches" behavior without making
  the method's *name* bare. Trait impls already carry the receiver type
  (`impl_cname_in(trname, ty, method)`), so the index exists in spirit. This is
  the principled answer: **UFCS dispatch is type-directed, not name-directed**,
  so prefixing the C symbol need not break it as long as the checker resolves
  `(type, method)` → mangled cname.
- **(B) UFCS only dispatches to bare (imported/defined) free fns.** Simpler, but
  a behavior change: you'd have to `{ op } = std.x` to use x's UFCS extension
  methods. Likely too restrictive for the stdlib's heavy UFCS style.

**Recommend (A):** mangle the C symbol, but resolve UFCS by receiver type +
method name against the whole closure's method/impl set. Bare-name lookup is
only for *direct* calls `foo()`.

### 2.4 Reconciling with the flat single-TU model

The backend stays one TU with one C namespace. We do **not** add backend
mangling. Instead the resolver guarantees uniqueness by prefixing every
non-bare top-level name with its module id in the **source text**, before parse
— identical in spirit to the existing `alias__name` rewrite, generalized to the
full closure and keyed by module id. After rewriting, `dedup_decls` still runs
(diamond deps of the *same* module now share the same prefix, so they dedupe
correctly and exactly once).

---

## 3. Mangling / emission scheme

### 3.1 Proposed mangling

- Canonical module id → prefix: `std/text/str` → `std__text__str__`.
- A module's own declared top-level name `at` → `std__text__str__at`.
- Bare (imported into caller / user-defined / `main`) names keep their short
  name. `main` continues to special-case to `zen_main`.
- Call-site resolution:
  - `foo()` bare → resolve in {user decls, names imported into this module} →
    if it's an imported export, rewrite to that export's mangled name.
  - `x.foo()` (namespace) → `std__x__foo()` (today's `rewrite_quals`, extended
    to the full id prefix).
  - `b.op(...)` (UFCS) → checker resolves `(typeof b, op)` to the mangled cname
    via the method/impl index (§2.3-A); not a text rewrite but a check-pass
    binding.

### 3.2 Confirm the four hard features still work

- **UFCS** — works via type-directed dispatch (§2.3-A). The desugar
  `op(b,args)` binds to the resolved mangled name.
- **Trait dispatch** — already keyed by `(trname, ty, method)` →
  `impl_cname_in`; impl method cnames are already synthesized, so prefixing
  free fns is orthogonal. Trait method names were never bare-global anyway.
- **Generics / monomorphization** — `mono.zen` specializes by appending type
  args to a base name (`mangle_str_in`). As long as the *base* name is the
  module-prefixed one, instances stay unique. No conflict; the prefix is just a
  longer base.
- **The compiler's own self-build** — the compiler modules import each other
  *heavily* with named imports (`parse.zen` imports ~40 names from
  `compiler.genc`). Under the rule those imported names become bare aliases in
  each importer, pointing at `compiler__genc__<name>`. This must round-trip
  byte-exactly through the seed (see §4).

---

## 4. Migration & risk

### 4.1 What breaks

- **Every std + compiler module** uses named imports as its primary style and
  relies on the *current* flat-everything behavior in subtle places (e.g. a
  module calling a transitive dependency's export *without* importing it,
  because it happened to be flattened in). Any such "accidental" reference
  becomes a hard `unknown name` once names are prefixed. These must be found and
  fixed (add the missing import or qualify) — this is the bulk of the work and
  cannot be fully enumerated statically without running the change.
- **UFCS on unimported methods** anywhere in the tree (§2.3-2) must be caught by
  the type-directed dispatch index; any spot the index misses becomes a build
  error.
- **`std.io.c` / FFI shims** already lean on `strip_all_quals`; the FFI-foreign
  decls (`dforeign`) must be excluded from prefixing (foreign C names like
  `malloc` must stay verbatim — `ProvidedSymbol.foreign` already tracks this).

### 4.2 Incremental vs big-bang

The *mechanism* can be staged, but the *cutover* is effectively big-bang per
build, because the seed is byte-exact: you cannot have half the modules prefixed
and half flat and still produce the identical seed. Recommended staging:

1. Land the generalized closure-prefix rewrite **behind the existing
   namespace-import path only** (fix §1.6's shallow bug first: make
   `t = std.x` prefix x's *full* closure, not just x's direct decls). This alone
   makes `x = std.x` actually collision-proof and is independently valuable.
2. Add the type-directed UFCS index so unimported methods still dispatch.
3. Flip named imports `{ a } = std.x` to "alias-only" lowering (named symbols
   bare, rest prefixed). This is the byte-exact-seed-breaking step.
4. Regenerate the seed; fixpoint to byte-exact; fix every leaked `unknown name`.

### 4.3 Byte-exact-seed risk — **HIGH**

This renames nearly every symbol in the emitted C, so the seed changes wholesale
in one commit. The repo's correctness oracle is byte-exact fixpoint + the binary
oracle corpus. Plan: regenerate seed, run full fixpoint, expect a large but
*mechanical* diff (every `std__…` name appears). The danger is a *silent*
mis-rewrite (a string-literal or comment identifier wrongly prefixed, or a
missed UFCS dispatch that compiles to a different-but-valid call) — these won't
fail the build, only the oracle. Mitigate by leaning on the existing
comment/quote-skipping in `rewrite_alias_names` (already battle-tested) and by
diffing the pre/post emitted C for *unexpected* (non-prefix) changes.

---

## 5. Alternatives & recommendation

**(a) Full closure prefixing of non-bare names (this design).**
Pro: actually solves the problem; reuses existing `alias__name` machinery;
no backend change. Con: HIGH seed risk; UFCS-on-unimported needs the
type-directed index; large mechanical migration.

**(b) Keep flat; just detect collisions better.** Improve the error
(`fail_dup_user`) to name the *offending dependency* and suggest a rename, maybe
auto-suffix the user's symbol. Pro: trivial, low risk. Con: does **not** fix the
problem — users still cannot define `at`/`len`/`words`; it only makes the
rejection friendlier. Non-solution for the stated goal.

**(c) Per-module C namespace via prefix-only-on-collision.** Only prefix a
transitive name when it would actually clash with a user/other-module name.
Pro: minimal seed churn (most names stay short → small diff). Con: prefixing
becomes *context-dependent and non-local* — whether `at` is `at` or
`std__text__str__at` depends on what else is in the program, so a module's
emitted text isn't stable across programs; this complicates dedup, caching, and
reasoning, and the seed (which IS a program) still churns for every genuine
clash. Fragile.

### Recommendation

**Adopt (a), staged as in §4.2, starting with the §1.6 fix (deep-prefix the
namespace-import closure) as an independently shippable first cut.** That first
step (a) closes the real-world `x = std.x` collision, (b) exercises the
full-closure prefix rewrite on a small blast radius before touching named
imports, and (c) requires no UFCS-dispatch change *if* we scope the first cut to
namespace imports of leaf-ish modules. Sequence the named-import flip
(seed-breaking) only after the type-directed UFCS index lands.

**First-cut scope:**
1. Generalize `rewrite_alias_names` + `collect_ns_edges` so a namespace bind
   `t = std.x` prefixes x's *entire transitive closure* with per-module ids,
   not just x's direct decls. Cross-module refs inside the closure rewrite to
   the callee module's prefix.
2. Verify `t = std.text.fmt` + user `at` builds (the §1.6 repro).
3. Hold named-import semantics unchanged in cut 1 (still flat) to keep the seed
   stable; only the namespace path changes.
4. Measure the seed diff; if the namespace path isn't used in the seed's hot
   paths the diff is small and de-risks the later named-import flip.

---

## Open questions for lead + user

1. **UFCS reach:** do we accept (A) "UFCS dispatches type-directed against the
   whole closure even for non-imported methods" (preserves today's ergonomics,
   more checker work), or (B) "UFCS only on bare/imported free fns" (simpler,
   forces explicit `{ method } = std.x` for extension methods)? This decides how
   invasive the check-pass change is.
2. **Migration appetite:** OK with a single big-bang seed-rename commit (HIGH
   risk, large mechanical diff) gated on byte-exact fixpoint + oracle, or do we
   want the staged §4.2 path that ships the namespace-only fix first and defers
   the named-import flip?
3. **Mangling spelling & limits:** prefix as `std__text__str__at`? Names get
   long; any C identifier-length or readability concern for emitted C / debug?
   (Alternative: a short hash, but that hurts the readable-C-output property.)
4. **Should named imports even change?** Given (b)/(c) exist: is the user's
   actual pain solved *enough* by making `x = std.x` namespace imports
   collision-proof (cut 1) + a better dup error, leaving `{ a } = std.x` as
   today? I.e. is the goal "users can write `at`" (cut 1 + qualify) or
   "named imports are truly scoped" (full design)?
