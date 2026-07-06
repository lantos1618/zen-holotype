#include "zenrt.h"
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <setjmp.h>
/* U1.3: the runtime primitives below are also defined in Zen by resolvable std modules.
 * Built programs emit their own strong definitions when they import those modules; these weak
 * fallbacks keep the bootstrap compiler and import-free programs linkable. String allocation is
 * intentionally not provided here; String builders must go through an explicit allocator. */
#define ZWEAK __attribute__((weak))
ZWEAK bool eq(const char* a, const char* b){ return strcmp(a, b) == 0; }
ZWEAK bool is_empty(const char* s){ return s[0] == 0; }
/* mirror std.text.str.starts_with / ends_with (prefix/suffix byte tests over a str). */
ZWEAK bool starts_with(const char* s, const char* prefix){ size_t pl = strlen(prefix); return strlen(s) >= pl && memcmp(s, prefix, pl) == 0; }
ZWEAK bool ends_with(const char* s, const char* suffix){ size_t sl = strlen(s), fl = strlen(suffix); return sl >= fl && memcmp(s + (sl - fl), suffix, fl) == 0; }
ZWEAK zslice bytes(String s){ zslice z; z.ptr = s.ptr; z.len = s.len; return z; }
ZWEAK void* heap(int64_t n){ return malloc(n); }
/* mirror the Zen bodies exactly:
 *   std.mem.raw.alloc(n)       = malloc(n)                                 (uninitialised n bytes)
 *   std.text.str.view(s)        = slice(s, strlen(s))                       ([u8] view over a str's bytes) */
ZWEAK uint8_t* alloc(int64_t n){ return (uint8_t*)malloc(n); }
ZWEAK zslice view(const char* s){ zslice z; z.ptr = (void*)s; z.len = (int64_t)strlen(s); return z; }

/* OS entry: the real main lives here, stashes argc/argv into globals that std.os reads, then calls
 * the Zen entry (emitted as `zen_main`). WEAK so that during the driver->Zen migration the zenc binary
 * — which still links bootstrap/driver.c and its own strong main — overrides this one (the weak body,
 * with its zen_main reference, is dropped at link). User programs (compiled with just <prog>.c +
 * zenrt.c, no driver.c) get this entry, which calls the program's own zen_main. */
int32_t __zen_argc = 0;
char**  __zen_argv = 0;
/* std.os reads argv through these (never touches the globals directly). Bounds-checked so an out-of-
 * range index is an empty string, not a crash. */
int32_t zen_argc(void){ return __zen_argc; }
const char* zen_argv_at(int32_t i){ return (i >= 0 && i < __zen_argc) ? __zen_argv[i] : ""; }
/* Weak stub so the zenc binary (whose weak main below is overridden by driver.c and never runs) still
 * links — a user program emits its own strong zen_main, which overrides this. */
ZWEAK int32_t zen_main(void){ return 0; }

/* ── stack-overflow panic ──────────────────────────────────────────────────────────────────────────
 * Zen's ONLY loop is recursion (control flow is `.match` + recursion), so a runaway recursion exhausts
 * the C stack and raises SIGSEGV. Untrapped that is a silent `Segmentation fault` (raw signal death, no
 * diagnostic) — the worst failure mode for the core idiom. Trap SIGSEGV and turn it into the same
 * `zen: panic:` line the div/idx/null guards print (see genc's zen__panic), then exit cleanly with the
 * panic exit code (134 = what abort() yields), so a deep recursion teaches instead of crashing.
 *
 * The handler MUST run on a DEDICATED alternate stack (sigaltstack + SA_ONSTACK) — when the fault is a
 * stack overflow the normal stack has no room left to run a handler on. write()/_exit() are async-
 * signal-safe; the message is a fixed literal, so the handler touches no heap and no shared state.
 * We deliberately report every SIGSEGV as a stack overflow: in a language whose sole unbounded-stack
 * construct is recursion (raw null derefs already panic via genc's AssertNonnull), that is the cause. */
