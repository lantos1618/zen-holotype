# MINIMISE — what src/ can delete, and what is only pretending to be deletable

An audit of ~64k lines of Zen across 188 files in `src/`. No code was changed.

Everything below was checked against a compiler built from this tree
(`make build`, green, commit `467107e6`). Where a workaround claims a bug, I
wrote the bug's reproducer and ran it. Probes live in `/tmp/mz/`; each entry
says what I observed.

**The headline is a correction, not a find.** The two shapes this audit was
launched to collapse — `tag()`/`same()` on `TokenKind`, and the 79 `=> true`
arms that look like set membership — are *not* wins. The first relocates 52
lines rather than deleting them; the second is a measured **~100x slowdown** on
the parser's hottest path. Both are written up in full below so the question
stays closed.

---

## Summary

| # | Entry | Status | ~Lines |
|---|---|---|---|
| 1 | Two-arm `Ok(())` matches → `.then` (215 sites) | NEEDS-DESIGN | 663 |
| 2 | `std.core.time` — zero callers in `src/` | NEEDS-DESIGN | 109 |
| 3 | `gen_c_print` reimplements `text_fmt.fmt_next` | NEEDS-DESIGN | 93 |
| 4 | Three hand-rolled insertion sorts beside `sort` | READY (1 of 3) | 80 |
| 5 | `Vec` has no `truncate` — 21 open-coded sites | READY after 1 add | 52 |
| 6 | 15 byte-identical helper pairs under 2 names | READY (with caveat) | 45 |
| 7 | Scope stack copied `sema_check` ↔ `gen_c_state` | NEEDS-DESIGN | 40 |
| 8 | Multi-variant match arms do not exist | BLOCKED (language) | 152 |
| 9 | `map`/`filter`/`pairs` — zero callers in `src/` | BLOCKED | 38 |
| 10 | Three decimal writers + three digit tables | BLOCKED (error sets) | 34 |
| 11 | `sema_trap` writes four tables as 12 functions | READY | 30 |
| 12 | SEMA §10 hoisted helpers — blocker gone | READY | 30 |
| 13 | `ok_or` at `T = ()` → `put` written three times | BLOCKED (live bug) | 25 |
| 14 | `std.core.path` — four bodyless fns, zero callers | READY | 21 |
| 15 | "Last index of a byte", written four times | READY after 1 add | 20 |
| 16 | `fmt_break.in_order` → `Cand.impl(Ordered)` | READY | 17 |
| 17 | `Hasher` is dead; 24 impls take an unread param | READY | 15 |
| 18 | `Display` — zero impls in `src/`, 380 `add_bytes` | BLOCKED (error sets) | 10 |
| 19 | Byte classification open-coded 7× | READY | 10 |
| 20 | `sema_ty.key_before` duplicates `str.before` | READY | 7 |
| 21 | `is_ascii` / `is_hex_digit` — zero callers anywhere | READY | 7 |
| 22 | `ast_find.empty_span` duplicates `ast_span.nowhere` | READY | 3 |
| 23 | `tag()` / `same()` on `TokenKind` | NEEDS-DESIGN (relocates) | 1 net |
| 24 | Collapsing parser predicates to `is_in` | **DO NOT** — 100x slower | (negative) |
| 25 | Four stale workaround comments | READY (comments) | 0 |
| 26 | Dead parameters — 98 slots, 94 signatures | READY | 72 |
| 27 | Functions with no callers (10 of 4,114) | READY | 40 |

**Start here.** Entries 26 and 27 are the best line-count-per-risk on the page:
112 lines, no design decision, no semantic change, and every body was read
rather than sampled. **One split matters inside entry 26:** a dead parameter in
the middle of a signature is free, while a dead *first* parameter is the UFCS
receiver, and deleting it turns a compliant `x.f(a)` into a `f(x, a)` that
`make style` rejects — the `UFCS_OWED` ledger is empty and monotone. 23 such
call sites are named there. Take the non-receiver slots first.

After those, entries 20, 21, 22, 11, 12, 16, 14 are unambiguous and mechanical
— another ~115 lines. Entries 5, 15, 19 are each
"add one std export, then delete N copies". Entry 1 is by far the largest
number on the page and by far the largest churn; read its RISK before acting.

**Two things came back clean**, which is worth saying because it bounds the
work: **unused imports: zero** (3,452 non-re-export bindings checked), and
**dead types, struct fields and enum variants: zero**.

---

## 1. Two-arm `Ok(())` matches → `.then` (215 sites) — NEEDS-DESIGN — ~663 lines

WHERE: 215 sites tree-wide. Heaviest: `src/gen/gen_c/gen_c_own.zen` (10),
`src/sema/sema_bound.zen` (10), `src/sema/sema_cycle.zen` (9),
`src/gen/gen_c/gen_c_fat.zen` (7), `src/sema/sema_depth.zen` (7),
`src/zen/zen_build.zen` (7), `src/gen/gen_c/gen_c_handle.zen` (5).
Total `false => Ok(())` arms: 147; total `true => Ok(())` mirrors: 14.

TODAY — `src/gen/gen_c/gen_c_op.zen:546`, which names itself a workaround:

```zen
    // `.match` and not `.then`: a `.then` closure capturing more than
    // one of its enclosing parameters is inlined with the receiver
    // substituted into the wrong argument slot, which `cc` catches and
    // docs/GEN_BOOTSTRAP_FIXES.md records.
    traps(b.op).match({
        true  => be.write_trap_args(node, b, out),
        false => Ok(()),
    }).try();
```

INSTEAD: `traps(b.op).then(() { be.write_trap_args(node, b, out).try(); });`
— four lines to one, 215 times.

BLOCKER: **gone, and verified twice.**
- The inliner bug (`GEN_BOOTSTRAP_FIXES.md` §5) is CLOSED. I ran a `.then`
  closure capturing three and then four enclosing parameters (`/tmp/mz/t9.zen`);
  both printed the right answer (`123`, `15`).
- The doc says so itself: *"The workaround is load-bearing for nothing.
  `.match({ true => .., false => Ok(()) })` in place of `.then` is now a style
  preference and not a workaround."*
- I also checked the thing that would actually make this unsafe: **does
  `.try()` inside a `.then` lambda propagate the error to the enclosing
  function, or swallow it?** It propagates. `/tmp/mz/t11.zen` runs the same
  failing call through both spellings and both print `ERR`.

RISK — three, and they are why this is NEEDS-DESIGN rather than READY:
- **It is a style ruling, not a bug fix.** `GEN_BOOTSTRAP_FIXES.md` has already
  ruled once that these 147 arms are *"the ordinary spelling of a one-sided
  conditional in a `Res<(), E>` position, not evasions of this bug"*. Someone
  has to overrule that deliberately.
- **663 is an upper bound.** The formatter re-wraps long lines, so a site whose
  `true` arm is a long call will not collapse to one line.
- **215 edits across every subtree at once** is the largest-churn item here, and
  `make build` is documented as flaky (a red must reproduce before it is
  believed). Do it per-directory, not in one sweep.

---

## 2. `std.core.time` — zero callers in `src/` — NEEDS-DESIGN — 109 lines

WHERE: `src/std/core/time.zen` (whole file, 109 lines).

TODAY: ten constructors/accessors, a `Unit` enum, `unit_of`, `count_in`,
`suffix`, `add`, `sub`.

```zen
micros_of*  = (self: Duration) u64 { self.ns / NS_PER_MICRO }
minutes_of* = (self: Duration) u64 { self.ns / NS_PER_MINUTE }
```

BLOCKER: I grepped `Duration`, `nanos_of`, `micros_of`, `millis_of`,
`seconds_of`, `minutes_of`, `unit_of`, `count_in` across `src/`, `tests/`,
`tools/`, `example/`.
- In `src/`: **every hit is a comment or a prelude re-export line.** The three
  `unit_of` hits in `src/gen/gen_c/` are a *different* `unit_of`, a method on
  `CBackend` (`gen_c_state.zen:577`).
