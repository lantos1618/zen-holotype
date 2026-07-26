#!/usr/bin/env python3
"""Mutation engine for scripts/fuzz-run.sh. Not meant to be run directly.

Argv: ITERS PER CRASH_DIR ASAN_BIN SEED... — mutates seeds, runs `ASAN check` on each, and records
sanitizer hits / signal crashes / hangs, deduped by failure signature.
"""
import os, random, subprocess, sys, hashlib, re

ITERS, PER, CR, ASAN, *SEEDS = sys.argv[1:]
ITERS, PER = int(ITERS), int(PER)
seeds = [open(s, "rb").read() for s in SEEDS]

# Adversarial tokens: unbalanced openers, huge digit/identifier runs, stray quotes/escapes, and Zen
# keywords that drive the deepest parser/checker paths (match/loop/impl/generics).
TOKENS = [b"{", b"[", b"(", b"<", b"}", b"]", b")", b">", b'"', b"'", b"\\", b"`",
          b"9" * 300, b"0x" + b"f" * 200, b"a" * 500, b"." * 64, b"=" * 32,
          b"match", b".loop", b"impl", b"return", b"=>", b"<T>", b"::", b"or_return",
          b"\x00", b"\xff", b"//", b"/*", b"*/", b"\n\t", b"_" * 100]

def mutate(data: bytes) -> bytes:
    b = bytearray(data)
    for _ in range(random.randint(1, 6)):
        if not b:
            b = bytearray(random.choice(TOKENS)); continue
        op = random.random()
        i = random.randrange(len(b))
        if op < 0.25:                                   # bit/byte flip
            b[i] ^= 1 << random.randrange(8)
        elif op < 0.45:                                 # truncate at random offset
            del b[i:]
        elif op < 0.65:                                 # insert adversarial token
            t = random.choice(TOKENS); b[i:i] = t
        elif op < 0.80:                                 # duplicate a span (blow up nesting/size)
            j = min(len(b), i + random.randint(1, 128)); b[i:i] = b[i:j]
        elif op < 0.92:                                 # delete a span
            del b[i:i + random.randint(1, 64)]
        else:                                           # overwrite with token
            t = random.choice(TOKENS); b[i:i + len(t)] = t
    return bytes(b[:1 << 20])                            # cap 1 MiB

# Match only the unambiguous sanitizer banners — NOT bare words like "stack-overflow", which the
# compiler echoes back when a fuzzed input happens to contain that text in a comment (false positive).
HIT = re.compile(rb"ERROR: AddressSanitizer:|SUMMARY: (Address|Undefined)Sanitizer|runtime error:")
def sig(out: bytes, rc: int) -> str:
    m = re.search(rb"(heap-buffer-overflow|stack-buffer-overflow|global-buffer-overflow|"
                  rb"heap-use-after-free|stack-overflow|SEGV|runtime error:[^\n]*|"
                  rb"stack-use-after-return)", out)
    frame = re.search(rb"#1 0x[0-9a-f]+ in ([A-Za-z0-9_]+)", out)  # first non-asan frame
    key = (m.group(1) if m else b"sig%d" % rc) + b"@" + (frame.group(1) if frame else b"?")
    return hashlib.sha1(key).hexdigest()[:12]

seen, hits, hangs, n = set(), 0, 0, 0
env = dict(os.environ)
tmp = "/tmp/fuzz_mutate_in.zen"
for n in range(1, ITERS + 1):
    data = mutate(random.choice(seeds))
    open(tmp, "wb").write(data)
    try:
        p = subprocess.run([ASAN, "check", tmp], capture_output=True, timeout=PER, env=env)
        out, rc = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        # Re-confirm with a longer budget: under CPU contention an ASan run can blow a tight timeout
        # without being a real infinite loop. Only a SECOND timeout at 4x counts as a hang.
        try:
            subprocess.run([ASAN, "check", tmp], capture_output=True, timeout=PER * 4, env=env)
            continue
        except subprocess.TimeoutExpired:
            pass
        s = "hang"
        if s not in seen:
            seen.add(s); hangs += 1
            open(f"{CR}/hang_{n}.zen", "wb").write(data)
            print(f"[{n}] HANG (>{PER * 4}s) -> hang_{n}.zen", flush=True)
        continue
    # A sanitizer report, OR a crash-signal exit (>=128, e.g. 139 SEGV / 134 SIGABRT) that isn't the
    # compiler's own clean panic. ASan-caught issues always print HIT; bare signals we keep too.
    if HIT.search(out) or rc >= 128:
        s = sig(out, rc)
        if s not in seen:
            seen.add(s); hits += 1
            open(f"{CR}/crash_{s}.zen", "wb").write(data)
            open(f"{CR}/crash_{s}.log", "wb").write(out)
            first = next((l for l in out.split(b"\n") if HIT.search(l)), b"")
            print(f"[{n}] HIT {s} rc={rc}: {first.decode('latin1')[:100]} -> crash_{s}.zen", flush=True)
    if n % 1000 == 0:
        print(f"...{n}/{ITERS} ({hits} unique hits, {hangs} hangs)", flush=True)

print(f"done: {n} iters, {hits} unique sanitizer hits, {hangs} hangs -> {CR}", flush=True)
# Findings FAIL the run. Without this the script exits 0 with 50 crashes on disk, and its sibling
# fuzz-corpus.sh (which does `exit 1` on hits) disagreed with it about whether finding bugs is a
# failure. `fuzz-run.sh` ends on this call, so its status is this status.
sys.exit(1 if (hits or hangs) else 0)
