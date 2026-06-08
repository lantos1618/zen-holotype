/* Generic value-case runner for a loader-flattened Zen program: zenc emits the flat program into
 * prog_body.c (via -I); this TU prepends the C int/bool types and calls prog_main(), returning it as the
 * process exit code so a shell harness checks $?. Pure libc — the program's whole std closure is in the
 * flattened body. (No <stdio.h>, so no SEEK_SET/SEEK_END macro clash with std.io constants.) */
#include <stdint.h>
#include <stdbool.h>

int32_t prog_main(void);

#include "prog_body.c"

int main(void) { return prog_main(); }
