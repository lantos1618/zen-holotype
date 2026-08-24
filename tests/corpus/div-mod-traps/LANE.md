# tests/corpus/div-mod-traps

Division and modulo by zero must PANIC, for every integer type. The
existing `traps/` suite pins i32 only; this lane sweeps the other
widths, because the zero-test is emitted per-width by gen_c and each
width fails differently: narrow widths get widened to C ints (the
check can aim at the wrong copy or be skipped), and the 64-bit
unsigned types fit no signed C type (a check typed `int`/`long` never
fires).

Every test follows the house shape from `traps/div_zero_i32.zen`: the
divisor comes from `env.var("ZEN_TRAP_NEVER_SET")` so no constant
folder can turn the runtime trap into a compile error (DESIGN.md: a
provable trap is a compile error), and every program prints real,
hand-checked arithmetic BEFORE trapping -- stdout survives the abort,
so `.expected` is non-empty and discriminates even if only the trap
half breaks.

Each directory holds `main.zen`, `main.expected` (exact stdout),
`main.exit` (134), and `main.stderr` (the trap line; the runner
matches it as a substring, so the `main.zen:L:C:` prefix stays valid
under the harness's staged paths). Verified against the gate:
`python3 tests/run.py --filter 'corpus/div-mod-traps/*'` -> 8 passed.

| path | one-line compiler change that makes it fail |
|---|---|
| div_zero_i8_u8 | skip the zero-check for sub-int widths (they widen to int anyway) -> raw SIGFPE, exit 136, no trap line; or truncate -119/13 toward floor -> `-10 11` instead of `-9 -2` |
| div_zero_i16 | type the divisor check `signed char`/narrowed while the divide runs widened -> garbage high bytes pass the check, silicon faults |
| div_zero_u16 | emit the check on the widened value but the divide narrowed (or vice versa) -> wrong half tested; also any i16-truncating lowering moves `675 60` |
| div_zero_u32 | compute u32 division in signed i32 intermediates -> negative/garbage first line instead of `4 301989883` |
| div_zero_i64 | emit the zero-test as `(int)` / low-32-bit compare of the divisor -> never fires for an 8-byte zero |
| div_zero_u64 | run the divisor test through a SIGNED intermediate (`long`) -> u64.MAX-sized operands read negative, check misses, SIGFPE; also ULL-suffixing regressions move line 1 |
| div_zero_usize | reuse the i32 check "because same machine divide" -> 32-bit test misses the zero in the upper word |
| div_zero_second_iteration | hoist the zero-test out of the loop / emit once per loop-invariant divisor -> iteration 2 kills the process uncaught |

## Not written up as tests (verified fine)

- `i64.MIN / -1` and `i64.MIN % -1`: correctly trapped with
  `integer overflow`, exit 134 -- the i32 fix in traps/ generalised to
  all widths. No gap found.
- `u8`/`u16` cannot hold a runtime `-1` divisor (unsigned negation of
  a literal is rejected), so the "MIN-style unsigned edge" has no
  analogue here; zero really is the only trap divisor for unsigned
  division.

## Compiler bugs

None found. Every width trapped with `trap: divide by zero` at the
operator token, exit 134; stdout printed before the trap always
survived.
TESTS: 8
