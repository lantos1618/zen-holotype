#!/usr/bin/env python3
"""Prove that rebuilding the compiler preserves every emitted C unit and the seed."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import fcntl
from functools import partial
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str], *, pass_fds: tuple[int, ...] = ()) -> None:
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            pass_fds=pass_fds)
    if result.returncode:
        sys.stderr.buffer.write(result.stdout)
        raise RuntimeError(f"command failed ({result.returncode}): {shlex.join(command)}")


def emission(directory: Path) -> dict[str, bytes]:
    files = {path.name: path.read_bytes() for path in directory.iterdir()
             if path.suffix == '.c' or path.name == 'zen.h'}
    if 'zen.h' not in files or not any(name.endswith('.c') for name in files):
        raise RuntimeError(f"incomplete C emission: {directory}")
    if any(not content for content in files.values()):
        raise RuntimeError(f"empty C emission: {directory}")
    return files


def compare(first: dict[str, bytes], second: dict[str, bytes]) -> None:
    if first.keys() != second.keys():
        changed = sorted(first.keys() ^ second.keys())
        raise RuntimeError(f"compiler fixpoint changed the emitted file set: {changed}")
    changed = [name for name in sorted(first) if first[name] != second[name]]
    if changed:
        raise RuntimeError(f"compiler fixpoint changed emitted bytes: {changed}")


@contextmanager
def workspace(directory: Path):
    """Keep compiler paths stable for ccache, while regenerating all output."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'fixpoint.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        stage = directory / 'stage'
        # An interrupted previous run may have left files behind. Never compare
        # a new compiler against those files or reuse its executable directly.
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir()
        try:
            yield stage, lock.fileno()
        finally:
            shutil.rmtree(stage)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zen', type=Path, default=ROOT / 'zen')
    parser.add_argument('--source', type=Path, default=ROOT / 'src')
    parser.add_argument('--seed', type=Path, default=ROOT / 'seed/zen.c')
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--cflags', default='-O2 -std=c99')
    parser.add_argument('--cache', default=shutil.which('ccache') or '')
    parser.add_argument('--jobs', type=int, default=16)
    parser.add_argument('--work-dir', type=Path, default=ROOT / 'build/fixpoint',
                        help='locked scratch directory; stable paths allow C object cache reuse')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    zen, source, seed = args.zen.resolve(), args.source.resolve(), args.seed.resolve()
    cc, flags, cache = shlex.split(args.cc), shlex.split(args.cflags), shlex.split(args.cache)
    if not cc:
        parser.error('--cc must name a C compiler')
    try:
        with workspace(args.work_dir.resolve()) as (work, lock_fd):
            # A killed parent must not release the workspace while its tools
            # still write there. Children retain this lock until they exit.
            execute = partial(run, pass_fds=(lock_fd,))
            first, second = work / 'first', work / 'second'
            first.mkdir()
            second.mkdir()
            execute([str(zen), 'build', str(source), '--emit-c-dir', str(first)])
            expected = emission(first)
            sources = sorted(first.glob('*.c')) + [source / 'std/proc/proc.c']
            objects = [work / f'unit-{i}.o' for i in range(len(sources))]
            commands = [cache + cc + flags + ['-c', str(src), '-o', str(obj)]
                        for src, obj in zip(sources, objects)]
            with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                list(pool.map(execute, commands))
            rebuilt = work / 'zen-rebuilt'
            execute(cc + [str(obj) for obj in objects] + ['-o', str(rebuilt)])
            execute([str(rebuilt), 'build', str(source), '--emit-c-dir', str(second)])
            compare(expected, emission(second))
            print(f'fixpoint: {len(expected) - 1} C units and zen.h are byte-identical', flush=True)
            regenerated = work / 'seed.c'
            execute([str(rebuilt), 'build', str(source), '--emit-c', '-o', str(regenerated)])
            if not regenerated.is_file() or not regenerated.stat().st_size:
                raise RuntimeError('compiler emitted no seed')
            if regenerated.read_bytes() != seed.read_bytes():
                raise RuntimeError('seed/zen.c is stale; regenerate it from the verified compiler')
            print('fixpoint: checked-in seed matches the rebuilt compiler')
    except (OSError, RuntimeError) as error:
        print(f'fixpoint: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
