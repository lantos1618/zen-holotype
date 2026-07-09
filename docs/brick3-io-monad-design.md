# Brick 3 — Can IO / allocation / `Sys` be an effect that composes through `or_return`?

**Status:** design only (no code, no compiler change, no seed regen). 2026-07-09.
**Reads on:** `docs/effects-as-types-design.md` (§5 EFFECTS-AS-STRUCTURE, BLUF) and the #47
Sys/allocator epic (`zen/std/sys.zen`, `zen/compiler/genc_emit.zen`).
**Scope:** the *sequencing* half of the effects model — the half that genuinely composes as a
monad. The *aliasing* half (owned/frozen/mut/read, discharged by `fits`) is Bricks 1–2 and is
NOT a monad; it is out of scope here.

---

## BLUF

**Is an `IO`/`Sys` monad wanted? No.** The one thing a monad buys — *composition of a
sequenced, short-circuiting effect* — is **already shipped** for IO: every fallible IO
operation already returns `Result<T, IoError>`, and `or_return` is already its monadic `bind`
(`check.zen:1718`). So the compositional half of "the IO effect" exists today and is spelled
`Result<T, IoError>` + `.or_return()`. The *other* half — making the `sys` capability itself
flow through a pipeline — is a **reader/environment** effect, and the only mechanism that would
make it *implicit* is precisely the ambient runtime that #47 **deliberately reversed**. Building
an `IO<T>` wrapper to thread `sys` invisibly would re-introduce the magic the team just removed.

**Verdict:** Brick 3 collapses into **"finish #47 well + document that `or_return` already
composes IO-fallibility."** It is **not a new build**. The smallest real next step is
documentation + #47 attenuation work, not a monad. Do **not** add `IO<T>`; do **not** invent an
effect-row system.

---

## 1. GROUNDING (file:line)

### 1.1 `or_return` is literally monadic `bind`

`lower_or_return_let` (`zen/compiler/check.zen:1718-1729`) desugars `x := recv.or_return()` into
three statements:

```
buf[0] = slett(tmp, t, recv2)                                   // (:1725) bind: evaluate  M a  into tmp
buf[1] = sif(cnd, a.one_stmt(sret(a.orret_err_value(...))),     // (:1726) fail / short-circuit:
              no_stmts())                                        //         if tmp.tag == Err { return tmp.Err }
buf[2] = slett(l.name, env.subj_variant_payload(t, "Ok"),       // (:1727) extract  a , continue with (a -> M b):
              a.subj_payload(a.cenode(vref(tmp)), "Ok", ptr))    //         x := tmp.Ok
```

where `cnd` is `tmp.tag == Err` (`:1723`). That is exactly

```
bind : M a → (a → M b) → M b
```

with the function tail after the `let` as the continuation `(a → M b)` and `return Err` as
`fail`. `or_return` is legal in any expression position and hoists innermost-first,
left-to-right (`check.zen:1740-1762`), so it sequences effects in evaluation order — i.e. Zen
already has *do-notation for one effect monad*. This is the single genuinely categorical anchor
of the whole effects model (`effects-as-types-design.md:198-213`).

### 1.2 `Result` and `Opt` are the existing effect monads

Both are ordinary generic enums given monadic structure by combinators + the `or_return`
desugar:

- `Result*<T, E>: Ok(T) | Err(E)` (`zen/std/core/result.zen:3`)
- `Opt*<T>: Some(T) | None` (`zen/std/core/result.zen:4`)
- `and_then` is the explicit bind, spelled out (`result.zen:89-94`):
  `and_then*<T,E,U> = (r: Result<T,E>, f: (T) Result<U,E>) Result<U,E>` — `M a → (a → M b) → M b`.
- `and_then_some` is `Opt`'s bind (`result.zen:145-150`).
- Units: `ok*` (`result.zen:10`), `err*` (`:11`); `map`/`map_err`/`ok_or` (`:74,81,131`) are the
  functor/natural-transformation surface.

So `Result`/`Opt` are monads, `and_then` is their explicit bind, and `or_return` is the
sugar-level bind the compiler lowers.

### 1.3 The CURRENT `Sys` threading — an explicit parameter, NOT a monad

`Sys` is a **plain record** bundling narrow capabilities (`zen/std/sys.zen:96-108`):