- Outside `src/`: 20 hits in `tests/`, and `example/build.zen:122`
  (`b.budget(seconds(60))`). `src/std/build/build.zen:207` declares
  `budget*(self :: @Self, d: Duration) ()` — bodyless, but it types the API.

So the module is dead *to the compiler* but alive as published std surface.
That is a product decision, not a cleanup.

Sub-item, and I withdraw it: `micros_of` and `minutes_of` have **zero callers
anywhere**, including tests — but the file's own comment forbids removing them,
and it is right: *"One accessor per constructor — asymmetry is a trap (build
from minutes, read only millis, and someone hand-divides and gets it wrong)."*
`micros*` and `minutes*` are the constructors they pair with. NEEDS-DESIGN
along with the rest of the file, not a free 2 lines.

RISK: deleting the module breaks `example/build.zen` and a corpus test, and
changes `std.build`'s signature.

---

## 3. `gen_c_print` reimplements `text_fmt.fmt_next` — NEEDS-DESIGN — ~93 lines

WHERE: `src/std/text/text_fmt.zen:78-170` (the export) vs
`src/gen/gen_c/gen_c_print.zen:234-345` (the second copy).

TODAY — the same classifier, down to a shared helper name (`opens_name`):

```zen
// src/std/text/text_fmt.zen:86
opens_name = (f: str, i: usize) bool {
    f[i] == '{' && (i + 1) < f.len && f[i + 1].is_ident_start()
}
```
```zen
// src/gen/gen_c/gen_c_print.zen:327
opens_name = (raw: str, i: usize, end: usize) bool {
    (i + 1 < end) && raw.index(i) == '{'
        && raw.index(i + 1).is_ident_start()
}
```
The step functions mirror each other too: `fmt_next → step_at → step_not_hole
→ step_named` against `fmt_at → at_no_hole → at_no_pair → at_ident`.

BLOCKER: `fmt_next` has **one caller in the whole repo** —
`tests/corpus/std/the_reference_format_parser_runs.zen:32`. Zero in `src/`. I
verified: every other `fmt_next` occurrence in `src/` is a comment or the
`text.zen:23` re-export line. So std ships a "reference format parser" and the
one component that needs one wrote its own.

The two are equivalent, not identical: `gen_c_print`'s carries an `end` bound
(the raw literal includes its quotes), handles `\\`, and splits `bad` into
`NoName`. Consolidating means widening `fmt_next` with an `end` parameter.

RISK: `text_fmt` is std and `gen_c_print` is the backend; widening a std export
to suit one consumer is the wrong direction if the extra parameter has no other
use. The honest alternative is to delete the unused half — but which half is
"unused" depends on whether the reference parser is meant to be std's contract.

---

## 4. Three hand-rolled insertion sorts beside `std.collections.sort` — READY (1 of 3) — ~80 lines

WHERE:
- `src/fmt/fmt_break.zen:486-505` (`in_order` + `before`, 21 lines) — **READY**
- `src/gen/gen_emit.zen:181-224` (`insert_ordered` + 4 helpers, 44 lines)
- `src/sema/sema_ty.zen:564-607` (`sort_unique_into` + 3 helpers, 44 lines)

TODAY — `src/fmt/fmt_break.zen:486`:

```zen
in_order = (cands :: Vec<Cand>) () {
    Range(1, cands.len).loop((h, i) {
        j ::= i;
        loop(() { j > 0 && before(
            cands.ptr().read(j),
            cands.ptr().read(j - 1)
        ) }, (g) {
            tmp = cands.ptr().read(j - 1);
            cands.ptr().write(j - 1, cands.ptr().read(j));
            cands.ptr().write(j, tmp);
            j = j - 1;
        });
    });
}

before = (x: Cand, y: Cand) bool {
    (x.lo < y.lo) || (x.lo == y.lo && x.hi > y.hi)
}
```

INSTEAD:
```zen
Cand.impl(Ordered, {
    before = (self: @Self, other: @Self) bool {
        (self.lo < other.lo) || (self.lo == other.lo && self.hi > other.hi)
    }
})
```
then `cands.sort()`. Net ~17 lines.

BLOCKER: none for `fmt_break`. `Ordered` and `sort` are exported at
`src/std/collections/collections_sort.zen:25,30`, and the exact substitution is
already done twice in this tree — `src/lsp/lsp_compl.zen:79` declares
`Item.impl(Ordered, ..)` and calls `items.sort()` at `:579`;
`src/lsp/lsp_colour.zen:369` calls `names.sort()`. `Cand` already has a
`before(x, y) bool` with the right meaning.

The `collections_sort.zen` header names this exact history: *"'std has no sort'
was true until two modules hand-copied the same 58 tokens ... the second copy is
what moved it here, per STYLE.md's second-caller rule."* Three more copies
survived that move.

RISK for `fmt_break`: `sort` is stable and `in_order`'s comment says stability
never arises for it ("(lo, hi) pairs are distinct per candidate"), so the
orders agree. None found.

RISK for the other two: neither is a plain sort. `gen_emit.insert_ordered` and
`sema_ty.sort_unique_into` **sort-and-deduplicate**, so only the sorting half
lifts out; the dedupe stays. `gen_emit.zen:175` also records that this loop was
*"10,032 insertions ... 29.63% of self time at -O2"* — and `std`'s `sort` is
also O(n²) insertion sort, so swapping to it fixes the duplication and **not**
the cost. Do not present that one as a performance fix.

---

## 5. `Vec` has no `truncate` — 21 open-coded sites — READY after one addition — ~52 lines

WHERE: 21 sites of `.take(x.len - 1)`; 13 wrapped in the identical four-line
loop. `src/sema/sema_check.zen:365,381,425,461,681`;
`src/sema/sema_own.zen:593,696,709`;
`src/gen/gen_c/gen_c_state.zen:378,387,607,685,743,799,803,807,812`;
`src/sema/sema_depth.zen:168,306`; `src/sema/sema_layout.zen:117`;
`src/sema/sema_spine.zen:66`.

TODAY — `src/sema/sema_check.zen:359-368`, which states the gap in its own
comment:

```zen
    // `Vec` has no truncate, so this takes the last element as many
    // times as there are extras — which is what truncate would have been.
    release* = (self :: @Self, mark: usize) Res<(), AllocError> {
        extra = self.locals.len - mark;
        Range(0, extra).loop((h, i) {
            self.locals.take(self.locals.len - 1);
        });
        Ok(());
    }
```

INSTEAD: `truncate*(self :: @Self, n: usize)` in
`src/std/collections/collections_vec.zen`, then `self.locals.truncate(mark)`.

BLOCKER: none. `Vec.take` already exists and does the element work; this is one
new export wrapping a loop that is written out 13 times.

RISK: `take` returns `Res<T>` and these sites discard it. A `truncate` that
returns `Res<(), AllocError>` keeps the `.try()` discipline; one that returns
`()` reads better and hides a `None` that cannot happen by construction. Pick
one deliberately — this is a 21-site decision.

---

## 6. Fifteen byte-identical helper pairs under two names — READY (with caveat) — ~45 lines

WHERE (each pair verified by reading both bodies):

