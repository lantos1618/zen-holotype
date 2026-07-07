# docs/history — archived point-in-time snapshots

These are historical records: reviews, audits, scout fix-queues, design-judge
rulings, and per-milestone implementation notes captured at a specific moment.
They are **not living docs** — they were true at their date and are preserved
here for provenance. Where a topic has a current, maintained doc (e.g.
`docs/rt-scoped-runtime.md`), that living doc supersedes the snapshots below.

## Index

| Doc | Date | What it captured |
| --- | --- | --- |
| `deep-audit-2026-06.md` | 2026-06-26 | Read-only 7-probe Monte-Carlo deep audit (parser, checker, codegen, driver/resolve/pretty, …). |
| `scout-queue-2026-06-27.md` | 2026-06-27 | Scout fix-queue: 5-dimension fan-out on main `e0f8317`, 30 findings ranked into a work plan. |
| `scout-queue-2-2026-06-28.md` | 2026-06-28 | Scout round 2, regression-focused (main `7f3f2ba`) — regressions to fix first. |
| `scout-m5-2026-06-28.md` | 2026-06-28 | M5 re-scout: usability verdict + polish queue. |
| `north-star-assessment-2026-07.md` | 2026-07 | North-star assessment against the 4 pillars; overall verdict 4.5/10. |
| `rt-design-judge-ruling-2026-07.md` | 2026-07 | rt-scoped-runtime judge-panel ruling (aggregate 5.9/10, revise-then-build). |
| `three-things-ruling-2026-07.md` | 2026-07 | 5-elite-judge ruling on rt v2 + error sugar + enum syntax. |
| `rt-foundation-notes.md` | 2026-07 | rt foundation slice impl notes — ambient thread-local Rt (rt-scoped-runtime §2b). |
| `rt-m3-notes.md` | 2026-07 | rt M3 impl notes — process-wide default runtime (SHIPPED, option a; §2b). |
| `rt-m4-notes.md` | 2026-07 | rt M4 impl notes — typed actors on the pool + per-actor ambient rt (§3). |
| `actor-panic-isolation-findings.md` | 2026-07 | Actor panic-isolation Phase 1 findings (a behavior panic kills that actor; the pool survives). |

_Superseded-by pointers, where applicable:_ the `rt-*` snapshots implement
slices of the living `docs/rt-scoped-runtime.md`; the scout / audit / review
snapshots are one-time reports with no living successor.
