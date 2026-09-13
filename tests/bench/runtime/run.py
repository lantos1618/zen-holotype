#!/usr/bin/env python3
"""Local generated-program measurements; checksum/allocation gates, no timing gate."""
import argparse
import json
import math
import platform
from pathlib import Path
import shutil
import statistics
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BODIES = {
    'integer': '    Range(0, n).loop((i) { sum = (sum * 33 + i) % 1000003; });',
    'map_vec': '''    values ::= a.Vec<usize>();
    index ::= a.Map<Key, usize>();
    Range(0, n).loop((i) {
        values.add(i * 3 + 7).try();
        index.set(Key(value: i), i).try();
    });
    Range(0, n).loop((i) {
        at = index.get(Key(value: n - i - 1)).ok_or(AllocError.OutOfMemory).try();
        sum = sum + values.get(at).ok_or(AllocError.OutOfMemory).try();
    });''',
    'string': '''    text ::= a.String().try();
    Range(0, n).loop((i) { text.write_usize(i).try(); text.add(58).try(); });
    text.view().loop((byte) { sum = sum + byte.to_usize(); });''',
    'stable_sort': '''    values ::= a.Vec<Item>();
    Range(0, n).loop((i) { values.add(Item(key: (n - i) % 257, index: i)).try(); });
    values.sort(a).try();
    values.loop((h, i, item) { sum = sum + (i % 97 + 1) * (item.key + item.index); });''',
    'callback': '''    Range(0, n).loop((i) {
        sum = apply(sum, (value: usize) usize { (value * 33 + i) % 1000003 });
    });''',
}

def expected(case, n):
    if case in ('integer', 'callback'):
        value = 0
        for i in range(n):
            value = (value * 33 + i) % 1000003
        return value
    if case == 'map_vec':
        return 3 * n * (n - 1) // 2 + 7 * n
    if case == 'string':
        return sum(sum(map(ord, str(i))) + 58 for i in range(n))
    rows = sorted(((n-i) % 257, i) for i in range(n))
    return sum((i % 97 + 1) * (key + index) for i, (key, index) in enumerate(rows))

def command(args):
    start = time.perf_counter()
    result = subprocess.run(list(map(str, args)), text=True, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f'{args}:\n{result.stdout}\n{result.stderr}')
    return result.stdout.strip(), time.perf_counter() - start

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--zen', type=Path, default=ROOT / 'zen')
    parser.add_argument('--std', type=Path, default=ROOT / 'src/std')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=7)
    parser.add_argument('--scale', type=int, default=1)
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--enforce-map-budget', action='store_true')
    parser.add_argument('--quick', action='store_true', help='small semantic/allocation check; no repeated timings')
    args = parser.parse_args()
    if args.repetitions < 1 or args.scale < 1:
        parser.error('repetitions and scale must be positive')
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'environment.json').write_text(json.dumps({
        'platform': platform.platform(), 'cc': command([args.cc, '--version'])[0],
        'flags': ['-O2', '-std=c11'], 'zen': str(args.zen.resolve()),
        'std': str(args.std.resolve()), 'quick': args.quick,
    }, indent=2) + '\n')
    results = []
    template = (HERE / 'main.zen.in').read_text()
    for case_id, (case, body) in enumerate(BODIES.items()):
        sizes = [64, 256] if args.quick else ([1000000, 4000000] if case_id in (0, 4) else [20000, 80000])
        for n in sizes:
            n *= args.scale
            work = args.out / f'{case}-{n}'
            source = work / 'src'
            source.mkdir(parents=True, exist_ok=True)
            shutil.copytree(args.std, source / 'std', dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('ast', 'lex', 'parse'))
            (source / 'main.zen').write_text(template.replace('@N@', str(n)).replace('@BODY@', body))
            _, emit_s = command([args.zen.resolve(), 'build', source, '--entry', 'main.zen', '--emit-c', '-o', work / 'out.c'])
            _, cc_s = command([args.cc, '-O2', '-std=c11', work / 'out.c', '-lm', '-o', work / 'zen-program'])
            command([args.cc, '-O2', '-std=c11', f'-DN={n}', f'-DCASE={case_id}', HERE / 'reference.c', '-o', work / 'c-program'])
            checksum = expected(case, n)
            times = {'zen': [], 'c': []}
            allocations = None
            for repeat in range(2 if args.quick else args.repetitions + 1):
                for language in (('zen', 'c') if repeat % 2 else ('c', 'zen')):
                    output, elapsed = command([work / f'{language}-program'])
                    fields = list(map(int, output.split()))
                    assert fields[0] == checksum, (case, n, language, fields, checksum)
                    if language == 'zen':
                        allocations = fields[1]
                        if args.enforce_map_budget and case == 'map_vec':
                            assert allocations <= 3 * math.ceil(math.log2(n)) + 4, (case, n, allocations)
                    if repeat:
                        times[language].append(elapsed)
            row = dict(case=case, n=n, checksum=checksum, allocator_calls=allocations,
                       generated_c_bytes=(work / 'out.c').stat().st_size,
                       executable_bytes=(work / 'zen-program').stat().st_size,
                       c_executable_bytes=(work / 'c-program').stat().st_size,
                       compiler_emit_seconds=emit_s, c_compile_seconds=cc_s,
                       samples_seconds=times,
                       median_seconds={key: statistics.median(value) for key, value in times.items()})
            results.append(row)
            print(json.dumps(row), flush=True)
            (args.out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')

if __name__ == '__main__':
    main()
