#!/usr/bin/env python3
"""Incremental seed bootstrap; publish ./zen only after every stage succeeds."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
from functools import partial
import hashlib
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time


def digest(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def run(command, *, pass_fds=(), env=None):
    subprocess.run(command, check=True, pass_fds=pass_fds, env=env)


def command_identity(command, *, pass_fds=()):
    """Include the driver, its version, and compiler/linker subprograms."""
    if not command:
        raise RuntimeError("C compiler command must not be empty")
    executable = shutil.which(command[0])
    if not executable:
        raise RuntimeError(f"command not found: {command[0]}")
    identity = [command, str(Path(executable).resolve()), digest(executable)]
    identity.append(subprocess.check_output(command + ["--version"], pass_fds=pass_fds).decode())
    for program in ("cc1", "as", "ld"):
        path = subprocess.check_output(command + [f"-print-prog-name={program}"], pass_fds=pass_fds).decode().strip()
        resolved = shutil.which(path)
        if resolved:
            identity.append([resolved, digest(resolved)])
    return identity


def c_directives(data):
    """Discard comments without interpreting comment markers inside literals."""
    tokens = rb'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*'
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n").replace(b"\\\n", b"")
    data = re.sub(tokens, lambda match: (b" " if match[0].startswith((b"/*", b"//")) else match[0]),
                  data, flags=re.S)
    return re.findall(rb"(?m)^\s*(?:#|%:|\?\?=)([^\n]*)", data)


class IncludeSearch:
    """Record include candidates absent from compiler dependency files.

    Dependencies track the selected header's bytes. Candidate existence also
    matters: a newly created header can shadow the old selection. Warm checks
    stat just those names, without scanning or hashing the system include tree.
    """
    def __init__(self, command, previous, *, pass_fds=()):
        self.previous = previous or {}
        if previous:
            self.roots = previous["roots"]
            self.plain_search = previous["plain_search"]
        else:
            probe = subprocess.run(command + ["-E", "-x", "c", "-v", "-o", os.devnull, "-"],
                                   input=b"", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   pass_fds=pass_fds, env={**os.environ, "LC_ALL": "C"})
            if probe.returncode:
                raise RuntimeError("cannot inspect C include search: " + probe.stderr.decode(errors="replace"))
            roots, collecting, recognized = [], False, False
            self.plain_search = True
            for line in probe.stderr.decode(errors="replace").splitlines():
                text = line.strip()
                if text.startswith('#include') and text.endswith('search starts here:'):
                    collecting = recognized = True
                elif text == 'End of search list.':
                    collecting = False
                elif collecting:
                    self.plain_search &= not text.endswith(' (framework directory)')
                    roots.append(text.removesuffix(' (framework directory)'))
                elif text.startswith(('ignoring nonexistent directory "',
                                      'ignoring duplicate directory "')):
                    roots.append(text.split('"', 2)[1])
            if not recognized:
                raise RuntimeError("C compiler did not report its include search directories")
            self.roots = sorted({str(Path(root).absolute()) for root in roots})
        # Opaque preprocessor options can hide includes or change without a
        # command change. Such configurations compile fresh instead of guessing.
        opaque = ('@', '-Wp,', '-Xpreprocessor', '-F', '-iframework', '-include-')
        self.safe = self.plain_search and not any(arg.startswith(opaque) for arg in command)
        self.forced = []
        for i, arg in enumerate(command):
            for option in ('-include', '-imacros'):
                if arg == option and i + 1 < len(command):
                    self.forced.append(command[i + 1])
                elif arg.startswith(option) and arg != option:
                    self.forced.append(arg[len(option):])
        self.reusable = bool(previous and self.safe and previous["safe"]
                             and all(Path(path).is_file() == exists
                                     for path, exists in previous["candidates"].items())
                             and self.root_targets() == previous["root_targets"])

    def root_targets(self):
        return {root: str(Path(root).resolve()) for root in self.roots}

    def snapshot(self, objects):
        candidates = set()
        safe = self.safe

        def add(name, local):
            for directory in [local, *self.roots]:
                candidates.add(str((Path(directory) / name).absolute()))

        for name in self.forced:
            add(name, Path.cwd())
        dependencies = {name: value for output, item in objects.items()
                        for name, value in item["files"].items() if name != output}
        includes = {}
        for name, value in dependencies.items():
            path = Path(name)
            parsed = self.previous.get("includes", {}).get(name)
            if parsed is None or parsed["digest"] != value:
                # Parsing only changes with file bytes, not include resolution.
                # Reuse it for unchanged generated C and system headers.
                data = path.read_bytes()
                directives = b"\n".join(c_directives(data))
                operands = re.findall(rb"(?m)^\s*(?:include_next|include|import)\b\s*([^\n]+)", directives)
                operands += re.findall(rb"__has_include(?:_next)?\s*\(\s*([^\n]+)", directives)
                names = []
                literal_only = not (b'??/' in data or re.search(rb'\\[ \t]+\r?\n', data))
                for operand in operands:
                    literal = re.match(rb'<([^>\n]+)>|"([^"\n]+)"', operand)
                    if literal:
                        names.append(os.fsdecode(literal[1] or literal[2]))
                    else:
                        literal_only = False
                parsed = {"digest": value, "names": names, "safe": literal_only}
            includes[name] = parsed
            safe &= parsed["safe"]
            for include in parsed["names"]:
                add(include, path.parent)
        return {"roots": self.roots, "plain_search": self.plain_search,
                "root_targets": self.root_targets(), "safe": safe, "includes": includes,
                "candidates": {path: Path(path).is_file() for path in sorted(candidates)}}


class Build:
    def __init__(self, args, lock_fd):
        self.args = args
        # Keep the workspace locked until every writing child exits, even when
        # this Python process is killed while waiting for a compiler.
        self.run = partial(run, pass_fds=(lock_fd,))
        self.directory = args.build_dir.resolve()
        self.cc = shlex.split(args.cc)
        self.compile = shlex.split(args.cache) + self.cc + shlex.split(args.cflags)
        self.state_path = self.directory / "bootstrap.json"
        try:
            self.previous = json.loads(self.state_path.read_text())
        except (FileNotFoundError, ValueError):
            self.previous = {}
        self.hashes = {}
        self.objects = {}
        self.compiled = 0
        self.settings = {
            "compiler": command_identity(self.cc, pass_fds=(lock_fd,)),
            "compile": self.compile,
            "cwd": os.getcwd(),
            "script": digest(__file__),
            # These environment variables alter header or toolchain lookup.
            "environment": {key: os.environ.get(key) for key in (
                "PATH", "CPATH", "C_INCLUDE_PATH", "LIBRARY_PATH", "COMPILER_PATH",
                "GCC_EXEC_PREFIX", "SDKROOT", "MACOSX_DEPLOYMENT_TARGET", "SOURCE_DATE_EPOCH", "ZEN_STD",
            )},
        }
        prior_search = (self.previous.get("include_search")
                        if self.settings == self.previous.get("settings") else None)
        self.include_search = IncludeSearch(self.cc + shlex.split(args.cflags), prior_search,
                                            pass_fds=(lock_fd,))

    def file_digest(self, path):
        path = str(path)
        if path not in self.hashes:
            self.hashes[path] = digest(path)
        return self.hashes[path]

    def unchanged(self, files):
        return bool(files) and all(value is not None and self.file_digest(path) == value
                                   for path, value in files.items())

    def compile_object(self, source, output=None):
        output = output or Path(str(source) + ".o")
        key = str(output)
        previous = self.previous.get("objects", {}).get(key, {})
        if (self.settings == self.previous.get("settings")
                and self.include_search.reusable
                and self.unchanged(previous.get("files", {}))):
            self.objects[key] = previous
            return output
        dependency = Path(str(output) + ".d")
        temporary = Path(str(output) + ".tmp")
        # A restored source can match a historical direct-cache manifest whose
        # missing headers were not tracked by the immediately previous build.
        # Our own cache skips unchanged objects; every actual compile submission
        # must let ccache preprocess current inputs before reusing an object.
        environment = {**os.environ, "CCACHE_NODIRECT": "1"}
        self.run(self.compile + ["-MD", "-MF", str(dependency), "-c", str(source), "-o", str(temporary)],
                 env=environment)
        temporary.replace(output)
        # GCC and Clang escape whitespace and wrap long dependency lists.
        dependencies = shlex.split(dependency.read_text().replace("\\\n", "").split(":", 1)[1])
        paths = [str(Path(path).absolute()) for path in dependencies] + [key]
        self.objects[key] = {"files": {path: digest(path) for path in paths}}
        self.compiled += 1
        return output

    def source_inputs(self):
        sources = []
        roots = [self.args.root]
        if os.environ.get("ZEN_STD"):
            roots.append(Path(os.environ["ZEN_STD"]))
        pending = [(root, frozenset()) for root in roots]
        while pending:
            directory, ancestors = pending.pop()
            resolved = directory.resolve()
            if resolved in ancestors:
                continue
            lineage = ancestors | {resolved}
            for path in directory.iterdir():
                if path.is_dir():
                    pending.append((path, lineage))
                elif path.suffix in (".zen", ".c", ".h"):
                    sources.append(path)
        sources.sort()
        if not any(path.suffix == ".zen" for path in sources):
            raise RuntimeError(f"no Zen sources under {self.args.root}")
        paths = sources + [Path("seed/zen.c"), Path("src/std/proc/proc.c")]
        return {str(path.absolute()): digest(path) for path in paths}

    def validate_symbol_map(self, inputs):
        target = self.args.symbol_map
        if target is None:
            return
        resolved = target.resolve()
        if target.exists() and not target.is_file():
            raise RuntimeError(f"symbol map must name a file: {target}")
        for directory in (self.directory / "c", self.directory / "obj"):
            if resolved == directory or directory in resolved.parents:
                raise RuntimeError(f"symbol map aliases build artifacts: {target}")
        protected = list(inputs) + [self.args.output, __file__, self.state_path, self.state_path.with_suffix(".tmp"),
                                   self.directory / "bootstrap.lock",
                                   self.directory / "zen-seed", self.directory / "zen-next"]
        for path in protected:
            other = Path(path)
            if resolved == other.resolve() or (target.exists() and other.exists()
                                               and target.samefile(other)):
                raise RuntimeError(f"symbol map aliases an input or build artifact: {target}")

    def build(self):
        start = time.monotonic()
        inputs = self.source_inputs()
        self.validate_symbol_map(inputs)
        request = {"root": str(self.args.root.resolve()),
                   "symbol_map": str(self.args.symbol_map.resolve()) if self.args.symbol_map else None}
        reusable = (self.settings == self.previous.get("settings")
                    and inputs == self.previous.get("inputs")
                    and request == self.previous.get("request"))
        if (reusable and self.include_search.reusable and self.unchanged(self.previous.get("artifacts", {}))
                and all(self.unchanged(item["files"])
                        for item in self.previous.get("objects", {}).values())
                and self.previous.get("objects")
                and os.access(self.args.output, os.X_OK)
                and self.unchanged({str(self.args.output.resolve()): self.previous.get("output")})):
            print(f"build: up to date ({time.monotonic() - start:.2f}s)")
            return

        objects_dir = self.directory / "obj"
        objects_dir.mkdir(exist_ok=True)
        # Stable paths retain ccache hits and compiler dependency paths.
        seed_source = Path("seed/zen.c").absolute()
        proc_source = Path("src/std/proc/proc.c").absolute()
        seed_obj = self.compile_object(seed_source, objects_dir / "seed.o")
        proc_obj = self.compile_object(proc_source, objects_dir / "proc.o")
        bootstrap = self.directory / "zen-seed"
        self.run(self.cc + [str(seed_obj), str(proc_obj), "-o", str(bootstrap)])

        generated = self.directory / "c"
        generated.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="emit-", dir=self.directory) as temporary:
            emitted = Path(temporary)
            command = [str(bootstrap), "build", str(self.args.root), "--emit-c-dir", str(emitted)]
            symbol_map = emitted / "symbols.tsv"
            if self.args.symbol_map:
                command += ["--symbol-map", str(symbol_map)]
            self.run(command)
            sources = sorted(emitted.glob("*.c"))
            if not sources or not (emitted / "zen.h").is_file():
                raise RuntimeError("bootstrap emitted no C sources or header")
            for source in sources + [emitted / "zen.h"]:
                destination = generated / source.name
                if digest(source) != digest(destination):
                    shutil.copyfile(source, destination)
                    self.hashes.pop(str(destination), None)
            live_names = {source.name for source in sources}
            for stale in generated.glob("*.c"):
                if stale.name not in live_names:
                    stale.unlink()
                    Path(str(stale) + ".o").unlink(missing_ok=True)
                    Path(str(stale) + ".o.d").unlink(missing_ok=True)
            with ThreadPoolExecutor(max_workers=self.args.jobs) as pool:
                objects = list(pool.map(self.compile_object, [generated / source.name for source in sources]))
            output = self.directory / "zen-next"
            self.run(self.cc + [str(obj) for obj in objects] + [str(proc_obj), "-o", str(output)])
            # A concurrent source edit must not produce an apparently current compiler.
            if inputs != self.source_inputs():
                raise RuntimeError("sources changed during bootstrap; rerun the build")
            include_search = self.include_search.snapshot(self.objects)
            self.args.output.parent.mkdir(parents=True, exist_ok=True)
            # Copy to the output filesystem before the atomic publication.
            with tempfile.NamedTemporaryFile(prefix=".zen-", dir=self.args.output.parent, delete=False) as file:
                publication = Path(file.name)
            map_publication = None
            pending = self.state_path.with_suffix(".tmp")
            try:
                shutil.copy2(output, publication)
                artifacts = {str(path): digest(path) for path in generated.iterdir()
                             if path.suffix in (".c", ".h")}
                if self.args.symbol_map:
                    self.args.symbol_map.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.NamedTemporaryFile(prefix=".zen-map-", dir=self.args.symbol_map.parent,
                                                     delete=False) as file:
                        map_publication = Path(file.name)
                    shutil.copyfile(symbol_map, map_publication)
                    artifacts[str(self.args.symbol_map.absolute())] = digest(map_publication)
                state = {"settings": self.settings, "inputs": inputs, "request": request,
                         "objects": self.objects, "artifacts": artifacts, "output": digest(publication),
                         "include_search": include_search}
                pending.write_text(json.dumps(state, sort_keys=True))
                if map_publication:
                    map_publication.replace(self.args.symbol_map)
                publication.replace(self.args.output)
                # The cache is optional. A failed cache rename after publication
                # must not turn a successfully published compiler into a failed
                # build; old state fails the content checks on the next call.
                try:
                    pending.replace(self.state_path)
                except OSError as error:
                    print(f"build: could not save incremental state: {error}", file=sys.stderr)
            finally:
                for temporary in (publication, map_publication, pending):
                    if temporary is not None:
                        try:
                            temporary.unlink(missing_ok=True)
                        except OSError:
                            pass
        print(f"build: compiled {self.compiled} C units ({time.monotonic() - start:.2f}s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("src"))
    parser.add_argument("--build-dir", type=Path, default=Path("build"))
    parser.add_argument("--output", type=Path, default=Path("zen"))
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--cache", default="")
    parser.add_argument("--cflags", default="-O2 -std=c99")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--symbol-map", type=Path)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    args.build_dir.mkdir(parents=True, exist_ok=True)
    try:
        with (args.build_dir / "bootstrap.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            Build(args, lock.fileno()).build()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"build: {error}\n")


if __name__ == "__main__":
    main()