```
Sys*: { _out: Writer, _err: Writer, _env: Env, _clock: Clock, _fs: Fs,
        heap = (s: Sys) Heap { gpa() }
        stdout = (s: Sys) Writer { s._out }   ...  }
```

It is passed by an **explicit parameter** at the entry point: `main = (sys: Sys) i32`
(`sys.zen:1,96`; fixture `tests/fixtures/zen/main_sys.zen:9`). The compiler renames the user body
to `zen_user_main(Sys sys)` and appends a **niladic trampoline** that feeds it `root()`
(`genc_emit.zen:611-616, 968-971`):

```
int32_t zen_main(void){ zen__init_globals(); return zen_user_main(<alias>__root()); }   // genc_emit.zen:971
```

so the C boundary (`zenrt.c`) stays byte-identical to the `main = () i32` case
(`genc_emit.zen:565-567`). Downstream, `sys` is **threaded by hand**: a caller passes the
narrowest cap it needs — `greet(sys.stdout())` hands a `Writer`, never the whole `Sys`
(`main_sys.zen:8,10`; the attenuation thesis, `sys.zen:4-6`). There is **no wrapper type, no
bind, no desugar** — the capability is an ordinary value in an ordinary parameter. This is the
#47 thesis in the flesh: *the capability-param IS the effect declaration.*

### 1.4 The load-bearing fact: fallible IO ALREADY returns `Result` and ALREADY composes

Every IO/OS operation in `std.sys` already surfaces failure as `Result<_, IoError>`:

- `Writer.write → Result<i64, IoError>` (`sys.zen:51`), `write_bytes` (`:55`), `write_all`
  (`:38`).
- `Fs.read → Result<str, IoError>` (`sys.zen:90`), `Fs.save → Result<i64, IoError>` (`:91`).
- libc sentinels are lifted to `Result` at the FFI floor: `ok_if` (`result.zen:16`), `ok_ptr`
  (`:18`).

Therefore an effectful IO pipeline **already chains through `or_return` today**:

```
raw := sys.fs().read(h, path).or_return()      // M a → bind
out := sys.fs().save(dst, raw, n).or_return()  //   → (a → M b), Err threads silently
```

The sequencing/short-circuit content of "the IO effect" is **shipped**. What is *not* a monad is
the `sys` value being handed to each step — that is a plain argument.

---

## 2. THE FORK — is Sys/IO already handled, or does it want a monad?

Two honest positions, argued adversarially.

### Position (a): the explicit `Sys` param ALREADY threads the effect — no monad needed

**Claim.** IO/allocation is a *capability* effect, and a capability is honestly modelled as a
**value you must possess** — a parameter. The signature `f = (s: Sys, …) Result<T, IoError>`
already declares, visibly and at the boundary, *both* facets a caller cares about:

1. **"this function performs IO/alloc"** — it demands a `Sys` (or a narrow `Writer`/`Fs`/
   `Allocator`). No `Sys` in scope ⇒ can't call it ⇒ the effect is statically gated. This is
   exactly object-capability discipline: the type of the parameter *is* the permission.
2. **"this function can fail"** — the `Result<T, IoError>` return, composed by `or_return`.

Both are visible in the signature, and both compose with machinery that already exists (argument
passing for the capability, `or_return` for the failure). The *sequencing* of the effects — "do
the read, THEN the write" — is provided for free by the fact that **Zen is strict and impure**:
statements execute in order; there is no laziness to tame, so there is no work for an `IO` monad
to do that the semicolon (newline) doesn't already do. A Haskell `IO` monad exists to *impose an
order on a pure/lazy language*; Zen has order natively. Adding `IO<T>` would be solving a problem
Zen does not have.

**Ethos fit.** #47 killed ambient-rt precisely to keep the IO/alloc effect *visible in the
signature*. "Ceremony you can see > magic you can't." An explicit param is the maximum-visibility
encoding. Position (a) is the status quo and is aligned with every decision the team has already
made (`effects-as-types-design.md:241-243`).

**Adversarial weakness of (a).** The ceremony is real: `sys` (or a narrow cap) must be named in
*every* signature along a call chain that eventually touches IO. A deep pipeline threads `sys`
through ten functions that don't otherwise use it — the classic "parameter tramp." This is the
tax users complain about (`usable-trustworthy-census-2026-07-08.md:43` — allocator/`sys`
threading is the ceremony tax on trivial programs). A monad's whole selling point is to *hide*
that threading.

