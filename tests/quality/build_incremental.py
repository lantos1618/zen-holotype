#!/usr/bin/env python3
"""Exercise bootstrap cache invalidation and failed-build publication with real C."""

import fcntl
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import tempfile


DRIVER = Path(__file__).resolve().parents[2] / "scripts/build.py"
SEED = r'''
#include <stdio.h>
int main(int argc, char **argv) {
    char source[4096], output[4096];
    if (argc < 5) return 2;
    snprintf(source, sizeof source, "%s/main.zen", argv[2]);
    snprintf(output, sizeof output, "%s/main.c", argv[4]);
    FILE *in = fopen(source, "rb"), *out = fopen(output, "wb");
    if (!in || !out) return 3;
    int ch;
    while ((ch = fgetc(in)) != EOF) fputc(ch, out);
    fclose(in); fclose(out);
    snprintf(output, sizeof output, "%s/zen.h", argv[4]);
    out = fopen(output, "wb");
    if (!out) return 4;
    fputs("int native_value(void);\n", out);
    if (fclose(out) != 0) return 5;
    if (argc == 7) {
        out = fopen(argv[6], "wb");
        if (!out) return 6;
        fputs("mock symbols\n", out);
        if (fclose(out) != 0) return 7;
    }
    return 0;
}
'''



