# Deep audit — 2026-06-26 (7-probe Monte-Carlo)

Read-only deep inspection: 7 parallel probes (parser, checker, codegen, driver/resolve/pretty,
data/mem, concurrency, runtime/FFI), each verified with repros against a live `./zenc`. Status:
🔧 = fix in flight · ⏳ = queued · 🎨 = needs design/taste call · ✅ = fixed/merged.

## KEYSTONE
- 🔧 **`subst_var` arg splicing** (check.zen:1349). Inliner splices the arg *expression* per param-use
  instead of binding once. param used N× → N evals → silent miscompile + the `gstr_push`/UAF class
  (the deferred M2b). param used 0× → arg node vanishes → generic instance never monomorphized →
  `Node_i32` undeclared, C won't compile. Trap: a prior fix regressed 37 cases by binding trait-method
  *receivers* — bind only non-trivial non-receiver args. Repros: `add2(bump())`→bump×2; `byte_size(Node<i32>(..))`.

## HIGH
- 🔧 **C5 `save(p,data,n)` OOB write-to-disk** (io/file:105) — no bound vs buffer; `save("hi",64)`→64 bytes.
- 🔧 **C8 run-queue `rq_push` unguarded** (pool:131) — actors>rqcap → heap corruption/UAF (SIGABRT/ASan).
- 🔧 **C9 unbounded recursion crashes** — math `fpow_pos`/`pow_i`, fs `count_entries` → stack overflow.
- ⏳ **C2 type identity diverges by import path** (mangler) — same type via qualified-alias vs unqualified →
  different C name → won't compile. Breaks qualified `str` import AND actor `Context`/`Receiver` API.
  Fix: mangle on canonical identity (defining module + name + args), not import path.
- 🎨 **C3 `zenc fmt` corrupts every file** (pretty) — (a) rewrites `RawPtr`/`MutPtr`→`Ptr` (pretty:223; all
  3 parse to one `Ty.Ptr`), (b) relocates comments (gf_decl_pos=0 for body-less decls). Can't run on its
  own codebase. NOTE: (a) ties to the safety-goal-D pointer-kind distinction — design call.
- ⏳ **C4 `--build-self`/`emit --force` skip `check_validate`** (driver:421) — the structural root of all
  "self-build leniency" bugs. Clean fix: validate in build_self.
- ⏳ **C6 double-free/UAF inside a match/if branch undetected** (check_validate:1283) — `own_step` only sees
  top-level stmts. Undermines the UAF guarantee.
- ⏳ **C7 parser crashes** — `a=a` self-alias → SIGSEGV (parse:259 over-broad + no resolver cycle guard);
  unbounded recursion depth → SIGSEGV (paren/while/unary/ty, no cap); list parsers (fill_args/pinits/
  sitems/tys) don't validate `)` → silently swallow code with no error.

## MEDIUM
- ⏳ infinite-size recursive type passes `check`, fails at cc (no containment-cycle rule) — 3× confirmed.
- ⏳ libm doesn't link under `zenc run` (only project `link="m"`) — sin/log/pow runtime arg → undefined ref.
- ⏳ literal constant-fold overflow accepted (open #8) — in-range wraps slip the range check.
- ⏳ value-receiver UFCS on a `MutPtr<T>` method type-checks but emits invalid C (arena `ar.free`).
- ⏳ float formatter prints finite doubles ≥9e18 as `"inf"` (no sci-notation).
- ⏳ `ReplyRef.await` ignores `ready` (dead sync; latent race under the pool).
- ⏳ `read_dir` TOCTOU heap-overflow (count→fill, no bound); `contents()` fails on /proc/pipes (lseek).
- ⏳ import-cycle → misleading `dup-fn` (no cycle diagnostic).

## LOW
temp `/tmp/zenc_zd_*` never unlinked · `build.zen` entry file not pid-namespaced · `run` reports success on
exec failure (-1/256=0) · unterminated block-comment no position · trailing-`\`-at-EOF OOB read · bitwise
binds tighter than comparison (footgun) · struct offsets x86-64-only · mono mangle collision `Box_i32`
(adversarial) · checkpoint/`request` dead surface (de-slop) · `pool_actor_count` non-atomic read.

## VERIFIED SOLID (no defects)
Data structures (Vec/Map/Set/String/Rc/Arc/arena — heavy stress) · parallel core (TSan+ASan clean) ·
codegen guards (div/mod/OOB/heap-promotion) · parser totality (250k fuzz) · diagnostics span math ·
gstr_push hoist audit (all in place) · integer/unsigned formatting · the #316 CPS return-lift.
The foundation is sound; defects are concentrated and fixable.