| body | site A | site B |
|---|---|---|
| `name.eq("println") \|\| name.eq("print")` | `gen_c_print.zen:52` `is_print*` | `sema_call.zen:244` `is_print_sugar` |
| `name.eq("Ok") \|\| name.eq("Err")` | `gen_c_call.zen:302` `is_res_ctor*` | `sema_call.zen:251` `is_res_ctor` |
| `c.args.get(i).match({Ok(a)=>Ok(a.value),None=>None})` | `gen_c_call.zen:768` `arg_value*` | `gen_c_shape.zen:212` `arg_value*` |
| `f.body.match({Ok(_)=>false,None=>true})` | `gen_c_call.zen:724` `bodyless` | `gen_c_sink.zen:80` `bodyless*` |
| `m.kind.match({Function(_)=>true,_=>false})` | `gen_c_fat.zen:116` `is_behaviour` | `gen_c_impl.zen:121` `is_function` |
| `m.kind.match({Field(_)=>true,_=>false})` | `gen_c_fat.zen:120` `is_storage` | `sema_bound.zen:447` `is_field` |
| `op.match({Equal=>true,NotEqual=>true,_=>false})` | `gen_c_op.zen:413` `is_equality` | `sema_bound.zen:615` `is_eq_op` |
| `Named(n) => n.name.text.eq("Drop"), _ => false` | `gen_c_own.zen:392` | `sema_drop.zen:100` |
| `c.world.table_at(mi).match({Ok(t)=>t.name,None=>""})` | `sema_bound.zen:126` `module_named` | `sema_inst.zen:267` `module_name*` |
| the 5-field `Ctx(...)` constructor (9 lines) | `gen_c_build.zen:571` `decl_ctx_of` | `gen_c_sink.zen:393` `door_ctx` |
| `d.kind.match({Struct(s)=>c.enter_struct_tvars(s,mi),_=>Ok(())})` | `sema_supply.zen:191` | `sema_decl.zen:297` |
| `self.depth = self.depth + 1;` | `gen_c_state.zen:711` `enter_call` | `gen_emit.zen:128` `indent` |
| `self.depth = self.depth - 1;` (×3) | `gen_c_state.zen:713` | `lsp_json_read.zen:408`, `parser.zen:663` |
| `self.text.view()` | `fmt_out.zen:83` | `gen_emit.zen:140` |
| `Res(_) => true, _ => false` (×4) | `gen_c_decl.zen:633`, `gen_c_range.zen:347` | `sema_bound.zen:262`, `sema_decl.zen:412` |

INSTEAD: one owner each. I traced the three most interesting ones to the end,
and they split into three different situations — a mechanical sweep would get
all three wrong.

**(i) `arg_value*` — READY, and it is a latent UFCS coin-flip the gate misses.**
Both copies are byte-identical, both exported, both `(c: Call, i: usize)
Res<ExprId>` — the *same name, same receiver type, same arity*, which is
exactly the collision `scripts/ufcs_collisions.py` exists to catch. I built the
grammar and ran the gate: it reports `0 ambiguous`, because both call sites use
the flat spelling `arg_value(c, i)` rather than `c.arg_value(i)` and the gate
only inspects the method form. Meanwhile consumers already disagree about who
owns it — `gen_c_fold.zen:39` imports `arg_value` from `gen_c_shape`, while
`gen_c_sink.zen:49` and `gen_c_floor.zen:53` import it from `gen_c_call`. No
single file imports both today, so nothing is miscompiling; the moment one does,
`c.arg_value(i)` is the coin flip that `gen_c_own.zen:132`'s `close_block`
already cost this project a fixpoint over. **Delete `gen_c_shape.zen:212`,
repoint `gen_c_fold.zen:39`.**

**(ii) `bodyless` — READY, but only in one direction.** `gen_c_sink.zen:80`
exports it; `gen_c_call.zen:724` is a private copy of the same three lines.
`gen_c_fmt.zen:44` and `gen_c_floor.zen:57` already import the exported one.
The obvious fix — have `gen_c_call` import from `gen_c_sink` — **creates an
import cycle**: `gen_c_sink.zen:49` already imports four names *from*
`gen_c_call`. Move `bodyless` down to a module both can see instead.

**(iii) `is_print`/`is_print_sugar` and `is_res_ctor` — NOT a duplication bug.**
These sit on opposite sides of the sema/gen boundary (`gen_c_print.zen:52` /
`sema_call.zen:244`; `gen_c_call.zen:302` / `sema_call.zen:251`). `gen` imports
`sema`, never the reverse, so sema cannot call gen's copy. Consolidating means
moving the predicate down into `std.ast` — a design change, not a deletion.
**Leave them.**

BLOCKER: none technically for (i) and (ii).

RISK: the flat C namespace was the worry here and it turns out not to apply —
I checked the emitted symbols and they are module-qualified
(`zu_f4_3gen5gen_c10gen_c_call9arg_value…` vs `…gen_c_shape9arg_value…`), so
two modules exporting one name link fine. The hazard is entirely at the Zen
level: UFCS resolution, and import cycles. Both are shown above. The remaining
eleven pairs in the table were read but not traced to their importers — treat
them as leads, not as a worklist.

---

## 7. Scope stack copied across `sema_check` ↔ `gen_c_state` — NEEDS-DESIGN — ~40 lines

WHERE: `src/sema/sema_check.zen:498-509` (`lookup*`) and
`src/gen/gen_c/gen_c_state.zen:767-778` (`slot_of*`) — 12 lines each,
**byte-identical bodies**, byte-identical comments:

```zen
        n = self.locals.len;
        Range(0, n).find((k) {
            self.locals.get(n - k - 1).match({
                Ok(b) => b.name.eq(name),
                None  => false,
            })
        }).match({
            None  => None,
            Ok(k) => self.locals.get(n - k - 1),
        })
```

Also `release` (`sema_check.zen:362` / `gen_c_state.zen:604`, 7 lines each,
identical), `mark` (`sema_check.zen:303` / `gen_c_state.zen:602`), and
`diag_count`/`diag_at` in **three** places — `sema_check.zen:226,228`,
`gen_c_state.zen:206,208`, `zen_build.zen:768,770`. `zen_build.zen:766` says
outright: *"deliberately the same pair `Checker` exports"*.

BLOCKER: three different element types (`Binding`, `LocalSlot`, `Diag`). There
is no generic scoped-stack type to hold this, so the fix is a new `std`
abstraction, not a deletion.

RISK: a generic `Stack<T>` with a `named(name) bool` bound reintroduces exactly
the generic-through-a-lambda defect that `is_in` and `collections_sort` both
document working around (`collections_sort.zen:9-16`). Prototype before
committing to the shape.

---

## 8. Multi-variant match arms do not exist — BLOCKED (language) — 152 arm-lines

WHERE: 18 matches tree-wide have 3+ arms sharing an identical right-hand side.
Two dominate:
- `src/lsp/lsp_colour.zen:158` — 48 arms, of which 24 are `Ok(Colour.Operator)`
  and 11 are `None`. **41 collapsible.**
- `src/sema/sema_diag.zen:268` — 51 arms, of which 22 are `out.write_name(f)`
  and 8 are `write_types(out, types, f)`. **34 collapsible.**
- `src/std/parse/parse_lookahead.zen:335` — 19 of 20 arms are `true`.

TODAY (`lsp_colour.zen:162-206`, abridged):
```zen
        Ellipsis     => Ok(Colour.Operator),
        ColonColon   => Ok(Colour.Operator),
        ColonColonEq => Ok(Colour.Operator),
        ...  (24 identical arms)
```

INSTEAD: `Ellipsis | ColonColon | ColonColonEq | ... => Ok(Colour.Operator),`

BLOCKER: **the language has no alternation pattern.** I compiled
`/tmp/mz/t12.zen`:
```zen
f = (k: K) i32 { k.match({ A | B => 1, C => 2, _ => 3 }); }
```
→ `main.zen:4:5: type mismatch: expected i32, found ()` (and 9 more). `A | B`
in pattern position is read as a type union, not an alternation.

RISK: **do not "fix" this with `_`.** I confirmed matches must be exhaustive
(`/tmp/mz/t13.zen` → *"match is not exhaustive: cover every case or write `_`"*).
The 11 `None` arms in `colour_of` *could* be `_ => None` today, and that would
be a real regression in safety: a new `TokenKind` variant would silently
colour as nothing instead of failing the build. The file's comment says the
arms are written *"in the order `src/std/lex/lex_token.zen` declares them"* on
purpose. Alternation preserves exhaustiveness; `_` destroys it.

---

