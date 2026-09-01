/* Positive control for the ASan/LSan and Valgrind gates. The allocation must
 * remain unreachable so both detectors prove that a silent compiler run is
 * genuinely clean rather than uninstrumented. */

#include <stdlib.h>

static void leak_canary(void) {
    void *leaked = malloc(64);
    if (!leaked) abort();
}

int main(void) {
    leak_canary();
    return 0;
}
