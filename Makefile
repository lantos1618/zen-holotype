# Top-level convenience Makefile — pure forwarding to bootstrap/Makefile so a newcomer can type
# plain `make` (build the compiler), `make harness` (run the test harness), etc. from the repo root
# without remembering the `-f bootstrap/Makefile` incantation. All real build logic lives in
# bootstrap/Makefile; this file only delegates. CI uses `make -f bootstrap/Makefile <target>`
# directly, so this wrapper never changes what CI builds.

BOOT := $(MAKE) -f bootstrap/Makefile

.PHONY: all zenc regen harness harness-fast difftest docs-check clean setup-git resolve-seed

# Default: build ./zenc.
all: zenc

zenc:
	$(BOOT) zenc

regen:
	$(BOOT) regen

harness:
	$(BOOT) harness

harness-fast:
	$(BOOT) harness-fast

difftest:
	$(BOOT) difftest

docs-check:
	$(BOOT) docs-check

clean:
	$(BOOT) clean

setup-git:
	$(BOOT) setup-git

resolve-seed:
	$(BOOT) resolve-seed