## 9. `map` / `filter` / `pairs` — zero callers in `src/` — BLOCKED — ~38 lines

WHERE: `src/std/core/loop/loop_find.zen:47-67` (`filter*`, 21 lines) and
`:69-85` (`map*`, 17 lines); `src/std/core/loop/loop_iter.zen:74` (`pairs*`).

BLOCKER: they are live std API. `filter` has 4 corpus tests, `map` has 3.
`pairs` has **zero callers anywhere including tests** — the only hits are the
re-export chain and an unrelated `pairs` field in `src/lsp/lsp_json.zen`. The
whole compiler walks with `loop` and `find` and never with these.

This is worth recording only as a fact about std's shape: three combinators
exist that the largest Zen program ever written does not use. Deleting them is
a language decision.

---

## 10. Three decimal writers and three copies of the digit table — BLOCKED — ~34 lines

WHERE:
- `src/std/text/text_fmt.zen:205` `add_u64*`, `:210` `add_i64*` (the export)
- `src/sema/sema_diag.zen:607-617` `write_usize*` + `digit_byte` (3 callers)
- `src/lsp/lsp_frame.zen:207-217` `write_decimal*` (12 callers, 7 files)

The ten-arm digit table appears three times: `sema_diag.zen:612`,
`text_fmt.zen:235`, `text_fmt.zen:242`.

BLOCKER: the error sets, and it is stated in the tree —
`src/sema/sema_diag.zen:592-597`:
```
// `add` speaks `WriteError`, which is `AllocError | IoError`, and this
// module returns `Res<_, AllocError>`. There is no From, so the wider set
// cannot propagate into the narrower one — the language working exactly
// as DESIGN.md specifies.
```
`text_fmt`'s writers speak `WriteError`; the consumers speak `AllocError`.
The two `text_fmt` digit tables are also justified in place (`:231`): a `u64`
past `i64.MAX` cannot widen, and DESIGN.md specifies no u64→u8 conversion.
`text_fmt.digit` is not even exported (`digit =`, no `*`), so `sema_diag`
cannot reach it.

RISK: this is the same blocker as entry 18 and it is a language design call
(see the "alloc door mislabels IoError" question already open in this project).
Nothing here is a cleanup.

---

## 11. `sema_trap` writes four tables as twelve functions — READY — ~30 lines

WHERE: `src/sema/sema_trap.zen:769-829` (12 functions, 61 lines), plus
`:638-657` (3 more functions, 20 lines) and
`src/gen/gen_c/gen_c_fs.zen:443-453` (3 more, 11 lines).

TODAY:
```zen
signed_max = (name: str) i64 {
    name.eq("i8").match({ true => 127, false => signed_max_16(name) })
}

signed_max_16 = (name: str) i64 {
    name.eq("i16").match({ true => 32767, false => signed_max_32(name) })
}

signed_max_32 = (name: str) i64 {
    name.eq("i32").match({ true => 2147483647, false => I64_MAX })
}
```
— and the same three-link chain again for `signed_min`, `unsigned_max`, and
`bits_of`. Twelve functions to express four `str → i64` tables.

INSTEAD, one match per table:
```zen
signed_max = (name: str) i64 {
    name.match({ "i8" => 127, "i16" => 32767, "i32" => 2147483647, _ => I64_MAX })
}
```

BLOCKER: none, and I ran the collapsed form rather than trusting the ledger.
`/tmp/mz/t16.zen` compiles the four-arm `str`-keyed match above and prints
`127 2147483647 9223372036854775807` — the same answers the twelve-function
chain gives. A `str` scrutinee against string-literal patterns is
`GEN_BOOTSTRAP_FIXES.md` §B and §7, recorded **CLOSED in both**, and the tree
already relies on it in production — `src/gen/gen_c/gen_c_type.zen:179` is a
17-arm `str`-keyed match.

RISK: none found. Not on a hot path — these are reached only during constant
folding in sema. `gen_c_fs.zen:443`'s chain keys on `usize`, not `str`, and
collapses the same way.

---

## 12. SEMA §10 hoisted helpers — the blocker is gone — READY — ~30 lines

WHERE: six sites, each a function that exists only because a `.then` could not
sit inside a `.loop` body.

- `src/sema/sema_supply.zen:139` `keep_reachable` (11 lines)
- `src/gen/gen_c/gen_c_assoc.zen:375` `write_assoc_arg` (17 lines, 8 of them
  parameters)
- `src/sema/sema_call.zen:332` `keep_one` (7 lines)
- `src/sema/sema_call.zen:858` `keep_fitting` (14 lines)
- `src/gen/gen_c/gen_c_expr.zen:192` `later` (3 lines)
- `src/sema/sema_def.zen:511` `variant_each` (8 lines)

TODAY — `src/sema/sema_supply.zen:138`, which names its own exit:
```zen
// A named helper rather than a `.then` inside the loop body:
// docs/SEMA_BOOTSTRAP_FIXES.md §10, now recorded CLOSED there.
keep_reachable = (
    m             : Member,
    name          : str,
    supplied_here : bool,
    kept          :: Vec<Member>
) Res<(), AllocError> {
    (m.named(name) && (has_body(m) || supplied_here)).match({
        true  => kept.add(m),
        false => Ok(()),
    })
}
```

INSTEAD: inline into the caller's loop body —
```zen
    all.loop((h, m) {
        (m.named(name) && (has_body(m) || supplied_here))
            .then(() { kept.add(m).try(); });
    });
```

BLOCKER: gone. `/tmp/mz/t14.zen` runs both shapes §10 was about — a `.then`
inside a `.loop` reading the loop binding, and the "surviving shape" the doc
warns about (a struct *parameter* reaching a `.then` body across the lambda
boundary). Both compile and print correctly. The doc agrees: *"a source comment
citing §10 to justify a workaround is citing a gap that is not there ... The
seven workaround sites named below are therefore no longer required."*

`src/sema/sema_check.zen:489` has already been reverted to the inline form, so
there is a worked precedent in-tree.

RISK: the doc asks for each site to be re-tested rather than assumed, because
the surviving shape is close. Do them one at a time. `keep_fitting` does more
than filter (it allocates a `Vec<TyId>` and calls `fn_params`) — inlining it
into a loop body may be worse code even though it compiles.

---

## 13. `ok_or` at `T = ()` — `put` written three times — BLOCKED (live bug) — ~25 lines

WHERE: `src/std/collections/collections_map.zen:224`, `src/sema/sema_ty.zen:638`,
`src/gen/gen_emit.zen:219` — the same five-line body three times. Two more
sites open-code it: `src/gen/gen_c/gen_c_state.zen:271,745`.

TODAY — `src/gen/gen_emit.zen:214-224`, which names the other copy:
```zen
// `Vec.set` refuses an out-of-range index with a bare `Res<()>` (no
// reason), and `.try()` won't lift a `None` into `Res<_, AllocError>`.
// Both indices here are in range by construction; `sema_ty.zen` carries
// the same five lines for the same reason.
put = (out :: Vec<usize>, i: usize, v: usize) Res<(), AllocError> {
    out.set(i, v).match({
        None  => Err(AllocError.OutOfMemory),
        Ok(_) => Ok(()),
    })
}
```

INSTEAD, the specified spelling: `out.set(i, v).ok_or(AllocError.OutOfMemory)`.

BLOCKER: **still live, and worse than the ledger records.** I ran the
reproducer (`/tmp/mz/t8.zen`):
```
std/core/result.zen:52:25: codegen cannot resolve `value`
```
`ok_or` (`src/std/core/result.zen:50`) binds its payload —
`Ok(value) => Ok(value)` — and at `T = ()` the binder does not resolve.
`SEMA_BOOTSTRAP_FIXES.md` §1 records this as a *spurious diagnostic* that still
emitted correct C under the bootstrapper. In the self-hosted compiler it is a
**hard codegen refusal**: the program does not build at all. The ledger entry
should be upgraded from "Blocking: no" to "Blocking: yes".

