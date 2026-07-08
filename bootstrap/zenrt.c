#include "zenrt.h"
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <setjmp.h>
#include <ucontext.h>   /* faulting-thread register context (SP) — used to classify a SIGSEGV */
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
 * stack overflow the normal stack has no room left to run a handler on. write()/_exit()/siglongjmp() are
 * async-signal-safe; each candidate message is a fixed literal, so the handler touches no heap and no
 * shared state.
 *
 * ── CLASSIFYING THE FAULT ─────────────────────────────────────────────────────────────────────────
 * Most null derefs already panic cleanly via genc's AssertNonnull, but an UNGUARDED wild/null access
 * (e.g. indexing a slice built over a null pointer — the bounds check passes, the deref does not) still
 * reaches SIGSEGV. We used to report EVERY SIGSEGV as "stack overflow", which actively misled debugging
 * of a genuine null/wild deref. So the handler now takes SA_SIGINFO and inspects the faulting address
 * (`si_addr`) against the faulting thread's stack pointer (from the machine context) to distinguish:
 *   - a STACK OVERFLOW faults in the guard page immediately below the current SP (empirically within a
 *     few bytes; we allow a generous window) — Zen's sole unbounded-stack construct is recursion;
 *   - a NULL deref faults at/near address 0 (a null base plus a small struct-field offset);
 *   - anything else is an arbitrary invalid access (a wild pointer).
 * The classification reads only si_addr + one register and picks a fixed literal, so it stays async-
 * signal-safe. When the SP is unavailable (unknown arch) it degrades to the historical assumption that a
 * non-null fault is an overflow, preserving old behavior on ports we can't introspect.
 *
 * ── PER-THREAD ALT STACK (worker pools) ───────────────────────────────────────────────────────────
 * `sigaltstack` is a PER-THREAD setting, but `sa_flags`/the handler are process-wide. A pool worker
 * pthread that registers no alt stack of its own would have a stack-overflow SIGSEGV delivered onto its
 * already-exhausted stack → raw process kill (exit 139), killing the WHOLE pool. So each thread that can
 * run Zen recursion must call `__zen_thread_init()` first to register its OWN alt stack. The buffer is
 * `_Thread_local` — one instance per pthread (a single static is unshareable), self-freed at thread
 * exit (no malloc/free bookkeeping, no leak). The main thread registers via the same call from
 * `__zen_install_sigsegv_handler`; pool workers call it as the first line of their trampoline. */
static _Thread_local char __zen_sigstack[65536];   /* SIGSTKSZ can be a few KB; 64K is ample; per-thread */
/* per-worker catch target, defined just below for the isolation path; declared here so the handler can
 * route an actor's overflow into it (siglongjmp) instead of killing the process. */
static _Thread_local sigjmp_buf* __zen_panic_jmp;
/* the faulting thread's stack pointer, read out of the signal's machine context; 0 = "unavailable on this
 * arch/OS" (the handler then falls back to the historical stack-overflow assumption for a non-null fault). */
static uintptr_t __zen_fault_sp(void* ucv){
#if defined(__linux__) && defined(__x86_64__)
    return (uintptr_t)((ucontext_t*)ucv)->uc_mcontext.gregs[15];   /* gregs[REG_RSP] */
#elif defined(__linux__) && defined(__aarch64__)
    return (uintptr_t)((ucontext_t*)ucv)->uc_mcontext.sp;
#else
    (void)ucv; return 0;
#endif
}
/* async-signal-safe strlen for the chosen literal (write() needs a byte count). */
static int64_t __zen_msg_len(const char* m){ int64_t n = 0; while(m[n]){ n = n + 1; } return n; }
static void __zen_on_sigsegv(int sig, siginfo_t* info, void* ucv){
    (void)sig;
    /* Classify: near-0 fault => null deref; fault in the guard window just below the faulting SP =>
     * stack overflow; SP unknown => assume overflow (old behavior) for a non-null fault; else wild. */
    uintptr_t addr = (uintptr_t)(info ? info->si_addr : 0);
    uintptr_t sp   = __zen_fault_sp(ucv);
    const uintptr_t NULL_WINDOW  = 65536;         /* null base + a plausible struct-field offset */
    const uintptr_t STACK_WINDOW = 256 * 1024;    /* guard-page slack below SP; empirically the fault is within bytes */
    const char* m;
    if(addr < NULL_WINDOW){
        m = "zen: panic: null pointer dereference\n";
    } else if(sp == 0){
        m = "zen: panic: stack overflow (recursion too deep)\n";   /* SP unavailable (unknown arch): preserve old default */
    } else if(addr < sp && (sp - addr) <= STACK_WINDOW){
        m = "zen: panic: stack overflow (recursion too deep)\n";
    } else {
        m = "zen: panic: segmentation fault (invalid memory access)\n";
    }
    (void)!write(2, m, __zen_msg_len(m));
    /* If a per-worker catch is installed (a pool behavior is running under __zen_actor_call), unwind into
     * it like the div0/OOB/null panics do — that ONE actor dies, the worker + pool live on (#410 isolation
     * now covers stack overflow too). Off the pool path (main, inline drain) no catch is installed, so exit
     * cleanly with the panic code exactly as before.
     *
     * The catch uses sigsetjmp with savesigs=0 (cheap — no per-message sigprocmask syscall on the behavior
     * hot path, see __zen_actor_call), so siglongjmp does NOT restore the mask. On handler entry the kernel
     * blocks SIGSEGV for the handler's duration; unwinding out with it still blocked would make the NEXT
     * overflow on this worker undeliverable (raw kill). So we UNBLOCK SIGSEGV here, right before the jump —
     * one sigprocmask, only on an actual (rare) overflow, keeping the hot path syscall-free. sigprocmask is
     * async-signal-safe and on Linux affects only the calling (this worker) thread. */
    if(__zen_panic_jmp){
        sigset_t only_segv;
        sigemptyset(&only_segv);
        sigaddset(&only_segv, SIGSEGV);
        sigprocmask(SIG_UNBLOCK, &only_segv, 0);
        siglongjmp(*__zen_panic_jmp, 1);
    }
    _exit(134);   /* the panic exit code — genc's zen__panic aborts (128 + SIGABRT = 134) */
}
/* register the calling thread's per-thread sigaltstack (idempotent-safe to call once per thread). Every
 * thread that can run Zen recursion — the main thread and every pool worker — must call this before it
 * recurses, or a stack-overflow SIGSEGV has nowhere to run the handler. Best-effort: on failure the
 * default behaviour is left in place. */