### Position (b): an `IO<T>` wrapper composed by `or_return` would let pipelines chain without threading `sys`

**Claim.** Model IO as `IO<T>` — a computation that, *given the world*, yields a `T`. Compose
with `or_return`-style bind so an effectful pipeline reads as pure data-flow and the `sys`
plumbing disappears from intermediate signatures:

```
prog : IO<i32> = read(path).and_then(parse).and_then(write(dst))   // no sys in sight
main = (sys: Sys) i32 { prog.run(sys) }                            // sys supplied once, at the edge
```

**Adversarial weakness of (b) — decisive.** Unpack what `IO<T>` must *be* to erase the `sys`
threading. It has to **carry the capability implicitly** — i.e. `IO<T>` is a *reader monad*
`Sys → T` (or `Sys → Result<T,E>`) with the `Sys` argument hidden inside the bind. But "hand the
ambient world to every step without naming it" is **exactly ambient-rt** — the thing #47
reversed. The monad wrapper doesn't remove the magic; it *relocates* it from a global into a
type constructor. The `sys` is still ambient *within the pipeline*; you've just stopped writing
it down. That is the precise property the team rejected: an effect you can no longer *see* at
each site.

Worse, it buys nothing on the failure axis that `Result` + `or_return` doesn't already buy — §1.4
shows fallible IO already composes. So `IO<T>` = (reader monad the team rejected) + (result monad
the team already has). The novel content is 100% the rejected part.

The only *legitimate* residue of (b) is the **ergonomic complaint** — threading `sys` is verbose.
But the sanctioned answer to that is #47's **attenuation** (pass the *narrowest* cap, so most
functions take a `Writer` or an `Allocator`, not the world) plus the niladic-`main` escape hatch
for programs that don't want the capability at all. Attenuation reduces the threading surface
*without* making the effect invisible. That is the Zen-shaped fix.

### Which fits Zen's ethos?

**Position (a).** Decisively. Zen's fixed precedent — killed ambient-rt, rejected `share`/`view`
verbs, "ceremony you can see > magic you can't" — is a standing vote *against* any construct whose
purpose is to hide the capability. `IO<T>`'s only non-redundant feature is hiding the capability.
The explicit `Sys` param *is* the effect declaration, and `Result`+`or_return` *is* the effect
composition. The fork resolves to (a).

---

## 3. IF a monad were wanted — the smallest real shape (and why it's already there)

Suppose, for argument, we want the compositional benefit. What is the *minimum* shape, and is it
new?

**It is not new. The IO monad — the part that is a monad — is already shipped as
`Result<T, IoError>`.** Concretely:

- **Type:** `Result<T, IoError>` (`result.zen:3`, `IoError` `:6`). No new type constructor.
- **Unit (`return`/`pure`):** `ok*` (`result.zen:10`).
- **Bind:** `or_return` (`check.zen:1718`) at sugar level, or `and_then` (`result.zen:89`)
  explicitly.
- **Fail / short-circuit:** `err*` + the Err-guard the desugar emits (`check.zen:1726`).

So the "IO monad" in a strict impure language is *just the fallibility monad over IO-returning
primitives*, and Zen has it. The syntax sketch is **existing surface**:

```
// every step is Result-returning fallible IO; or_return is the bind; no new syntax
copy = (fs: Fs, a: MutPtr<Heap>, src: str, dst: str) Result<i64, IoError> {
    raw := fs.read(a, src).or_return()        // bind:  M a
    n   := raw.view().len                     //        pure step (a -> b), no wrapper
    fs.save(dst, raw, n)                       //        tail is itself M b — no `ok(...)` needed
}
```

**What is genuinely missing vs already there:**