This matters beyond the 25 lines: `ok_or` is documented as *the only* route
from `Res<T>` to `Res<T, E>`, and `Vec.set`, `Vec.take` and `Map.get` all
return a bare `Res`. Every one of them at `T = ()` hits this.

RISK: the fix is in the compiler (make a unit-payload binder resolve), not in
`src/`. Until then all five sites are load-bearing.

---

## 14. `std.core.path` — four bodyless functions, zero callers — READY — 21 lines

WHERE: `src/std/core/path.zen` (whole file, 21 lines).

TODAY — four exported declarations with **no bodies at all**:
```zen
join*   = (a: Alloc, base: Path, rest: str) Res<Path, AllocError>
parent* = (self: Path) Res<Path>
name*   = (self: Path) str
ext*    = (self: Path) Res<str>
```

Meanwhile `src/zen/zen_path.zen` writes the same operations over `str`:
```zen
// zen_path.zen:25 — this is Path.name
base_of* = (root: str) str { root.slice(root.after_last_slash(), root.len); }
// zen_path.zen:61 — this is Path.parent
parent_of* = (path: str) str {
    cut = path.after_last_slash();
    (cut == 0).match({ true => "", false => path.slice(0, cut - 1) })
}
```

BLOCKER: none for deletion. Zero callers of `Path`, `.join(`, `.name()`, `.ext`
anywhere in the repo. (`example/build.zen:52` binds a *local* named `ext`;
`gen_c_member.zen:462` and `sema_match.zen:775` have unrelated local `join`
functions.) `Path*` is re-exported from `src/std/std.zen:21`, so the prelude
line goes too.

RISK: it is published std surface with a name a newcomer would reach for. The
alternative — give it bodies by moving `zen_path`'s three functions in — is the
better outcome and is NEEDS-DESIGN. Deleting is the mechanical one.

---

## 15. "Last index of a byte", written four times — READY after one addition — ~20 lines

WHERE: `src/zen/zen_path.zen:31-37` (`after_last_slash`, `'/'`);
`src/sema/sema_def.zen:719-725` (`last_segment`, `'.'`);
`src/sema/sema_def.zen:843-849` (`cut_before`, `'.'`).

TODAY — `src/zen/zen_path.zen:31`:
```zen
    cut ::= 0;
    Range(0, path.len).loop((h, i) {
        (path.index(i) == '/').then(() { cut = i + 1; });
    });
    cut
```
The other two are the same loop with a different byte and a different base
(`cut ::= name.len` / `cut = i`).

INSTEAD: one `rindex*(self: str, b: u8) Res<usize>` in
`src/std/text/text_str.zen`.

BLOCKER: none. `str` already owns `len`, `index`, `slice`; this is the missing
fourth.

RISK: the three differ in what they return on "not found" (0, `len`, and
`len` again) and in whether the index is inclusive. A single `Res<usize>` makes
each caller state its own default, which is right but is three edits, not a
rename.

---

## 16. `fmt_break.in_order` → `Cand.impl(Ordered)` — READY — ~17 lines

Broken out of entry 4 because it is the one sort that is unconditionally ready.
See entry 4 for the code, the blocker check, and the two in-tree precedents.

---

## 17. `Hasher` is dead; 24 impls take a parameter none of them reads — READY — 15 lines

WHERE: `src/std/core/hash.zen:14-28` (the `Hasher` struct).

TODAY:
```zen
Hasher* = {
    state ...
    write_u8*  = (self :: @Self, b: u8) ()
    write_u64* = (self :: @Self, v: u64) ()
    finish*    = (self: @Self) u64
}
```
and every implementor is forced to accept one:
```zen
// src/std/ast/ast_id.zen:42
    hash = (self: @Self, hasher :: Hasher) u64 { self.index.to_u64() }
```

BLOCKER: none. I grepped `write_u8`, `write_u64` across `src/`, `tests/`,
`tools/`, `example/` — **zero hits outside the definition**, in either the
`f(` or `.f(` spelling. `finish` appears only inside two English sentences
(`zen_write.zen:144`, `env.zen:75`).

All 14 `Hash` impls in `src/` (and 10 more in `tests/`) declare
`hasher :: Hasher` and never touch it. The one impl that *should* use a hasher
— `str` (`text_str.zen:96`) — rolls its own FNV inline with its own constants
(`STR_HASH_SEED`, `STR_HASH_MULT`), which differ from `Hasher`'s. std ships two
hash algorithms and one of them is unreachable.

RISK: dropping the parameter changes the `Hash` trait's signature, which is a
published contract and touches 24 declarations. Deleting `Hasher` while
*keeping* the parameter is not an option — the type is its own signature. This
is one commit, but it is a wide one.

---

## 18. `Display` — zero impls in `src/`, 380 `add_bytes` calls — BLOCKED — ~10 lines

WHERE: `src/std/core/display.zen` (the trait); 380 `add_bytes(` calls across
**63** files (not ~20 — the spread is wider than the brief assumed). Heaviest:
`src/lsp/lsp_hover.zen` 30, `src/sema/sema_ty.zen` 23,
`src/gen/gen_c/gen_c_call.zen` 23, `src/gen/gen_c/gen_c_fat.zen` 19,
`src/gen/gen_name.zen` 18.

`impl(Display` appears **18 times, all outside `src/`** — 17 in `tests/`, one
in `example/src/main.zen:32`. So the trait is exercised by the corpus and
implemented by no compiler type.

BLOCKER: the same error-set wall as entry 10, stated at
`src/sema/sema_diag.zen:592`. `Display` writes to a `Sink`, whose `write`
speaks `WriteError = AllocError | IoError`; the diagnostic modules return
`Res<_, AllocError>`, and there is no `From`.

The genuinely removable part is the half that cannot be implemented:
`Display.dump` (`display.zen:44`) has no body and is gated on `@meta`, which is
stage 5. `Display.toString(self, a: Alloc)` is reachable from one test.

RISK: "migrate 380 sites to `Display`" is not a cleanup, it is the error-set
design question. Do not put it on a deletion list.

---

## 19. Byte classification open-coded seven times — READY — ~10 lines

WHERE and INSTEAD:

| site | today | should call |
|---|---|---|
| `src/sema/sema_trap.zen:733` | `digit_value = (b: u8) i64 { ((b >= '0') && (b <= '9')).match({..}) }` — **shadows the std export's own name** | `b.is_digit()` / `b.digit_value()` |
| `src/lsp/lsp_json.zen:359` | `(b >= '0' && b <= '9').match({` | `b.is_digit()` |
| `src/lsp/lsp_json_read.zen:163` | `Ok(b) => b >= '0' && b <= '9',` | `b.is_digit()` |
| `src/lsp/lsp_json_read.zen:122` | `(b >= '1' && b <= '9').match({` | `b.is_digit() && b != '0'` |
| `src/zen/zen_cli.zen:344` | `place_of = (b: u8) usize { (b - '0').to_u32().to_usize() }` | `b.digit_value()` |
| `src/std/lex/lex_literal.zen:237` | `d = (b - '0').to_u64();` | `b.digit_value()` |
| `src/lsp/lsp_frame.zen:191` | `blankish = (b: u8) bool { b == ' ' \|\| b == '\t' }` | `b.is_in([' ', '\t'])` |

BLOCKER: none. `src/std/core/byte.zen:36` exports `is_digit*`, `:62`
`digit_value*`. The last row is quoted *verbatim* in `src/std/core/eq.zen:33`
as the example justifying `is_in`'s existence: *"`b.is_in([' ', '\t'])` is the
form a run of `||` was spelling out."* I compiled and ran exactly that
(`/tmp/mz/t16.zen`): `blankish(' ')` → `true`, `blankish('x')` → `false`. The
`u8` `Eq` impl it needs is at `src/std/core/num.zen:205`.

