/* Value-case runner for tests/oracle.zen (the Zen-native correctness oracle).
 *
 * The oracle runs `zenc emit <case.zen>` to produce the case's C body at /tmp/zo_body.c, then
 * compiles THIS file (which #includes that body) and runs it: main() prints `test()`'s integer to
 * stdout, which the oracle compares to the expected value. Mirrors tests/_oracle.py's _RUNNER + shim.
 *
 * Build:  cc -std=gnu11 -w -I/tmp tests/oracle_runner.c -o /tmp/zo_prog   (-I/tmp finds zo_body.c)
 */
#include <stdint.h>
#include <stdbool.h>
/* The one runtime symbol lowered value-case code can reach: `eq` (str content equality — `a == b`
 * on strs lowers to a call to eq(a, b)). No zenrt.c is linked into the standalone runner. */
static bool eq(const char* a, const char* b){ for (; *a && *a == *b; a++, b++); return *a == *b; }
#include "zo_body.c"
#include <stdio.h>
int main(void){ printf("%lld", (long long)(test())); return 0; }