static char __zen_sigstack[65536];   /* SIGSTKSZ can be a few KB; 64K is ample for write()+_exit */
static void __zen_on_sigsegv(int sig){
    (void)sig;
    static const char m[] = "zen: panic: stack overflow (recursion too deep)\n";
    (void)!write(2, m, sizeof(m) - 1);
    _exit(134);   /* the panic exit code — genc's zen__panic aborts (128 + SIGABRT = 134) */
}
static void __zen_install_sigsegv_handler(void){
    stack_t ss;
    ss.ss_sp = __zen_sigstack;
    ss.ss_size = sizeof(__zen_sigstack);
    ss.ss_flags = 0;
    if(sigaltstack(&ss, 0) != 0){ return; }   /* best-effort: leave the default behaviour if it fails */
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = __zen_on_sigsegv;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = SA_ONSTACK;
    sigaction(SIGSEGV, &sa, 0);
}

/* ── per-actor panic isolation ─────────────────────────────────────────────────────────────────────
 * A behavior panic (div0 / OOB / null / explicit) must kill only THAT actor, not the whole process, so
 * a pool worker can keep running the other actors. All those panics funnel through genc's `zen__panic`
 * (it prints the `zen: panic:` line, then — now — calls `__zen_panic_unwind` before `abort()`).
 *
 * The catch is a thread-local setjmp target installed ONLY around a pool worker's behavior call
 * (std.concurrent.pool `drain_batch` calls `__zen_actor_call`). When no target is installed — a panic
 * in `main`, in an inline sync drain, anywhere off the pool worker path — `__zen_panic_unwind` returns
 * and `zen__panic`'s `abort()` runs exactly as before: the non-actor path is byte-identical (proven by
 * the negative fixture). `__zen_panic_jmp` is _Thread_local so each worker has its own target and workers
 * never race on it. `__zen_actor_call` SAVES and RESTORES the previous target, so even a (currently
 * non-existent) nested re-entry — a behavior that synchronously ran another behavior under the same
 * worker — uses its own distinct `jmp_buf` and cannot clobber the outer one.
 *
 * KNOWN v1 LIMIT: a longjmp abandons the crashed behavior's C frame, so anything it malloc'd before the
 * panic (e.g. a typed message box) LEAKS — leaking one dead actor's memory beats aborting the whole
 * process. The real fix (DEFERRED) is a per-actor arena rt that is reset when the actor dies, reclaiming
 * everything the behavior allocated in one shot. No lock is held across the catch (the pool runs the
 * behavior OUTSIDE the mailbox lock), so the longjmp cannot strand a lock. */
static _Thread_local jmp_buf* __zen_panic_jmp = 0;   /* per-worker catch target; 0 = "no catch installed" */
/* run behavior(user, msg) under a setjmp catch. Returns 0 if it returned normally, 1 if it panicked
 * (zen__panic longjmp'd back here). Save/restore of `prev` keeps re-entrancy safe. */
int64_t __zen_actor_call(void (*behavior)(uint8_t*, int64_t), uint8_t* user, int64_t msg){
    jmp_buf jb;
    jmp_buf* volatile prev = __zen_panic_jmp;   /* volatile: read after longjmp must not be a clobbered reg */
    if(setjmp(jb) != 0){ __zen_panic_jmp = prev; return 1; }
    __zen_panic_jmp = &jb;
    behavior(user, msg);
    __zen_panic_jmp = prev;
    return 0;
}
/* called by genc's zen__panic AFTER it prints its line: unwind to the installed worker catch, else return
 * (and let zen__panic abort() — the unchanged non-actor path). */
void __zen_panic_unwind(void){ if(__zen_panic_jmp){ longjmp(*__zen_panic_jmp, 1); } }

ZWEAK int main(int argc, char** argv){
    __zen_argc = (int32_t)argc;
    __zen_argv = argv;
    __zen_install_sigsegv_handler();
    return (int)zen_main();
}