def check_orphaned_compiler(root, command, environment):
    """A killed driver cannot hand its workspace to the next build too soon."""
    marker = root / "compiler-started"
    release = root / "compiler-release"
    wrapper = root / "gated-cc"
    real_cc = shutil.which(os.environ.get("CC", "cc"))
    wrapper.write_text(f"""#!{sys.executable}
import os
from pathlib import Path
import sys
import time
if '-c' in sys.argv:
    Path({str(marker)!r}).write_text(str(os.getpid()))
    deadline = time.monotonic() + 15
    while not Path({str(release)!r}).exists():
        if time.monotonic() > deadline:
            raise SystemExit(97)
        time.sleep(0.01)
os.execv({real_cc!r}, [{real_cc!r}, *sys.argv[1:]])
""")
    wrapper.chmod(0o755)
    with (root / "orphan-build.log").open("w+") as log:
        parent = subprocess.Popen(command + ["--cc", str(wrapper)], cwd=root,
                                  stdout=log, stderr=log, env=environment, start_new_session=True)
        try:
            deadline = time.monotonic() + 10
            while not marker.exists():
                if parent.poll() is not None or time.monotonic() > deadline:
                    log.seek(0)
                    raise AssertionError(f"compiler did not reach its gate:\n{log.read()}")
                time.sleep(0.01)
            parent.kill()
            parent.wait(timeout=5)
            with (root / "build/bootstrap.lock").open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    raise AssertionError("killing the driver released a live compiler's workspace lock")
                release.touch()
                deadline = time.monotonic() + 10
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() > deadline:
                            raise AssertionError("compiler did not release its inherited lock")
                        time.sleep(0.01)
        finally:
            release.touch()
            if parent.poll() is None:
                parent.kill()
            parent.wait(timeout=5)
            # Also clean up a gated orphan when this regression intentionally
            # goes red: no surviving compiler may write into a deleted fixture.
            try:
                os.killpg(parent.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def check_header_search(environment, cache=""):
    """Adding an earlier candidate must invalidate both shortcuts and objects."""
    configurations = (
        ("joined-I", ["-Ifirst", "-Isecond"], {}, '<value.h>', "first/value.h"),
        ("separate-I-missing-root", ["-I", "first", "-I", "second"], {}, '<value.h>', "first/value.h"),
        ("CPATH", [], {"CPATH": "first:second"}, '<value.h>', "first/value.h"),
        ("C_INCLUDE_PATH", [], {"C_INCLUDE_PATH": "first:second"}, '<value.h>', "first/value.h"),
        ("nested-header", ["-Ifirst", "-Isecond"], {}, '<nested/value.h>', "first/nested/value.h"),
        ("quoted-local", ["-Ifirst", "-Isecond"], {}, '"value.h"', "src/std/proc/value.h"),
        ("iquote", ["-iquote", "first", "-iquote", "second"], {}, '"value.h"', "first/value.h"),
        ("forced-include", ["-Ifirst", "-Isecond", "-include", "value.h"], {}, None, "first/value.h"),
        ("dangling-shadow", ["-Ifirst", "-Isecond"], {}, '<value.h>', "target/value.h"),
        ("has-include", ["-Ifirst"], {}, None, "first/optional.h"),
        ("compact-comment-directive", ["-Ifirst", "-Isecond"], {}, '<value.h>', "first/value.h"),
        ("computed-include", ["-Ifirst", "-Isecond"], {}, None, "first/value.h"),
        ("multiline-comment", ["-Ifirst", "-Isecond"], {}, None, "first/value.h"),
        ("crlf-continuation", ["-Ifirst", "-Isecond"], {}, None, "first/value.h"),
        ("retarget-duplicate-root", ["-Ifirst", "-Ialias", "-Isecond"], {}, '<value.h>', "target/value.h"),
        ("history-reversion", ["-Ifirst", "-Isecond"], {}, '<value.h>', "first/value.h"),
    )
    for label, flags, variables, include, shadow in configurations:
        with tempfile.TemporaryDirectory(prefix="zen-header-check-") as temporary:
            root = Path(temporary)
            for directory in ("seed", "src/std/proc", "second/nested"):
                (root / directory).mkdir(parents=True)
            if label != "separate-I-missing-root":
                (root / "first").mkdir()
            (root / "seed/zen.c").write_text(SEED)
            (root / "src/main.zen").write_text('#include "zen.h"\nint main(void) { return native_value(); }\n')
            native = root / "src/std/proc/proc.c"
            native.write_text((f'#include {include}\n' if include else '')
                              + 'int native_value(void) { return VALUE; }\n')
            if label == "compact-comment-directive":
                native.write_text('/* leading comment */ #include<value.h>\n'
                                  'int native_value(void) { return VALUE; }\n')
            if label == "multiline-comment":
                native.write_text('#include /* comment\n */ <value.h>\n'
                                  'int native_value(void) { return VALUE; }\n')
            if label == "crlf-continuation":
                native.write_bytes(b'#inclu' + b'\\\r\n' + b'de <value.h>\r\n'
                                   b'int native_value(void) { return VALUE; }\r\n')
            if label == "computed-include":
                native.write_text('#define HEADER <value.h>\n#include HEADER\n'
                                  'int native_value(void) { return VALUE; }\n')
            if label == "has-include":
                native.write_text('#if __has_include(<optional.h>)\n#define VALUE 7\n'
                                  '#else\n#define VALUE 1\n#endif\n'
                                  'int native_value(void) { return VALUE; }\n')
            (root / "second/value.h").write_text('#define VALUE 1\n')
            (root / "second/nested/value.h").write_text('#define VALUE 1\n')
            if label == "retarget-duplicate-root":
                (root / "alias").symlink_to("first", target_is_directory=True)
            if label == "dangling-shadow":
                (root / "first/value.h").symlink_to("../target/value.h")
            command = [sys.executable, str(DRIVER), "--jobs", "2", "--cc", os.environ.get("CC", "cc"),
                       "--cflags=" + " ".join(["-O0", "-std=c99", *flags]), "--cache", cache]
            env = {**environment, **variables, "CCACHE_DIR": str(root / "cache")}
            phases = (("initial", 1), ("unchanged", 1), ("shadowed", 7), ("warm", 7))
            if label == "history-reversion":
                # Historical A gets a direct-cache manifest, then B stops
                # tracking value.h before a new shadow is added and A returns.
                phases = (("B", 0), ("A", 1), ("B-again", 0), ("shadowed", 7), ("warm", 7))
            for phase, expected in phases:
                if label == "history-reversion" and phase != "warm":
                    native.write_text('int native_value(void) { return 0; }\n'
                                      if phase.startswith("B") else
                                      '#include <value.h>\nint native_value(void) { return VALUE; }\n')
                if phase == "shadowed":
                    target = root / shadow
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text('#define VALUE 7\n')
                    if label == "retarget-duplicate-root":
                        (root / "alias").unlink()
                        (root / "alias").symlink_to("target", target_is_directory=True)
                result = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True)
                assert result.returncode == 0, (label, phase, result.stdout, result.stderr)
                cached = phase in ("unchanged", "warm") and label != "computed-include"
                assert ("up to date" in result.stdout) == cached, (label, phase, result.stdout)
                actual = subprocess.run([str(root / "zen")]).returncode
                assert actual == expected, (label, phase, actual, expected)
    return len(configurations)


