# Top-level convenience Makefile — pure forwarding to bootstrap/Makefile. Only the targets that
# survive the reset are exposed here: everything else (regen, harness, bench, difftest, docs-check,
# ffi-verify, resolve-seed) consumed sources that no longer exist in this tree. bootstrap/Makefile
# still defines them; they will fail until there is a compiler to regenerate.

BOOT := $(MAKE) -f bootstrap/Makefile

.PHONY: all zen clean

# Default: cc the frozen stage-0 seed into ./zen.
all: zen

zen:
	$(BOOT) zen

clean:
	$(BOOT) clean