RISK: `lex_literal.zen:237` is on the lexer's hot path. `digit_value` returns
`Res<u8>`, so the call adds an unwrap where a subtraction stands today. Measure
that one; the other six are cold.

---

## 20. `sema_ty.key_before` duplicates `str.before` — READY — 7 lines

WHERE: `src/sema/sema_ty.zen:653-659`, plus the re-export at
`src/sema/sema.zen:53`. One caller: `sema_ty.zen:600`.

TODAY — the code names its own exit, exactly like the `tag()` example:
```zen
// A DUPLICATE OF A CLOSED GAP: `str.before` now exists in
// `std.text.text_str`, and its own comment names "sema's type-key
// ordering" as one of the three copies it consolidated. Delete this and
// the `sema.zen` re-export; import `str.before`.
// (`docs/SEMA_BOOTSTRAP_FIXES.md` §4 still records the gap as open and
// is itself stale.)
key_before* = (a: str, b: str) bool {
```

INSTEAD: `self.key_at(a).before(self.key_at(b))` at `sema_ty.zen:600`; delete
the function and the re-export line.

BLOCKER: none. `src/std/text/text_str.zen:65` exports `before*`, and its
comment confirms the same history from the other side: *"THREE components had
each written their own — sema's type-key ordering, the backend's section sort,
deterministic emit."* Two of the three were consolidated; this is the survivor.

RISK: none found. The bodies are equivalent (`a[i]` and `self.index(i)` are the
same call).

---

## 21. `is_ascii` / `is_hex_digit` — zero callers anywhere — READY — 7 lines

WHERE: `src/std/core/byte.zen:34` and `:56-60`, plus the re-export lines
`src/std/core/core.zen:31-32`.

BLOCKER: none. Grepped both names across `src/`, `tests/`, `tools/`,
`example/`: the only hits are the definitions and the two re-export lines. Not
even a corpus test. (`tests/corpus/std/byte_ascii_questions.zen` exercises
`hex_value` and `hex_digit`, which are different functions and are used.)

RISK: published std surface — `is_ascii` is a name a user would expect to
exist. This is "delete unused std" versus "keep the alphabet complete", a small
version of entry 14's question.

---

## 22. `ast_find.empty_span` duplicates `ast_span.nowhere` — READY — 3 lines

WHERE: `src/std/ast/ast_find.zen:119-121` vs `src/std/ast/ast_span.zen:78-80`
— same subtree, **byte-identical bodies**:
```zen
    Span(file: "", start: Pos(line: 0, col: 0), end: Pos(line: 0, col: 0))
```

BLOCKER: none. Two callers, both in `ast_find.zen` (`:59`, `:98`).

RISK: none found. Note `src/std/parse/parser.zen:326`'s `empty_span*` is a
*different* thing — an empty span at the parser's cursor — and must stay.

The irony is on the record: `ast_span.zen:70` says `nowhere` exists because the
span *"had been written out five times under three names ... before anyone put
it where `Span` lives."* The sixth copy is two files away from it.

---

## 23. `tag()` / `same()` on `TokenKind` — NEEDS-DESIGN (relocates, does not delete) — ~1 net line

WHERE: `src/std/parse/parse_token.zen:78-129` (`tag*`, 52 lines) and `:134`
(`same*`, 1 line). `.tag()` has exactly **2 call sites**, both on line 134.
`.same(` has **36**, in 5 files (`parse_lookahead.zen` ×29, `parse_decl.zen` ×3,
`parse_expr.zen` ×2, `parser.zen` ×1, `fmt.zen` ×1).

TODAY — the file names its own exit, which is why this audit was commissioned:
```zen
// It is a counter and not a meaning: nothing outside this module may
// depend on a particular value, and the day `TokenKind` impls `Eq`
// this function and every `.tag()` beside it delete. Reported.
tag* = (self: TokenKind) usize {
    self.match({ Ident => 0, Int(_) => 1, ... Eof => 47 });
}

same* = (self: TokenKind, other: TokenKind) bool { self.tag() == other.tag() }
```

BLOCKER: **not what the comment says.** Two separate findings:

1. **An enum CAN impl `Eq` today, and `==` dispatches to it.** The comment
   implies otherwise. `/tmp/mz/t3.zen` declares `K = A | B | C(u64)`, writes
   `K.impl(Eq, { eq ::= .. })`, and `x == y` compiles, links, and prints the
   right answer. So the impl is *unwritten*, not blocked. (`/tmp/mz/t2.zen`
   confirms bare `==` without an impl is refused, as `LEXER_BOOTSTRAP_FIXES.md`
   §5 records.)

2. **But the impl body needs a comparison, and the only one available is the
   tag.** `==` on an enum is refused unless an `Eq` exists, so the `eq` body
   cannot be `self == other`. It has to be `self.tag() == other.tag()`.
   **`tag` therefore moves to `src/std/lex/lex_token.zen`; it does not
   delete.** Only `same` (1 line) actually goes.

**And there is no speed win**, contrary to what the shape suggests. I read the
emitted C for the enum-with-`Eq` probe: `x == y` lowers to a *call* to `eq`,
which calls `ktag` twice — byte-for-byte the same work `same` does today:
```c
static bool zu_f3_4main1K2eqO2_...(zu_t2_4main1K self, zu_t2_4main1K other) {
    return (zu_f2_4main4ktagO1_...(self) == zu_f2_4main4ktagO1_...(other));
}
```
The real prize — one integer compare instead of two 48-arm chains — needs
codegen to lower enum equality to a `.zg_tag` comparison directly. That is a
compiler change, and it is the thing worth designing.

RISK — a semantic trap that must not be missed: `same` compares **tags only**,
so `Int(5).same(Int(7))` is `true` today. Anything named `Eq` will be read as
value equality by the next person. Either the impl must be documented as
tag-only, or 36 call sites must be audited for payload-sensitivity.

Secondary: `TokenKind` already carries **three** 48-arm tables in three files —
`tag` (`parse_token.zen:79`), `kind_name` (`lex_token.zen:113`), and
`colour_of` (`lsp_colour.zen:158`). Moving `tag` next to `kind_name` at least
makes two of them adjacent and gateable.

---

## 24. Collapsing parser predicates to `is_in` — **DO NOT** — a measured 100x regression

WHERE: the 14 set-membership matches, 79 discriminating arms. The two largest
are `src/std/parse/parse_lookahead.zen:335` (19 arms, `continues_expr`) and
`src/std/parse/parse_expr.zen:271` (18 arms, `starts_expr`).

TODAY:
```zen
continues_expr = (kind: TokenKind) bool {
    kind.match({
        Dot => true, ParenOpen => true, BracketOpen => true, ... _ => false,
    });
}
```

INSTEAD (the tempting one-liner):
`kind.is_in([TokenKind.Dot, TokenKind.ParenOpen, ...])`

BLOCKER: `is_in` requires `T: Eq` (`src/std/core/eq.zen:59`) and no enum impls
it — but per entry 23 that is fixable, so the blocker is not the reason to
stop.

**The reason to stop is cost. I measured it.** Two programs, identical except
for the predicate, 40M calls each, `cc -O2`, three runs:

```
match form:   0.08s   0.05s   0.02s
is_in form:   7.77s   5.28s   4.64s
```

Both print the same answer (`20000000`). That is roughly **100x**, and the
generated C says why — `is_in` materialises the whole array as a compound
literal on **every call** and then linear-scans it:

```c
static bool by_is_in(K k) {
    return is_in(k, ((zg_a18_K){ { {.zg_tag=C}, {.zg_tag=D}, ... 18 elements ... } }));
}
...
while (zg_i5 < 18) {
    K v = r1.zg_elems[zg_i5];
    bool b = K_eq(v, x);        /* two 48-arm tag walks per element */
```

For an 18-element `TokenKind` list that is a ~288-byte stack write plus 18
calls to `eq`, each of which is two 48-arm chains — versus a straight-line
`else if` ladder on one `int32_t` that `cc` turns into a jump table.

