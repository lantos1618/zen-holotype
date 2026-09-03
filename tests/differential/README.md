# Semantic differential harness

`run.py` observes each maintained fixture at three boundaries: Zen acceptance,
C acceptance with warnings kept visible, and native process exit. Run it from
the repository root:

```sh
python3 tests/differential/run.py --zen ./zen
```

The manifest records the intended classification. `CC_REJECTED` is understood
by the classifier but is never an allowed green outcome: if Zen accepts a
program, its generated C must compile. The manifest must also retain probes for
Zen rejection, C warnings, zero exit, and nonzero exit, so deleting the useful
cases cannot turn the lane vacuously green.

The warning policy enables common C warnings while suppressing unused shared
runtime helpers and variables. A fixture-specific unused parameter proves that
warnings produced by the fixture are still reported. This lane checks a small,
maintained semantic sample; the corpus remains responsible for broad language
and platform coverage.
