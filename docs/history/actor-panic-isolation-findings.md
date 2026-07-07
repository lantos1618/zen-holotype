# Actor panic isolation — Phase 1 findings

Goal of the slice: a behavior panic (div0 / OOB / explicit) kills THAT actor and lets the pool keep
running the others. NOT restart/links/monitors (full OTP) — that is explicitly deferred.

## 1. How panic works today

- **`zen__panic`** is emitted as a `static` function in the C preamble
  (`zen/compiler/genc_emit.zen:829`):
  `static void zen__panic(const char* m){ write(2, m, n); abort(); }`.
  It writes the message to fd 2 and `abort()`s → SIGABRT → exit 134. Whole process dies.
- **div0 / mod0 / division-overflow / OOB-index** all funnel through `zen__panic`
  via `zen__divz` / `zen__modz` / `zen__udivz` / `zen__umodz` / `zen__idx` (same preamble line).
- **null deref** → `AssertNonnull` emits an inline `zen__panic("... null pointer deref")`
  (`genc_emit.zen:269`).
- **stack overflow (#396)** is a SEPARATE mechanism in `bootstrap/zenrt.c`: a `SIGSEGV` handler on a
  dedicated `sigaltstack` prints a fixed message and `_exit(134)`. This is signal-based and is left
  UNCHANGED by this slice (recovering from SIGSEGV is the deferred (b) option).

So every "normal" panic (div0/OOB/null/explicit) = `zen__panic` → `abort()`. That is the single
choke point to intercept.

## 2. The catch mechanism — RECOMMENDATION: option (a), setjmp/longjmp

Chosen because it is minimal, portable, and reuses the ONE existing choke point (`zen__panic`).
Option (b) (sigsetjmp for SIGSEGV/OOB) is harder and only needed for stack-overflow recovery, which
we defer.

### The worker call site
`pool.zen drain_batch` (lines 239-244) is where a worker runs one behavior:
```
saved := enter(a.art)
a.behavior(a.user, msg)   // <-- the type-erased (RawPtr<u8>, i64) void fn-ptr
leave(saved)
```

### The exact runtime change (`bootstrap/zenrt.c`)
Add a thread-local jmp target + a trampoline + an unwind hook:
```c
#include <setjmp.h>
static _Thread_local jmp_buf* __zen_panic_jmp = 0;   // per-worker; 0 = "no catch installed"

// run behavior(user,msg) under a setjmp catch. Returns 0 normally, 1 if it panicked.
int64_t __zen_actor_call(void (*behavior)(uint8_t*, int64_t), uint8_t* user, int64_t msg){
    jmp_buf jb;
    jmp_buf* volatile prev = __zen_panic_jmp;   // volatile: survives longjmp
    if(setjmp(jb) != 0){ __zen_panic_jmp = prev; return 1; }
    __zen_panic_jmp = &jb;
    behavior(user, msg);
    __zen_panic_jmp = prev;
    return 0;
}
// called by zen__panic AFTER it prints: unwind to the worker if a catch is installed, else return
// (caller aborts as today — non-actor panics unchanged).
void __zen_panic_unwind(void){ if(__zen_panic_jmp){ longjmp(*__zen_panic_jmp, 1); } }
```

### The preamble change (`genc_emit.zen:829`)
`zen__panic` prints (unchanged) then calls the hook before abort:
```c
void __zen_panic_unwind(void);   // declared inline in the preamble, like abort()
static void zen__panic(const char* m){ ...write...; __zen_panic_unwind(); abort(); }
```
When no jmp is installed (main, inline drain) `__zen_panic_unwind` returns and `abort()` runs —
**the non-actor path is byte-for-byte unchanged**.

### The Zen wiring (`pool.zen`)
- Bodyless FFI decl (same mechanism as `std.c.libc`): `__zen_actor_call = (behavior: (RawPtr<u8>, i64) void, user: RawPtr<u8>, msg: i64) i64`.
  genc emits the prototype (verified: it does this for every used bodyless decl, e.g. `clock_gettime`),
  ABI-compatible with the zenrt.c definition; the name is kept verbatim (FFI, not mangled/intrinsic).
- Add a `dead: i64` field to `PoolActor` (init 0).
- `drain_batch`: replace the direct call with
  `crashed := __zen_actor_call(a.behavior, a.user, msg)`, bracketed by the SAME `enter`/`leave`
  (leave runs because the trampoline returns NORMALLY to Zen after catching). On `crashed != 0` set
  `a.dead = 1`; while dead, dequeue-and-discard remaining messages (don't run behavior) so the actor
  quiesces and the pool reaches `live == 0`. `run_quantum` then deschedules it normally.

## 3. Risk / what breaks / defer list

**Risks (accepted, documented):**
- **Leaks on longjmp.** Any `malloc` done inside the behavior before the panic leaks — notably the
  typed `pool_actor` message box (freed by `pa.free_msg` which won't run). The actor is dead so its
  half-mutated state is irrelevant; this is a one-time leak on an abnormal path. (The proof uses the
  RAW pool with i64 messages — no box — so it is leak-free.)
- **Reentrancy / thread-safety.** `__zen_panic_jmp` is `_Thread_local` → one jmp target per worker,
  saved/restored around each call, no nesting (behaviors don't re-enter the trampoline). Safe under
  the pool's real pthreads.
- **A longjmp out of a C frame that held a lock** would deadlock — but `drain_batch` runs the
  behavior strictly OUTSIDE the mailbox lock (by design, line 226 comment), so no lock is held across
  the catch. Verified.
- The dead actor's mailbox may hold undrained messages if new sends arrive after death; they are
  discarded on the next turn (dequeue-without-run). No corruption.

**Deferred (NOT this slice):** actor restart, supervision trees, links/monitors (OTP); SIGSEGV/
stack-overflow recovery (stays a whole-process `_exit`); per-actor error reporting beyond the
existing `zen: panic:` line + a "actor dead" note.

## Gates to clear in Phase 2
`make zenc`; `make oracle-fast`; full `make oracle` (pool fixtures 10x); `--build-self` zero
over-rejection; seed fixpoint byte-exact (zenrt.c is linked but NOT in the seed closure — verify the
build still links); `fmt --check`; PR CI. `panics.zen` proof: 3 actors, one div0s, other two finish,
exit defined, one panic on stderr; without isolation this is 134.