void __zen_thread_init(void){
    stack_t ss;
    ss.ss_sp = __zen_sigstack;
    ss.ss_size = sizeof(__zen_sigstack);
    ss.ss_flags = 0;
    (void)!sigaltstack(&ss, 0);
}
static void __zen_install_sigsegv_handler(void){
    __zen_thread_init();   /* main thread's own alt stack */
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_sigaction = __zen_on_sigsegv;   /* SA_SIGINFO form: we need si_addr + the fault machine context */
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = SA_ONSTACK | SA_SIGINFO;   /* process-wide handler; runs on whichever thread's alt stack faulted */
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
/* __zen_panic_jmp (the per-worker catch target; 0 = "no catch installed") is declared above, next to the
 * SIGSEGV handler, because BOTH the ordinary panics (via __zen_panic_unwind) AND a worker's stack-overflow
 * SIGSEGV route into it. It is a `sigjmp_buf` (not `jmp_buf`) so the SIGSEGV handler can siglongjmp out of
 * a signal context safely. The mask handling is the crux: on handler entry the kernel blocks SIGSEGV, and
 * a plain longjmp would NOT clear that — SIGSEGV would stay blocked after the unwind and the NEXT overflow
 * on that worker would be undeliverable (raw kill). We use the CHEAP variant: sigsetjmp with savesigs=0
 * here (no per-message sigprocmask syscall on the behavior hot path — a heavy pool stress regressed ~60%
 * with savesigs=1), and the handler UNBLOCKS SIGSEGV itself right before siglongjmp, so the one syscall
 * happens only on an actual (rare) overflow. The div0/OOB/null path reaches this same buffer via
 * __zen_panic_unwind's siglongjmp; on that (non-signal) path SIGSEGV is not blocked, so no unblock is
 * needed and savesigs=0 is exactly right. */
/* run behavior(user, msg) under a sigsetjmp catch. Returns 0 if it returned normally, 1 if it panicked
 * (zen__panic siglongjmp'd back here, or a worker stack-overflow SIGSEGV did). Save/restore of `prev`
 * keeps re-entrancy safe. */
int64_t __zen_actor_call(void (*behavior)(uint8_t*, int64_t), uint8_t* user, int64_t msg){
    sigjmp_buf jb;
    sigjmp_buf* volatile prev = __zen_panic_jmp;   /* volatile: read after longjmp must not be a clobbered reg */
    if(sigsetjmp(jb, 0) != 0){ __zen_panic_jmp = prev; return 1; }   /* savesigs=0: cheap (no syscall); handler unblocks SIGSEGV */
    __zen_panic_jmp = &jb;
    behavior(user, msg);
    __zen_panic_jmp = prev;
    return 0;
}
/* called by genc's zen__panic AFTER it prints its line: unwind to the installed worker catch, else return
 * (and let zen__panic abort() — the unchanged non-actor path). siglongjmp pairs with the sigsetjmp above. */
void __zen_panic_unwind(void){ if(__zen_panic_jmp){ siglongjmp(*__zen_panic_jmp, 1); } }

ZWEAK int main(int argc, char** argv){
    __zen_argc = (int32_t)argc;
    __zen_argv = argv;
    __zen_install_sigsegv_handler();
    return (int)zen_main();
}