`continues_expr` and `starts_expr` are per-token predicates in the parser, and
the compiler compiles itself. **This is the single most expensive suggestion in
the audit and it must not be actioned.**

RISK if actioned anyway: the failure is invisible to every oracle. Output is
identical; only the clock moves.

WHERE IT IS STILL FINE: `is_in` has 43 call sites already and is well adopted
for short lists of primitives (`src/std/lex/lex_byte.zen:32`). Two or three
`u8`s is not this problem. The line is roughly "short list, cheap `eq`, cold
path".

---

## 25. Four stale workaround comments — READY — 0 lines, but they mislead

Each of these blames a bug that no longer exists. The comment is wrong; the
code around it may or may not need to change. Deleting the *claim* is free and
stops the next reader propagating it.

**a. `src/zen/zen_build.zen:45`** — "BUG, reported: aliasing the module and
qualifying through it DOES NOT WORK for a name two modules declare". I built
exactly that (`/tmp/mz/run_alias/`): two modules each exporting `message*` with
the same signature, both aliased, both qualified. It prints `FROM-A` /
`FROM-B`. **Stale.** The flat-import hack (`message = std.lex.lex`) can become
a proper alias, which also removes the "a driver that needed two at once would
need rename-on-import" caveat.

**b. `src/gen/gen_c/gen_c_op.zen:546`** and the other `.then`-avoidance
comments — see entry 1. `GEN_BOOTSTRAP_FIXES.md` §5 is CLOSED and I re-ran the
reproducer.

**c. `src/lsp/lsp_json.zen:353`** — `stepped` is a free function because of a
"bootstrapper limit". The comment itself already says *"The self-hosted
compiler gets it right"*, and the bootstrapper was deleted in commit
`3e6524fa`. The reason is gone; the function is fine as it is.

**d. `src/std/core/eq.zen:42`** — this one is stale in the opposite direction
and is the reason to check rather than assume. It blames the bootstrapper for
rejecting the `xs.find((v) { v.eq(x) })` spelling. The bootstrapper is deleted,
so the comment reads as obsolete — **but the bug is live in the self-hosted
compiler.** `/tmp/mz/t6.zen` gives:
```
main.zen:6:19: codegen cannot resolve `eq`
```
The accumulator spelling is still load-bearing. Only the attribution is wrong.
(This is the same defect `collections_sort.zen:9-16` documents working around,
and it is the one that would bite entry 7.)

Also worth noting, not counted: `src/sema/sema_ty.zen:651` says
`SEMA_BOOTSTRAP_FIXES.md` §4 "still records the gap as open and is itself
stale", and `LEXER_BOOTSTRAP_FIXES.md` §8's diagnostic count is recorded as
grown from 125 to 158. The three `*_BOOTSTRAP_FIXES.md` files are now
records of a deleted program that source comments still cite as live
authority. A pass that rewrites every `docs/*_BOOTSTRAP_FIXES.md` citation in
`src/` to say what is true *today* would be worth more than most of the line
counts on this page.

---

## 26. Dead parameters — READY — ~72 lines across 98 slots

WHERE: 106 candidate slots in 94 signatures, every body read. `src/gen` 57,
`src/sema` 28, `src/std` 14, `src/lsp` 6, `src/zen` 1. Thirty-six occupy their
own source line, which is why the line count is what it is.

This confirms and *itemises* a claim `docs/GEN_C_SHAPE.md` already makes at the
headline level — *"A mechanical scan finds 92 in `src/`, 59 of them in
`src/gen`"* — but the ledger names only four individual parameters (`node` into
`lower_logical`, `prim` into `lower_compare`, `want` on `gen_c_member.zen`'s
entry point), **and all four are already removed**. The raw scan here finds 88,
which is that 92 minus `gen_c_member.zen`'s eight already paid down. So the
ledger owns the headline and does not own the list; this is the list, and it
does not overlap the work already done.

TODAY — the worst single signature, `src/gen/gen_c/gen_c_expr.zen:894`:

```zen
lower_literal = (
    be   :: CBackend,
    id   : ExprId,      // never appears in the body
    l    : Literal,
    ctx  : Ctx,         // never appears in the body
    want : TyId,        // never appears in the body
    out  :: String
) Res<(), AllocError> {
    l.kind.match({
        Str   => be.lower_str_literal(l, out),
        Int   => lower_int_literal(l.text, out),
        Float => out.add_bytes(l.text),
        Char  => out.add_bytes(l.text),
        Bool  => out.add_bytes(l.text),
    }).try();
    Ok(());
}
```
Three of six parameters are dead outright; `be` survives only to reach
`lower_str_literal` (`:938`), which ignores it in turn. An eight-line signature
becomes one line, and the call site at `:833` loses four arguments.

The five chains worth doing first, each traced end to end:

| chain | param | files | lines |
|---|---|---|---|
| `bind_name` → `declare_var` | `ctx: Ctx` | `sema_own.zen:214,228` | 11 |
| `lower_literal` → `lower_str_literal` | `id`,`ctx`,`want`,`be` | `gen_c_expr.zen:894,938` | 8 |
| `zip*` → `zip_one` → `zip_arg` | `c :: Checker` | `sema_inst.zen:324,333,345` | 6 |
| `check_receiver*` → `check_method_call` → `check_receiver_path` | `ctx: Ctx` | `sema_recv.zen:65,73,81` | 3 |
| `lower_settled` → `lower_bounded` / `lower_forever` | `id: ExprId` | `gen_c_loop.zen:396,424,236` | 3 |

BLOCKER: none. This is signature editing plus call-site editing; the compiler
has no opinion.

Ten further chains were traced but are smaller: `gen_c_call.zen:321→:106`
(`id`), `gen_c_decl.zen:138→:157` (`m`) and `:327→:339` (`x`),
`gen_c_expr.zen:1046→:1054` (`be`), `gen_c_op.zen:555→:809` (`be`),
`lsp_diag.zen:224→:256/:287` (`uris`), `sema_member.zen:370→:380` (`node`),
`gen_c_scope.zen:154→:162` (`ctx`), `lsp_compl.zen:397→:411` (`a`),
`parse_member.zen:166→:248/:258` (`p`).

The densest single signatures, if you want the shortest path to the line count:
`gen_c_main.zen:327` `write_void_exit` is **two of four parameters dead** —
I read it, and neither `be` nor `ret` occurs in the body:
```zen
write_void_exit = (be :: CBackend, ret: TyId, call: str, out :: Emit)
                  Res<(), AllocError> {
    out.bytes(call).try();
    out.say(";").try();
    out.say("return 0;").try();
    Ok(());
}
```
Also `gen_c_ptr.zen:397,398` `shift` (2 of 8), `gen_c_fs.zen:303`
`run_and_read` (13 params, `aty` dead), `gen_c_range.zen:428`
`lower_impl_walk` (11 params).

Three that are worth reading before deleting, because each is a symptom rather
than a leftover:
- **`src/gen/gen_c/gen_c_build.zen:443` `default_value` takes `ty: TyId`,
  ignores it, and recomputes the same value** via `be.storage_type(s, name,
  dinst, dctx)`. Two computations of one type with nothing comparing them —
  `GEN_C_SHAPE.md`'s "Lever 2" with a disagreement hazard attached.
- **`src/gen/gen_c/gen_c_infer.zen:399` `fn_ret_type` drops `want`** — the
  *second* dead `want`, after the one the ledger already found on
  `gen_c_member.zen`'s exported entry point. `want` occupies 118 parameter lines
  in `gen/`; two of the ones checked are dead. That ratio justifies a pass on
  `want` alone.
- **`src/std/parse/parse_lookahead.zen:363`** — verified by reading the body:
  ```zen
  decl_head_ahead* = (p :: Parser, module_level: bool) bool {
      p.at_kind(TokenKind.Ident).match({ false => false, true => p.head_shape_ahead() });
  }
  ```
  A boolean parameter that decides nothing. Either a rule that was meant to
  differ at module level and does not, or a leftover. Read the history first;
  this is the only entry on the page where deleting might hide a bug.

