/* Positive control for the UBSan gate. Volatile operands keep the signed
 * overflow in the executed program so the runtime must diagnose it. */

#include <limits.h>

int main(void) {
    volatile int maximum = INT_MAX;
    volatile int one = 1;
    volatile int overflow = maximum + one;
    return overflow == 0;
}
