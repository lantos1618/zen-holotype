# Known compiler limits

Surfaced while building the Colour demo (hex `String` formatting beside a `Canvas` actor).
Each entry is a real, reproducible limit with a minimal repro, the root cause, and the
workaround. Two were FIXED (#4, #2); two are documented LIMITS (#1, #3).

`ZEN_ROOT=<checkout> ./zenc build <file>.zen` / `./zenc run <file>.zen` reproduces all of these.

---

## FIXED — String + actor imports collide on `new_in` (was "BUG #4")

Importing both `std.text.string` and `std.concurrent.actor` produced a cascade of
`error[struct-field]` / `error[arity]` errors, even when used in unrelated code.

Root cause: a flattened program has ONE global decl namespace and NO function overloading
(`func_idx.put` overwrites by name). `std.text.string` exports `new_in`/`try_new_in` (arity-1
`String` builders) and `std.mem.arena` ALSO exported `new_in`/`try_new_in` (arity-2 `Arena`
constructors). `actor` pulls `arena` in transitively (actor → runtime → arena), so both bare
`new_in` decls landed in one TU and `m.addr().new_in()` resolved to the wrong arity.

Fix: arena's constructors were renamed to the type-unique `make_in` / `try_make_in`
(string/rc/arc/own keep `new_in`). The shared `new_in` convention is fine as long as two
same-named allocator-constructors don't reach one flattened program; arena was the one
reachable beside `String`.

---

## FIXED — generic `String` builder chains hung the build (was "BUG #2")

NOTE: this is a DIFFERENT root cause from the recursive-generic limit (#1) below — it is a
template-inliner blow-up, and it is FIXED, not a standing limit.

```
push_byte<A> = (s: String, a: MutPtr<A>, v: u8) String { s.push_in(a, v).push_in(a, v) }
to_hex<A>    = (a: MutPtr<A>) str { a.new_in().push_byte(a,'r').push_byte(a,'g').push_byte(a,'b').finish_in(a) }
```

A deep chain of generic `String`-builder helpers made `zenc build` hang. Generic functions are
inlined templates; `std.text.string.reserve_in` read its `s: String` arg FOUR times
(`s.len`, `s.cap`, `grow_in(s,…)`, `false => s`). When `s` is itself a builder chain, every
nested `.push_in(…)` spliced the whole receiver subtree in 4× — k chained links ≈ 4^k inlined
size (k=2 ≈ 9 s, k=3 timed out).

Fix: `reserve_in` binds `s` to a local once (`s := s`, the same force-once pattern `push_in`
already used for `b`). The receiver is then emitted once per level and the four reads reference
the cheap local, so inlining is linear (an 8-deep chain compiles in ~0.16 s).

General note for stdlib authors: a generic (therefore inlined) function that reads a non-trivial
value parameter more than once should bind it to a local first, or callers passing builder-chain
expressions can trigger super-linear inlined size.

---

## LIMIT — recursive generic functions are not monomorphized ("BUG #1")

```
f = (s: String, a: Allocator, b: i32) String {
    (b <= 0).match({ true => s, false => f(s.push_in(a, 'x'), a, b - 1) })   // self-call
}
```

A generic function that calls ITSELF miscompiles:

* explicit generic (`f<A> = (a: MutPtr<A>, …)` calling `f`) → link error
  `undefined reference to 'f'`;
* the `(a: Allocator)` sugar → C `type mismatch in conditional expression` / `error[arg-type]`.

Root cause: generic functions are realized by INLINING (templates), never emitted as concrete C
functions. `compiler.mono` monomorphizes generic STRUCTS and ENUMS but explicitly skips generic
functions (`mono.zen`: "a generic fn is inlined; skip its T-params"). The inliner breaks
recursion (`check.zen` `maybe_template` → `is_inlining` → `recall`) by emitting a literal call to
the template name `f`, but no concrete `f` is ever generated, so the recursive call dangles.

Note this is reached by allocator-threaded code without writing `<A>` explicitly: `(a: Allocator)`
is sugar for an implicit `<A: Allocator>` generic (`parse.zen` `desugar_trait_params`), so a
RECURSIVE function with an `(a: Allocator)` param is a recursive generic and hits this.

NON-recursive generics are fine — including nested `(a: Allocator)` params threaded through
several calls (the Colour demo's `to_hex` → `push_byte` → `push_in` proves it). Only direct (or
mutual) self-recursion of a generic function is affected.

Workarounds:
* make the helper non-generic (concrete allocator type, e.g. `MutPtr<Heap>`) — a concrete
  function CAN recurse; or
* make the recursion non-generic: keep the generic entry point thin and recurse through a
  concrete inner function; or
* express the repetition with `.loop` / `@while` instead of self-recursion.

Proper fix (roadmap, NOT a demo-scoped change): a function-monomorphization pass — mangle each
recursive generic per concrete type-arg set, rewrite self-calls to the mangled name, and emit the
instances as concrete `DFunc`s (mirroring the struct/enum monomorphizer in `compiler.mono`).
Risky to the byte-exact seed; deferred deliberately.

---

## LIMIT — namespace-qualified type identity ≠ imported type identity ("BUG #3")

```
{ Heap } = std.mem.alloc
mem = std.mem.alloc
use = (h: MutPtr<Heap>) i64 { 42 }
main = () i32 { m := mem.default()  use(m.addr())  0 }   // error[arg-type]
```

The same std type imported two different ways does not unify: `mem.default()` yields a value the
checker treats as `mem.Heap` (emitted `mem__Heap`), distinct from the directly-imported `Heap`,
so `MutPtr<mem.Heap>` does not fit a `MutPtr<Heap>` parameter.

Root cause: a namespace import (`mem = std.mem.alloc`) renames the module's decls per-alias
(`mem__Heap`) so that two DIFFERENT sibling modules can export the same type name without
colliding (this is intentional and load-bearing — see
`test_namespace_bound_siblings_can_export_same_type_name`). The bug only appears when the SAME
module is imported BOTH namespaced AND destructured; the renamed copy and the flat copy are
distinct nominal types.

Workaround: for any one module, pick a SINGLE import style and use it consistently —
either `mem = std.mem.alloc` everywhere (`mem.Heap`, `mem.default()`), or
`{ Heap, default } = std.mem.alloc` everywhere. Don't mix the two for the same module.

Proper fix (roadmap): the resolver should recognize "same module id imported more than one way"
and canonicalize its type identities, without collapsing genuinely-distinct sibling-module types.
Entangled with the namespace design; deferred.