def main():
    with tempfile.TemporaryDirectory(prefix="zen-build-check-") as temporary:
        root = Path(temporary)
        (root / "seed").mkdir()
        (root / "src/std/proc").mkdir(parents=True)
        seed = root / "seed/zen.c"
        source = root / "src/main.zen"
        native = root / "src/std/proc/proc.c"
        header = root / "value.h"
        output = root / "zen"
        seed.write_text(SEED)
        source.write_text('#include "zen.h"\nint main(void) { return native_value(); }\n')
        native.write_text('#include "../../../value.h"\nint native_value(void) { return VALUE; }\n')
        header.write_text('#define VALUE 0\n')
        command = [sys.executable, str(DRIVER), "--jobs", "2", "--cc", os.environ.get("CC", "cc")]
        checks = 0
        environment = dict(os.environ)
        environment.pop("ZEN_STD", None)

        def build(expected, *extra, succeeds=True):
            nonlocal checks
            result = subprocess.run(command + list(extra), cwd=root, text=True, capture_output=True, env=environment)
            if (result.returncode == 0) != succeeds or expected not in result.stdout + result.stderr:
                raise RuntimeError(f"unexpected build result ({result.returncode}):\n{result.stdout}{result.stderr}")
            checks += 1
            return result

        build("compiled 3 C units")
        build("up to date")
        # A timestamp-only edit is not a source change.
        source.touch()
        build("up to date")
        source.write_text(source.read_text().replace("return native_value()", "return native_value() + 1"))
        build("compiled 1 C units")
        assert subprocess.run([str(output)]).returncode == 1
        # Native headers are not in the Zen source list: compiler dependencies
        # must invalidate the result even when the top-level inputs are equal.
        header.write_text('#define VALUE 2\n')
        build("compiled 1 C units")
        assert subprocess.run([str(output)]).returncode == 3
        original_header = root / "original-value.h"
        header.rename(original_header)
        header.symlink_to(original_header.name)
        build("up to date")
        replacement_header = root / "replacement-value.h"
        replacement_header.write_text('#define VALUE 4\n')
        header.unlink()
        header.symlink_to(replacement_header.name)
        build("compiled 1 C units")
        assert subprocess.run([str(output)]).returncode == 5
        # Retarget again after an object has recorded the symlink dependency.
        header.unlink()
        header.symlink_to(original_header.name)
        build("compiled 1 C units")
        assert subprocess.run([str(output)]).returncode == 3
        header.unlink()
        header.symlink_to(replacement_header.name)
        build("compiled 1 C units")
        assert subprocess.run([str(output)]).returncode == 5
        native.write_text(native.read_text() + '\n/* native floor change */\n')
        build("compiled 1 C units")
        seed.write_text(seed.read_text() + '\n/* seed change */\n')
        build("compiled 1 C units")
        build("compiled 3 C units", "--cflags=-O0 -std=c99")
        build("up to date", "--cflags=-O0 -std=c99")
        build("compiled 3 C units")
        source.write_text(source.read_text() + "\nthis is invalid C\n")
        published = output.read_bytes()
        build("build:", succeeds=False)
        assert output.read_bytes() == published
        source.write_text(source.read_text().replace("\nthis is invalid C\n", "\n"))
        build("compiled 1 C units")
        # Reject input that cannot compile as a seed without replacing ./zen.
        seed.write_text(SEED + "\ninvalid seed\n")
        published = output.read_bytes()
        build("build:", succeeds=False)
        assert output.read_bytes() == published
        seed.write_text(SEED)
        build("compiled 1 C units")
        (root / "build/c/main.c.o").unlink()
        build("compiled 1 C units")
        (root / "build/c/main.c.o").write_bytes(b"corrupt")
        build("compiled 1 C units")
        (root / "build/c/zen.h").write_text("corrupt header")
        build("compiled 0 C units")
        output.write_bytes(b"corrupt executable")
        build("compiled 0 C units")
        output.unlink()
        build("compiled 0 C units")
        output.chmod(0o600)
        build("compiled 0 C units")
        assert os.access(output, os.X_OK)
        # A newly added source and removal must both invalidate emission.
        extra = root / "src/added.zen"
        extra.write_text("// extra source\n")
        build("compiled 0 C units")
        extra.unlink()
        build("compiled 0 C units")
        external = root / "external"
        external.mkdir()
        (root / "src/imported").symlink_to(external, target_is_directory=True)
        dependency = external / "dependency.zen"
        dependency.write_text("// imported source\n")
        build("compiled 0 C units")
        dependency.write_text("// changed imported source\n")
        build("compiled 0 C units")
        build("up to date")
        alias = root / "src/another_import"
        alias.symlink_to(external, target_is_directory=True)
        build("compiled 0 C units")
        (root / "src/imported").unlink()
        build("compiled 0 C units")
        alias.rename(root / "src/renamed_import")
        build("compiled 0 C units")
        (root / "src/renamed_import").unlink()
        environment["ZEN_STD"] = str(external)
        build("compiled 3 C units")
        dependency.write_text("// changed external standard library\n")
        build("compiled 0 C units")
        build("up to date")
        environment.pop("ZEN_STD")
        build("compiled 3 C units")
        symbol_map = root / "symbols.tsv"
        build("compiled 0 C units", "--symbol-map", str(symbol_map))
        assert symbol_map.read_text() == "mock symbols\n"
        build("up to date", "--symbol-map", str(symbol_map))
        published = output.read_bytes()
        blocked = root / "blocked"
        blocked.write_text("not a directory")
        source.write_text(source.read_text().replace("native_value() + 1", "native_value() + 2"))
        build("build:", "--symbol-map", str(blocked / "symbols.tsv"), succeeds=False)
        assert output.read_bytes() == published
        build("symbol map must name a file", "--symbol-map", str(root), succeeds=False)
        for target in (output, source, root / "build/c/zen.h", root / "build/bootstrap.json"):
            build("symbol map aliases", "--symbol-map", str(target), succeeds=False)
            assert output.read_bytes() == published
        alias = root / "aliased-symbols"
        alias.symlink_to(output)
        build("symbol map aliases", "--symbol-map", str(alias), succeeds=False)
        alias.unlink()
        os.link(output, alias)
        build("symbol map aliases", "--symbol-map", str(alias), succeeds=False)
        alias.unlink()
        assert output.read_bytes() == published
        build("compiled 1 C units", "--symbol-map", str(symbol_map))
        assert subprocess.run([str(output)]).returncode == 6
        # Cache metadata must be prepared before the executable is replaced.
        published = output.read_bytes()
        (root / "build/bootstrap.tmp").mkdir()
        source.write_text(source.read_text().replace("native_value() + 2", "native_value() + 3"))
        build("build:", succeeds=False)
        assert output.read_bytes() == published
        (root / "build/bootstrap.tmp").rmdir()
        build("compiled 1 C units")
        assert subprocess.run([str(output)]).returncode == 7
        build("must not be empty", "--cc=", succeeds=False)
        build("must be positive", "--jobs=0", succeeds=False)
        shutil.rmtree(root / "build")
        build("compiled 3 C units")
        published = output.read_bytes()
        check_orphaned_compiler(root, command, environment)
        checks += 1
        assert output.read_bytes() == published
        # A stranded temporary object is harmless; the next build still has
        # to pass dependency and publication checks before replacing ./zen.
        build("up to date")
        scenarios = check_header_search(environment)
        modes = "native"
        if shutil.which("ccache"):
            check_header_search(environment, shutil.which("ccache"))
            modes += " and ccache"
        print(f"buildcheck: {checks} cache, dependency, publication, and lock checks passed; "
              f"{scenarios} header-search scenarios passed with {modes}")


if __name__ == "__main__":
    main()
