# Name interning — design (follow-up to the hotspot-kill PR)

Status: DESIGN ONLY. Attempted as Phase 3 of the strlen/strcmp/unify hotspot campaign and
deliberately stopped: `name: string_view` fields appear in **38 files** across
parse/check/mono/backends/resolve — far past the agreed ~15-file blast-radius budget for that PR.
This doc records where the IDs should live and the migration order so the campaign can be run as
its own serialized lane.

## Why (what interning buys, measured 2026-07-23)

After the receiver-inference fix (`gen_call_ret` sharing one arg0 inference) the self-build profile
is no longer dominated by the checker; the remaining string tax is spread thin:

| symbol            | self% | what it is                                        |
|-------------------|------:|---------------------------------------------------|
| `__strcmp_avx2`   |  4.7  | every `==` on names: didx maps, VList, keywords    |
| `line_eq`         |  3.9  | resolve's newline-delimited string sets (O(n^2))   |
| `tok_word_eq`     |  2.9  | lexer/parser keyword compares                      |
| `lookup_var_b`    |  2.7  | checker scope cons-list walk (strcmp per candidate)|
| `mchain`          |  1.2  | Map bucket-chain key compares (strcmp)             |

Interning converts all name equality to integer equality and didx/Map keys to int keys —
realistically worth ~10% of the remaining 2.7s self-build, i.e. a modest win now. It is worth doing
for *architecture* (symbol tables, incremental compilation, LSP) more than for raw speed.

## Where the IDs live

- **`Interner`** — a new `src/compiler/intern.zen`: append-only string table.
  - `Sym` = `i32` newtype (0 = the empty/absent name; IDs are dense, allocation order).
  - storage: one growable byte buffer (all names, NUL-separated) + `[i32]` offsets column +
    a `Map<i32>`-style FNV index for text→Sym on first sight. `sym_text(s) string_view` is an
    O(1) offset load, so *display/emit paths keep working on views*.
  - ownership: the interner is allocated once in the driver and threaded exactly like the
    `Malloc` shim (`a: MutPtr<Malloc>`) already is — an extra field on the parser/checker state
    structs, NOT a global (flat-namespace globals would collide across modules).
- **Producers**: the lexer/parser interns at identifier-token creation (`parse_primary`/
  `parse_type`); resolve interns the names it mints (mangled/shadow names) at `gstr_finish` time.
- **Consumers**: `Param.name`, `VarData.name`, `CallData.fn`, `Func.name`, struct/enum/field/
  variant names, `Ty.Named`/`.Generic` heads, VList cells, didx map keys.

## Migration order (each step independently gated on byte-identical difftest + seed fixpoint)

1. **Interner lands unused** (`intern.zen` + unit coverage in the harness). Zero risk.
2. **didx maps go int-keyed**: `DeclIndex` keys become `Sym`; `env_func`/`idx_*` take `Sym`.
   Contained to check.zen + check_resolve.zen + map call sites; the AST still carries views, the
   didx build interns on insert, lookups intern once per query site (still a net win: one hash per
   name instead of one per map probe).
3. **AST name fields become `Sym`** — the big one, done family-by-family in dependency order:
   a. `Ty` heads (`Named`/`Generic.name`) — touches check_infer/unify (`n == tp` becomes int).
   b. `VarData`/`CallData`/`MemberData` — parse, check, passes, backends.
   c. Decl names (`Func`/`Struct`/`Enum`/`Impl`) + `Param`.
   The C/JS backends and pretty/diagnostics call `sym_text` at their boundary — emitted bytes
   unchanged by construction.
4. **VList/scope**: `VCell.name: Sym`; `lookup_var` becomes int-compare walk (or the array-backed
   scope, which becomes trivial once names are ints).
5. **resolve's string sets** (`line_eq`/`seen_name`) — either intern-keyed sets or the existing
   `rset` Map; this is separable and can go first if resolve grows again.

Steps 2 and 5 are individually shippable and low-risk; step 3 is the >30-file wave and must be a
serialized lane (one agent, compiler core) per the fleet strategy.

## Invariants the migration must keep

- **Byte-identical emitted C** at every step (scripts/difftest.sh OLD/NEW over the full corpus +
  seed fixpoint). Interning is internal; any emitted-C drift is a bug in the step.
- Mangled/synthesized names (`0return`, `0#tp`, inline markers, mangle_str_in output) go through
  the same interner — marker compares become int compares for free.
- The flat C namespace rule: `Sym`, `intern`, `sym_text` are new top-level names — check for
  collisions across the tree before landing (`zen audit` + grep).
- Diagnostics keep rendering through `sym_text`; positions/spans are untouched.