| Facet of "the IO effect" | Status |
|--------------------------|--------|
| Sequencing (do A then B) | **Already there** — Zen is strict; statements order themselves. |
| Short-circuit on failure | **Already there** — `Result` + `or_return` (`check.zen:1718`). |
| Failure *type* visible at boundary | **Already there** — `Result<T, IoError>` return. |
| Capability visible at boundary | **Already there** — `sys`/narrow-cap parameter (#47). |
| Capability threaded *implicitly* | **Deliberately absent** — that is ambient-rt, reversed by #47. |
| Static "this fn does IO" gate | **Already there** — you cannot call it without a cap in scope. |

The only column an `IO<T>` monad would add is the one marked *deliberately absent*. There is no
genuinely-missing compositional capability. A new monad type would be **redundant on five rows and
regressive on the sixth.**

**Does it need new syntax?** No. It reuses `Result`/`or_return` machinery wholesale
(`check.zen:1718`, `result.zen:3-11,89`). Any "new syntax" would exist only to hide `sys`, i.e.
to build the reader monad §2(b) rejected.

---

## 4. HONEST VERDICT

**Brick 3 is not a real new buildable thing. It collapses into "#47 done well" +
"document that `or_return` already composes IO-fallibility."**

The reasoning, stated sharply:

1. **The monad already exists.** Fallible IO returns `Result<T, IoError>` today
   (`sys.zen:38,51,90,91`), and `or_return` is its bind (`check.zen:1718`). The compositional /
   sequencing half of the IO effect is **shipped**, not pending.

2. **The remaining half is not a monad — it's a capability, and #47 already models it the
   Zen-correct way:** an explicit parameter, visible at the boundary
   (`sys.zen:96`, `genc_emit.zen:565-616`). The capability *is* the effect declaration.

3. **The only thing an `IO<T>` wrapper would add is implicit capability threading — a reader
   monad — which is exactly the ambient-rt that #47 reversed.** Building it would undo a decision,
   not extend the model. It is regressive against the "ceremony you can see" ethos.

4. **The real user pain (threading `sys`) has a sanctioned, non-monadic fix already in #47:
   attenuation** — pass the narrowest cap (`Writer`/`Fs`/`Allocator`), not the world
   (`sys.zen:4-6`, `main_sys.zen:8`), plus the niladic-`main` escape hatch. That shrinks the
   threading surface without hiding the effect.

**Smallest real next step (NOT a new build):**

> **(i) Finish #47's attenuation story** — make narrow-cap parameters the idiomatic default so
> most functions take a `Writer`/`Fs`/`Allocator`, never the whole `Sys`; and **(ii) add one
> documentation note** (in `sys.zen`'s header and/or the effects doc) stating plainly: *"the IO
> effect's composition is `Result<T, IoError>` + `or_return`; the IO effect's capability is the
> `Sys`/narrow-cap parameter; there is no separate `IO` monad and there will not be one, because
> its only novel content — implicit capability threading — is the ambient-rt we removed."*

This is documentation + finishing an in-flight epic. It commits to **no** new type, **no** new
syntax, **no** desugar change, **no** effect-row engine.

**Explicitly out of bounds (do NOT build):**

- An `IO<T>` / reader-monad wrapper that hides `sys`. (= ambient-rt, reversed by #47.)
- An effect-row inference system (Koka-style). (Rejected by ethos and budget in
  `effects-as-types-design.md:241-243,330-336`.)
- Any "unified effect algebra" folding alloc+io+mut+send+own into one mechanism. (The aliasing
  half is a poset discharged by `fits`, not a monad — `effects-as-types-design.md:215-227`.)

**One honest caveat.** If, after attenuation, real programs still show painful `sys`-tramping
through IO-free intermediate layers, the *smallest* future lever is **not** a monad but a
narrower ergonomic aid on the existing param model (e.g. a lint that flags passing `Sys` where a
narrow cap suffices, or a struct that bundles the few caps a subsystem needs). Those stay on the
*explicit-value* side of the line #47 drew. The line itself — visible capability, no implicit
world — should not move.

---

## Appendix — the two halves of the effects model, located

| Half | Structure | Mechanism | Composition | This brick? |
|------|-----------|-----------|-------------|-------------|
| **Aliasing** (owned/frozen/mut/read) | refinement lattice (poset) | `mode_of` + `fits` (`check.zen:4540`) | *discharged*, not composed | Bricks 1–2 |
| **Sequencing** (Result/Opt, fallible IO) | monad | `or_return` = bind (`check.zen:1718`) | genuinely composes | **Brick 3 — already shipped** |
| **Capability** (Sys/alloc/io) | value you possess | explicit param (`sys.zen:96`, #47) | threaded by hand (attenuated) | **Brick 3 — #47, not a monad** |

Brick 3's honest content is the bottom two rows: the monadic row is **done** (`Result` +
`or_return`), the capability row is **#47** (explicit param). There is no third thing to build.
