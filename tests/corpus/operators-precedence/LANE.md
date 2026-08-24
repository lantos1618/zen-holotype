# lane: operators-precedence

Precedence and associativity pinned against explicit parens, per
docs/TESTING.md § Parser ("one test per operator pair, including +% against
+"). Tier order is grammar/grammar.js D1 / PREC:
|| < && < (== !=) < (< > <= >=) < (+ - +% -%) < (* / % *%) < unary < call/index/member,
all binary operators left-associative. Every .expected is byte-exact stdout
from ./runzen.sh at write time.

- additive_binds_looser_than_multiplicative/main.zen -- move `* / % *%` onto
  the additive precedence row in the parser's binary-operator table; every
  line prints a different small number (`mul` 14->20, `divtrunc` 18->20,
  `sink` 12->4), none rejects.
- binary_operators_group_left/main.zen -- flip prec.left to prec.right for
  the binary expression rule (or make the Pratt loop recurse on equal
  precedence); `divchain` flips 4->16 and `mixed` 12->18.
- comparison_binds_tighter_than_equality/main.zen -- delete the separate
  equality row: merging ==/!= into comparison stops `cmpcmp` from
  compiling; demoting them under additive makes `add_eq` print 1 instead of
  true.
- and_binds_tighter_than_or/main.zen -- move && onto the || row; `andor`
  flips true->false while the paren twin stays true.
- wrapping_ops_share_the_trapping_tier/main.zen -- give `+% -% *%` their own
  precedence row (either direction): lifted, `w2` 18->30; lowered below
  additive, `w1` 11->5.
- postfix_binds_tighter_than_unary/main.zen -- lower call/index/member below
  unary, or fold a constant negation into a call's argument: `negcall`
  -16->16 via the fold, `idxmul` 50->60 via the reorder.
- unary_minus_binds_tighter_than_binary/main.zen -- let prefix `-` take the
  full additive expression as its operand (or hang it on its left
  neighbour): `neg` 1->-5, `suboperand` 7->-13 or reject.
- parentheses_override_every_tier/main.zen -- make parenthesized_expression
  splice its child into the parent so the enclosing loop can reassociate
  across the wall: `p1` 15->13, `p3` 1->5, `wallsub` 11->5.

## Compiler bugs

None found. Every output matched D1 and C semantics; nothing was suppressed.

Two grammar behaviours met while probing, reported not bug-classed:

1. A block-bodied local lambda (`dub = (x: i32) i32 { ... };` inside main)
   is rejected at parse ("a declaration begins with the name it declares");
   helpers must be module-level. That pushed all helper functions in these
   tests to module scope. If locals-with-function-type are meant to be
   legal, this is a parser gap worth its own lane.
2. `.to_i64()` does not resolve on an untyped integer binding (`no to_i64 on
   int`) -- conversions live behind the std.core.num widen_* bounds. Not a
   precedence matter; noted because it shaped which spellings these tests
   could use.

TESTS: 8
