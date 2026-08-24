# imports lane

One line per test: path -- the one-line compiler change that would break it.

- duplicate_import_first_binding_wins -- resolve a duplicated bare import by module walk order instead of source (declaration) order, or flip first-wins to last-wins -> 999999999999999.
- field_default_survives_the_boundary -- build gen_c's initialiser list from call-site arguments only and never from the declaration -> `5 0` instead of `5 77`.
- generic_type_imported_and_instantiated -- key monomorphisation on the file that USES the type instead of the file that DECLARES it -> two distinct C structs for one Box<i32>, cc rejects; or truncate u64 storage at the boundary -> 18446744073709551615 becomes garbage.
- imported_constant_folds_through_both_spellings -- fold `Type.NAME` only when the type is declared in the same module -> `value.NAME` falls through to the field path, emits C naming a member the struct does not declare, cc rejects.
- two_declarers_dealt_by_receiver -- key overload resolution on the imported NAME instead of the declared parameter type -> 300 printed twice or 4000 twice.
- type_alone_carries_its_ufcs -- resolve `x.f(..)` in the importing file's bare-name scope before (or instead of) the receiver's type -> ball's decoy wins, prints 4000 not 300.
- unstarred_import_works_in_its_own_module -- drop unstarred bindings from the importing module's own scope (or zero them) -> "cannot resolve double", or 7/0 instead of 22.
- unused_import_still_binds -- treat an import whose bindings are never read as an entry that never resolves -> 0 where u64.MAX should be.

## Suspected compiler bugs / undocumented behaviour found while probing

1. Bare-constructor resolution with two same-named types imported is ORDER-DEPENDENT.
   Two modules each declare `Box*` with identical fields; main writes
   `Box = box.box` then `Box = crate.crate`. A bare call `Box(label: 3)` is typed
   by whichever import comes FIRST in the source: swapping the two lines swaps the
   constructed type (verified both ways: `.describe()` answers 300/300 vs
   3000/4000 depending on order). Nothing rejects or warns; DESIGN.md's law is
   about which names are VISIBLE, and says nothing about the second same-name
   import silently shadowing the first for construction. Program:

       // box/box.zen            // crate/crate.zen
       Box* = {                  Box* = {
           label*: i32,              label*: i32,
                                     describe* = (self: @Self) i32 { self.label * 1000 },
       }                         }
                                 describe* = (b: Box) i32 { b.label * 1000 }

       Box = box.box             // swap these two lines and the answer flips:
       Box = crate.crate         // 300/300 becomes 300/4000
       describe = box.box

       main = (env: Env) Res<i32, IoError> {
           a = Box(label: 3);
           b = Box(label: 4);
           println("{}", a.describe());
           println("{}", b.describe());
           Ok(0);
       }

   The lane's two_declarers test deliberately builds values through per-module
   factories so it does NOT stand on this behaviour; if last-wins (or an error)
   is ever decided, that test still passes but this note should turn into a
   must-fail/expectation pair.

2. Duplicate import of one name: FIRST binding silently wins (pinned by
   duplicate_import_first_binding_wins). No diagnostic, and no way to reach beta's
   `cap` afterwards. Recorded as behaviour, not bug -- but it is undocumented in
   DESIGN.md, and "last wins" would be equally defensible, so it is pinned loudly
   (values differing in every digit).

3. Not a bug, worth knowing: an UNUSED import line compiles fine. STYLE.md makes
   every name on an import line a claimed dependency (a review rule); the language
   itself accepts it and the binding stays live (unused_import_still_binds pins
   that the unused name still resolves to its real value, not a zero).

TESTS: 8
