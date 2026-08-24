# match-exhaust

tests/corpus/match-exhaust/arms_shuffled_against_declaration_order -- arm chain emitted in a different member order than the tags were assigned in (canonical-vs-declaration tag numbering); an arm misdispatches and "11 22 30"/"63" changes.
tests/corpus/match-exhaust/binder_arm_hands_the_whole_value_on -- the binder arm forwards a stale or wrong-width slot instead of the scrutinee; `Blue` arrives at the second match wearing `Red`'s words and "cool" becomes garbage.
tests/corpus/match-exhaust/nested_arms_cover_every_path_without_wildcard -- inner dispatch reads one shared payload slot across outer cases; Right's three answers collapse onto Left's (42/505/17).
tests/corpus/match-exhaust/wildcard_mid_chain_still_guards_its_case -- a mid-chain `_` is emitted as the unconditional else without its case guard; `Gone` answers "RO".
tests/corpus/match-exhaust/literal_arms_and_wildcard_remainder -- a literal comparison emitted at 32 bits instead of 64; 4294967297 aliases arm `1` and its line answers 10, 2147483648/i64.MAX answer 99.
tests/corpus/match-exhaust/three_levels_of_pattern_fully_covered -- specialisation drops or misreads a column below depth two; Right's answers (904/55/66) collapse onto Left's or Gone's 77 drifts.

## Notes on what could NOT be tested here, and why

Truly-unreachable and duplicate arms are compile-time REJECTIONS
(`SemaFault.UnreachableArm`, sema_match.zen check_reachable), so they belong to
must-fail, not corpus: a corpus test must run and print. Their runtime half is
what this lane pins instead -- that correctly-ordered arms still dispatch right
(arms_shuffled...), that wildcards mid-chain keep guarding their own case
(wildcard_mid_chain...), and that binders forward the whole scrutinee.

Two shapes were written, run, and thrown away for encoding a wrong premise:

1. NAMED CASES AFTER AN EARLY WILDCARD. First drafted with a binder arm
   (`whatever =>`) then a bare `_` first and `Red`/`Blue` after it: Zen rejects
   both, and it is RIGHT. A wildcard -- bare `_` or binder (`WildPat covers a
   bare _ AND a binder`, sema_match.zen:56-57) -- covers every value, so every
   arm after one is genuinely unreachable. There is no legal program whose
   runtime behaviour distinguishes "early wildcard swallowed dispatch" from
   correct emission; the mid-chain form (wildcard_mid_chain...) is the closest
   legal cousin and that one ships.

2. A NEGATIVE LITERAL PATTERN (`-1 => ..`). Rejected at PARSE: "expected a
   pattern". The tree-sitter grammar agrees -- `_pattern` (grammar.json) admits
   number_literal/string_literal/char_literal/boolean_literal/wildcard/
   destructure/path patterns and no unary minus, so a signed literal is not a
   pattern in Zen by construction. If pattern-position negation is wanted, the
   grammar needs it first; nothing to pin at runtime until then.

No compiler bugs found beyond those two grammar/sema facts: every accepted
program produced exactly the values predicted from DESIGN.md's rules on its
first run.

TESTS: 7
