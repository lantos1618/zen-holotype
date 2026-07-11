# Sys phase 2 — honest print / Writer spine

**Status:** SHIPPED (2026-07). This doc records what landed and how callers migrate.
**Parent:** [runtime-design.md](runtime-design.md) § "Writer → Result".
**Related:** [brick3-io-monad-design.md](brick3-io-monad-design.md) (IO composes via `Result` + `.or_return`, not a monad wrapper).

---

## BLUF

`Writer.write` / `write_bytes` return `Result<i64, IoError>`. A broken pipe (EPIPE), full
disk (ENOSPC), or closed fd is a **value** — `.or_return()`, `.match`, or explicit handling —
never swallowed. `write_or_panic` is the one-call honest-but-fatal sink for scripts. Ambient
`println` / `print` remain **best-effort** (`i64`, errors mapped to 0) during the transition;
new code that owns a `Writer` should use the Result path.

---

## What shipped (`zen/std/sys.zen`)

| Surface | Return | Semantics |
|---|---|---|
| `write_all(fd, ptr, len, done)` | `Result<i64, IoError>` | write(2) retry loop; short writes advance; 0-byte stall → `.Eof` |
| `Writer.write(w, s: str)` | `Result<i64, IoError>` | str view → `write_all` |
| `Writer.write_bytes(w, b: [u8])` | `Result<i64, IoError>` | slice → `write_all` |
| `Writer.write_line(w, s: str)` | `Result<i64, IoError>` | `write(s)` then `write("\n")`; first Err wins |
| `Writer.write_or_panic(w, s)` | `i64` | `.write` + panic on Err (framed `zen: panic: <IoError>`) |

`IoError` lives in `std.core.result` (`.Errno(rc)`, `.Eof`, …). `Fs.read` / `Fs.save` and
`std.io.file` paths already share the same error type.

---

## Attenuation pattern (preferred)

```zen
{ Sys, Writer } = std.sys

greet = (w: Writer) Result<i64, IoError> {
    w.write_line("hi\n")    // or: w.write("hi\n").or_return()
}

main = (sys: Sys) i32 {
    greet(sys.stdout()).match ({
        .Ok(_)  => 0,
        .Err(e) => {
            sys.stderr().write_or_panic(e.name())
            1
        },
    })
}
```

Libraries take the **narrowest** capability: `(w: Writer)`, never `(sys: Sys)`.

---

## Transition plan (additive, no 314-site churn)

1. **Now:** `Writer` Result spine is live; `main_sys.zen` fixture proves `write_or_panic`.
2. **New code:** prefer `w.write` / `w.write_line` + `.or_return()` or `.match`.
3. **Scripts / demos:** `write_or_panic` or ambient `println` (still swallows via `out_bytes().or(0)`).
4. **Later batch:** migrate hot paths from `println` → explicit `Writer`; retire ambient stdout
   only after corpus coverage. No compiler flag flip — migration is callsite-by-callsite.

`std.text.fmt` Display ops (`println`, `write_text`) still target fd-1 best-effort. A future
`println_w(w, x)` Display→Writer bridge is optional; not required for phase-2 closure.

---

## What phase 2 does *not* include

- No `IO<T>` monad wrapper (see brick3-io-monad-design.md).
- No change to niladic `main = () i32` or the `zen_main` trampoline.
- No requirement to thread `Sys` through pure functions — only the sink you actually write to.

---

## Done-when checklist

- [x] `Writer.write` returns `Result<i64, IoError>` with write-all retry
- [x] `write_or_panic` for fatal scripts
- [x] `write_line` additive helper
- [x] This design doc + runtime-design cross-link
- [ ] Batch `println` → `Writer` migration (deferred; tracked in GOALS item 12 follow-up)
