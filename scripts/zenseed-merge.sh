#!/bin/sh
# Custom git merge driver for the generated bootstrap seed: bootstrap/zenc.gen.c
#
# The seed is a BUILD ARTIFACT — the C the Zen frontend emits for the compiler sources. Every PR
# regenerates it, so parallel branches conflict on it on essentially every merge. A textual 3-way
# merge of generated C is meaningless (and never what you want), so this driver resolves the conflict
# trivially: it keeps the current side as-is and reports success. That leaves a clean, compilable
# (but possibly stale) seed with NO conflict markers, so `zenc` can build and `make resolve-seed`
# (i.e. `make regen`) can reproduce the correct, byte-exact seed from the .zen sources.
#
# git invokes this as:  zenseed-merge.sh %O %A %B %P
#   %O = ancestor version, %A = current/ours (the result file git reads back), %B = other/theirs,
#   %P = pathname. The merge result must be left in %A; it already holds "ours", so we just exit 0.
#
# Register it once per clone with:  make -f bootstrap/Makefile setup-git
# Always follow a seed merge with:  make -f bootstrap/Makefile resolve-seed
exit 0
