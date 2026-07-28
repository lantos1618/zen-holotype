/* OOM / allocation-failure injection shim (LD_PRELOAD).
 *
 * Intercepts malloc/calloc/realloc and makes the Nth allocation return NULL, so a single, precise
 * allocation-failure point can be forced without touching the program. Zen's design claim is
 * "OOM-as-value": every allocation returns a Result the caller must handle. This shim tests it — if
 * a failing allocation is handled it should surface a clean value/error; if it is NOT handled it
 * null-derefs, double-frees, or corrupts the heap.
 *
 *   FAIL_AT=N   fail the Nth (1-based) malloc/calloc/realloc call, all others succeed. Unset/<=0 = never fail.
 *   FAIL_SIZE=N fail EVERY malloc/calloc/realloc of exactly N bytes. FAIL_AT counts allocations
 *               globally, which is not reproducible in a MULTI-THREADED target (worker threads race
 *               for the counter, so the Nth allocation is a different one on every run). Sizing is
 *               thread-stable: a test picks a capacity whose allocation size is unique in the program
 *               (e.g. a run queue of 173 slots grows to 346*8 = 2768 bytes) and fails exactly that
 *               site, on whichever thread reaches it. This is what makes an allocation failure
 *               INSIDE a pool worker a deterministic test rather than a sweep.
 *   FAIL_SKIP=K  with FAIL_SIZE: let the first K matching allocations SUCCEED (default 0).
 *   FAIL_COUNT=C with FAIL_SIZE: fail at most C matching allocations, then let the rest succeed
 *               (default 0 = unlimited). Together they select an OCCURRENCE WINDOW of one site — e.g.
 *               "the actor spawn works, its first restart is out of memory, the retry works", which is
 *               how a supervisor's RECOVERY from a failed restart gets tested rather than just its failure.
 *   ZALLOC_COUNT=1   print "ZALLOC_TOTAL=<n>" to stderr at exit (the injectable allocation count for a dry run).
 *
 *   cc -shared -fPIC -O2 oom-shim.c -ldl -o oom-shim.so
 *   ZALLOC_COUNT=1 LD_PRELOAD=./oom-shim.so ./prog            # count allocation sites
 *   FAIL_AT=7      LD_PRELOAD=./oom-shim.so ./prog            # fail the 7th allocation
 *
 * NOTE: this CANNOT instrument the ASan build — AddressSanitizer owns malloc/calloc/realloc and does
 * not chain to a preloaded interposer (a preloaded malloc is simply never called under ASan). So the
 * OOM sweep runs the ORDINARY (glibc) compiler/program; run glibc with MALLOC_CHECK_=3 to have libc
 * abort on heap corruption / double-free discovered on an error path. See README.md.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdlib.h>
#include <stdio.h>

static long ctr = 0, fail_at = 0, fail_size = 0, fail_skip = 0, fail_count = 0, counting = 0, ready = 0;
static long size_hits = 0;   /* matching-size allocations seen so far (for FAIL_SKIP / FAIL_COUNT) */
static void *(*real_malloc)(size_t);
static void *(*real_calloc)(size_t, size_t);
static void *(*real_realloc)(void *, size_t);

static void init(void) {
    const char *e = getenv("FAIL_AT");
    fail_at = e ? atol(e) : 0;
    e = getenv("FAIL_SIZE");
    fail_size = e ? atol(e) : 0;
    e = getenv("FAIL_SKIP");
    fail_skip = e ? atol(e) : 0;
    e = getenv("FAIL_COUNT");
    fail_count = e ? atol(e) : 0;
    counting = getenv("ZALLOC_COUNT") != NULL;
    real_malloc = dlsym(RTLD_NEXT, "malloc");
    real_calloc = dlsym(RTLD_NEXT, "calloc");
    real_realloc = dlsym(RTLD_NEXT, "realloc");
    ready = 1;
}
/* true => this call should be failed (returns NULL). Counts every allocation regardless. */
static int should_fail(size_t s) {
    long n = __sync_add_and_fetch(&ctr, 1);
    if (fail_size > 0 && (long)s == fail_size) {
        long h = __sync_add_and_fetch(&size_hits, 1);   /* 1-based occurrence of THIS size */
        return h > fail_skip && (fail_count <= 0 || h <= fail_skip + fail_count);
    }
    return fail_at > 0 && n == fail_at;
}

void *malloc(size_t s) {
    if (!ready) init();
    if (should_fail(s)) return NULL;
    return real_malloc(s);
}
void *calloc(size_t n, size_t s) {
    if (!ready) init();
    /* dlsym itself may call calloc before real_calloc is resolved; serve those from a tiny static pool. */
    if (!real_calloc) { static char pool[8192]; static size_t off; size_t need = n * s;
        if (off + need <= sizeof(pool)) { void *p = pool + off; off += need; return p; } return NULL; }
    if (should_fail(n * s)) return NULL;
    return real_calloc(n, s);
}
void *realloc(void *p, size_t s) {
    if (!ready) init();
    if (should_fail(s)) return NULL;
    return real_realloc(p, s);
}

__attribute__((destructor)) static void report(void) {
    if (counting) fprintf(stderr, "ZALLOC_TOTAL=%ld\n", ctr);
}
