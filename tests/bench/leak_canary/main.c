/* THE POSITIVE CONTROL FOR `make leak` (tests/bench/leak.sh).
 *
 * WHY A GATE NEEDS ONE AT ALL. The detector is not a property of the binary
 * you meant to test; it is a property of the process valgrind ACTUALLY runs,
 * and nothing in `valgrind $BIN` checks that $BIN is what got
 * instrumented. Point the gate at any ordinary executable -- a wrapper on
 * PATH, a stale path, a copy of the compiler built without anything in it --
 * and valgrind runs that program to completion, reports zero errors, and
 * exits 0 over a compiler it never examined. The gate then reads exactly
 * like a clean tree. Silence must mean "the detector ran and found
 * nothing", never "nothing was being detected", so the script proves the
 * detector speaks BEFORE trusting its silence: it runs THIS file first,
 * with the same flag string, and refuses to gate unless both substrings in
 * main.reports come back.
 *
 * The bug is deliberately shaped like a REAL leak and unlike the two
 * allowed ones: malloc called from a helper one frame below main, the same
 * depth at which a leak anywhere in the compiler would sit. That is also
 * the second thing the canary asserts -- valgrind.supp may only ever
 * suppress a malloc whose caller IS generated main, so if the suppression
 * file is ever widened enough to swallow this block too, the canary goes
 * quiet and the gate refuses to run instead of passing over everything.
 */

#include <stdlib.h>

static void leak_canary(void) {
    /* 64 deliberate bytes, never freed. */
    (void)malloc(64);
}

int main(void) {
    leak_canary();
    return 0;
}