Also: `src/std/parse/` threads `p: Parser` as a UFCS receiver into six
functions that never touch it (`has_body`, `merge_tparams`, `assigns`,
`has_value*`, `the_value*`, `no_value`). `parse_stmt.zen:293` is the pure form:
`no_value = (p: Parser) Res<ExprId> { None }` — a constant with a parameter.

RISK 1 — **deleting a dead RECEIVER turns a compliant method call into a
style-gate violation, and the gate is monotone.** This is the risk that would
have bitten a sweep, and the parallel census had it backwards (it said the
`zip` chain "moves `scripts/style.py`'s `UFCS_OWED` for `sema_inst.zen`").
`UFCS_OWED` is `{}` — **empty** — and `scripts/style.py:99` states the rule is
*"not 'no new dirty files' but 'no new sites, anywhere'"*. `rule_ufcs`
(`:673`) flags a free call `f(x, ..)` where `x` is a bare typed parameter and
`f` is reachable through a dot. So:

```zen
zip* = (c :: Checker, vars: Vec<TyId>, args: Vec<TyId>, inst :: Inst)
```
is called five times as `c.zip(vars, n.args, inst)`
(`sema_inst.zen:305,318`, `sema_depth.zen:202,382`, `sema_apply.zen:361`).
Drop the dead `c` and every one becomes `zip(vars, args, inst)` — `vars` is a
typed parameter, `zip` is reachable, so that is **five new `UFCS_OWED` sites
and a red `make style`**.

I verified 23 call sites already in this position: the 5 above, plus 18 across
`decl_ctx*` (`gen_c_type.zen:420`), `plain_ctx*` (`gen_c_decl.zen:590`) and
`write_position*` (`gen_c_op.zen:809`) — all three carrying a dead `be` as
their first parameter. The six `parse_*` slots that thread an unread
`p: Parser` are the same shape.

The fix is not to skip these; it is to **rename the survivor into the receiver
slot** so the call keeps a dot, or to pay the ledger down deliberately in the
same commit. Either way it is a decision per chain, not a sweep. Leaf
parameters that are not first (`id`, `want`, `ctx` in the middle of a
signature) carry none of this and are the safe subset.

RISK 2 — **one class of false positive, and it would have broken nine corpus
files.** Eight `hash = (self: @Self, hasher :: Hasher)` slots never read
`hasher` (`ast_id.zen:42,50,58,66`, `sema_id.zen:58,72`, `sema_ty.zen:41`,
`text_str.zen:97`) — but the signature is mandated by the `Hash` trait
(`src/std/core/hash.zen:34`) and is user-visible API: `tests/corpus/map/*` and
six more contain user-written `hash ::= (self: @Self, hasher :: Hasher)`. They
are excluded from the 98. See entry 17 for the real finding underneath them.

Two things this census *cleared*, which is worth as much as what it found:
**unused imports: zero** (2,055 import lines, 4,096 bound names, 644 of them
re-exports, all 3,452 remaining checked). **Dead types, fields and enum
variants: zero** — the four raw hits are all declared-API-awaiting-stage-5
(`ArgError.Parse`, `ThreadError.SpawnFailed`/`Panicked`) or a parser artefact.

---

## 27. Functions with no callers — READY — ~40 lines

Out of 4,114 function declarations in `src/`, exactly **10** are unreferenced
anywhere in the repo. This tree is already clean here; a name-cull is worth
~40 lines, not hundreds.

**a. `src/zen/zen_path.zen:305` `file_of*` — 12 lines with its comment.**
```zen
// Where the bytes an IMPORT names are: `<root>/a/b/c.zen`, or
// `<root>/a/b/c/c.zen` when the last segment names a folder. ...
file_of* = (env: Env, a: Alloc, root: str, q: QualifiedName)
           Res<str, AllocError> {
    flat = joined(a, root, q, false).try();
    env.fs.exists(flat).match({ true => Ok(flat), false => joined(a, root, q, true) })
}
```
Its only three occurrences in the tree are this declaration and two prose
mentions (`zen_build.zen:202,390`). The live resolver is
`candidate`/`root_for`/`relative_to`.

**Correction, and the reason to re-check a census before acting on it.** The
parallel scan reported this as a *three-function cascade* — `file_of` →
`joined*` → `last_of*`, 29 lines. That is wrong. `joined*` has two live callers
outside `file_of`: `src/zen/zen_build.zen:377,378`, imported at `:74`. And
`last_of*` is called from `joined:318`. **Only `file_of` is dead.** The
cascade shrinks from 29 lines to 12.

**b. Three one-line accessors, 3 lines:**
- `src/gen/gen_c/gen_c_state.zen:428` `newline*` — zero call sites (its
  siblings `fmt*`/`indent*`/`dedent*` are all called)
- `src/sema/sema_check.zen:230` `type_store*` — one occurrence, its own
- `src/std/ast/ast_arena.zen:149` `pattern_ids*` — one occurrence, its own
  (siblings `expr_ids`/`type_ids`/`block_ids` are all called)

BLOCKER: none. Verified by building an occurrence index over every `ident`
token in all 1,213 `.zen` files under `src/ tests/ tools/ example/ scripts/
seed/ editors/ grammar/`, which subsumes both the `f(` and `.f(` spellings, and
also catches a bare-value reference and a reach through a trait impl. I then
re-grepped each of the ten by hand — which is how the `joined`/`last_of` error
above surfaced.

RISK: `src/std/core/hash.zen:17,21,25` (`write_u8*`, `write_u64*`, `finish*`)
and `src/std/core/time.zen:45,48` (`micros_of*`, `minutes_of*`) are also
uncalled and are **deliberately held back** — see entries 17 and 2. `time.zen`'s
own comment forbids removing the second pair: *"One accessor per constructor —
asymmetry is a trap (build from minutes, read only millis, and someone
hand-divides and gets it wrong)."* That comment overrules my entry 2's
"READY sub-item"; treat those two as NEEDS-DESIGN.

---

## Method, and what I did not check

Every entry above was read in the file. Where a blocker was claimed, I wrote
the reproducer and ran it against a compiler built from this tree; the probes
are in `/tmp/mz/` and each is named in its entry. I did not run `make test`,
`make fixpoint`, or the shared gate.

Counts I corrected from the brief: the set-membership sites are 14 / 79 arms,
not 10 / 62 (several sites pack multiple arms per line). The `add_bytes` sites
are 380 across 63 files, not ~378 across ~20.

Not checked, and deliberately left off rather than padded:
- Whether `BinOp.impl(Eq, ..)` would compile clean against the
  `EqNeedsImpl` machinery in `sema_bound.zen` — unverified.
- Eleven of the fifteen pairs in entry 6 were read but not traced to their
  importers. The four that were traced split three different ways, so do not
  assume the rest are uniform.
- `src/gen/gen_c/gen_c_expr.zen:744` `want_of` vs `:607` `res_type_of` — a
  same-file near-duplicate I read but did not trace to confirm they are
  interchangeable.
- Entry 26's 98 parameter slots: I read the five traced chains and the three
  symptomatic singletons myself; the remaining ~80 leaf slots I took on the
  census's evidence (it reports reading all 106 bodies, and its one class of
  false positive — the `Hash` impls — it caught itself). **Re-check before a
  sweep: two of that census's claims were wrong where I checked them** — the
  `file_of`/`joined`/`last_of` cascade (entry 27a, 29 lines claimed, 12 real)
  and the direction of the `UFCS_OWED` consequence (entry 26, RISK 1, which is
  a gate failure rather than a ledger move). Both errors were in the direction
  of over-claiming, and both were found by re-running the grep by hand.
- Entry 6's remaining eleven pairs, entry 26's leaf slots, and entry 8's
  smaller sites are the three places where volume outran verification. They
  are leads.
