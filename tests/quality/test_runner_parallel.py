#!/usr/bin/env python3
"""Shards must cover every selected test once and retain the runner's red gates."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("zen_test_runner", Path(__file__).parents[1] / "run.py")
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


class ParallelRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="zen-runner-check-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tests = [self.make_test(tid) for tid in (
            "corpus/a/one", "corpus/a/two", "corpus/b/three", "example/demo",
            "must-fail/a/four", "must-fail/b/five", "must-fail/b/six",
        )]
        self.collection = runner.Collection(tests=self.tests)

    def make_test(self, tid):
        source = self.root / (tid.replace("/", "_") + ".zen")
        return runner.Test(tid, tid.split("/")[0], "fixture", source, source,
                           source.with_suffix(".expected"), b"")

    def invoke(self, *arguments, outcome=None):
        output = io.StringIO()
        tool = runner.Toolchain("fixture", ["unused-compiler"])
        if outcome is None:
            outcome = lambda test, *_: runner.Result(test, True)
        with patch.object(runner, "discover", return_value=self.collection), \
             patch.object(runner, "make_toolchain", return_value=tool), \
             patch.object(runner.shutil, "which", return_value="unused-cc"), \
             patch.object(runner, "run_one", side_effect=outcome) as run, \
             redirect_stdout(output), redirect_stderr(output):
            code = runner.main(["--jobs", "2", "--stage", "4", *arguments])
        return code, output.getvalue(), run.call_count

    def test_result_cache_hits_skip_execution_and_no_cache_runs_again(self):
        for test in self.tests:
            test.source.write_text("main = () () {}\n")
            test.expected_path.write_bytes(test.expected)
        cache = self.root / "verdicts"
        report = self.root / "cached.json"
        arguments = ["--result-cache", str(cache), "--timings-json", str(report)]
        with patch.object(runner.ResultCache, "context", return_value="stable-test-toolchain"):
            first = self.invoke(*arguments)
            second = self.invoke(*arguments)
            self.assertEqual(first[0], 0, first[1])
            self.assertEqual(first[2], len(self.tests))
            self.assertEqual(second[0], 0, second[1])
            self.assertEqual(second[2], 0)
            data = json.loads(report.read_text())
            self.assertEqual(data["cached"], len(self.tests))
            self.assertTrue(all(row["cached"] for row in data["tests"]))
            third = self.invoke(*arguments, "--no-result-cache")
            self.assertEqual(third[0], 0, third[1])
            self.assertEqual(third[2], len(self.tests))
            refresh = self.invoke(*arguments, "--refresh-result-cache")
            self.assertEqual(refresh[2], len(self.tests))
            self.tests[0].source.write_text("main = () () { changed() }\n")
            changed = self.invoke(*arguments)
            self.assertEqual(changed[2], 1)
            # A cached pass must never hide collection errors outside selection.
            self.collection.problems = ["broken expectation elsewhere"]
            blocked = self.invoke(*arguments, "--filter", "corpus/*")
            self.assertEqual(blocked[0], 2)
            self.assertEqual(blocked[2], 0)

    def test_shards_partition_filtered_tests_independent_of_discovery_order(self):
        patterns = ["corpus/*", "must-fail/a/*", "corpus/a/*"]
        selected = runner.select(self.tests, patterns)
        parts = [runner.shard(list(reversed(selected)), (index, 3)) for index in range(1, 4)]
        ids = [test.tid for part in parts for test in part]
        self.assertEqual(sorted(ids), sorted(test.tid for test in selected))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertLessEqual(max(map(len, parts)) - min(map(len, parts)), 1)
        for index, part in enumerate(parts, 1):
            code, output, calls = self.invoke("--list", "--filter", "corpus/*",
                                               "--filter", "must-fail/a/*",
                                               "--shard", f"{index}/3")
            self.assertEqual(code, 0, output)
            self.assertEqual(output.splitlines(), [test.tid for test in part])
            self.assertEqual(calls, 0)

    def test_invalid_shards_and_nonpositive_worker_counts_are_usage_errors(self):
        for value in ("0/4", "5/4", "1/0", "-1/4", "1/-4", "1", "1/2/3", "a/2"):
            with self.subTest(shard=value), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    runner.parse_args([f"--shard={value}"])
                self.assertEqual(error.exception.code, 2)
        for flag in ("--jobs", "--timings"):
            with self.subTest(flag=flag), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    runner.parse_args([flag, "0"])
                self.assertEqual(error.exception.code, 2)

    def test_empty_shard_or_selection_never_passes(self):
        for mode in ([], ["--list"]):
            for selection in (["--filter", "corpus/a/one", "--shard", "2/2"],
                              ["--filter", "missing/*", "--shard", "1/2"]):
                with self.subTest(mode=mode, selection=selection):
                    code, output, calls = self.invoke(*mode, *selection)
                    self.assertEqual(code, 2, output)
                    self.assertEqual(calls, 0)

    def test_discovery_errors_outside_shard_still_block_execution(self):
        self.collection.problems = ["must-fail/outside: unreadable expectation"]
        code, output, calls = self.invoke("--filter", "corpus/*", "--shard", "1/2")
        self.assertEqual(code, 2, output)
        self.assertIn("outside", output)
        self.assertEqual(calls, 0)

    def test_uncollected_files_outside_shard_still_fail(self):
        self.collection.uncollected = ["must-fail/outside/orphan.zen"]
        code, output, calls = self.invoke("--filter", "corpus/*", "--shard", "1/2")
        self.assertEqual(code, 1, output)
        self.assertEqual(calls, 2)
        self.assertIn("orphan.zen", output)

    def test_empty_example_suite_still_blocks_filtered_shards(self):
        self.collection.tests = [test for test in self.tests if test.kind != runner.EXAMPLE]
        code, output, calls = self.invoke("--filter", "corpus/*", "--shard", "1/2")
        self.assertEqual(code, 2, output)
        self.assertIn("example/ suite collected no programs", output)
        self.assertEqual(calls, 0)

    def test_timings_include_failures_and_deferred_tests_without_changing_verdicts(self):
        report = self.root / "new/reports/timings.json"
        deferred = self.tests[3]
        deferred.stage_at = 5
        deferred.stage_path = self.root / "main.stage"

        def outcome(test, *_):
            return runner.Result(test, test not in (self.tests[0], deferred), ["fixture rejection"])

        code, output, calls = self.invoke("--timings", "2", "--timings-json", str(report), outcome=outcome)
        self.assertEqual(code, 1, output)
        self.assertEqual(calls, len(self.tests))
        data = json.loads(report.read_text())
        self.assertEqual(data["jobs"], 2)
        self.assertIsNone(data["shard"])
        self.assertGreater(data["elapsed_seconds"], 0)
        self.assertEqual([row["id"] for row in data["tests"]], [test.tid for test in self.tests])
        statuses = {row["id"]: row["status"] for row in data["tests"]}
        self.assertEqual(statuses[self.tests[0].tid], "failed")
        self.assertEqual(statuses[deferred.tid], "deferred")
        self.assertEqual(statuses[self.tests[1].tid], "passed")
        self.assertTrue(all(row["seconds"] > 0 for row in data["tests"]))
        slow = output.split("slowest tests", 1)[1].splitlines()[1:]
        self.assertEqual(len(slow), 2)

    def test_shard_json_describes_only_executed_tests(self):
        report = self.root / "timings.json"
        code, output, calls = self.invoke("--filter", "corpus/*", "--shard", "2/2",
                                         "--timings-json", str(report))
        self.assertEqual(code, 0, output)
        self.assertEqual(calls, 1)
        data = json.loads(report.read_text())
        self.assertEqual(data["shard"], {"index": 2, "count": 2})
        self.assertEqual(data["filter"], ["corpus/*"])
        self.assertEqual([row["id"] for row in data["tests"]], ["corpus/a/two"])

    def test_import_manifest_preserves_transitive_modules_overrides_and_private_copies(self):
        sources = self.root / "compiler-src"
        files = {
            "std/core/core.zen": "Core = {}\n",
            "std/parse/parse.zen": "Lex = std.lex\n",
            "std/lex/lex.zen": "Lex = {}\n",
            "std/ast/ast.zen": "Ast = {}\n",
            "api/api.zen": "Worker = worker\nParse = std.parse\n",
            "worker/worker.zen": "Core = std.core\n",
            "shadow/shadow.zen": "Wrong = {}\n",
        }
        for name, content in files.items():
            path = sources / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        # copytree follows source symlinks today; sharing a manifest must not
        # change the bytes staged or introduce links back into the checkout.
        shared = self.root / "linked-source"
        shared.write_text("Linked = {}\n")
        (sources / "worker/linked.zen").symlink_to(shared)
        case = self.root / "program"
        (case / "shadow").mkdir(parents=True)
        (case / "main.zen").write_text("Api = api\nShadow = shadow\n")
        (case / "shadow/shadow.zen").write_text("Mine = {}\n")
        test = runner.Test("corpus/fixture/program", runner.CORPUS, "fixture",
                           case, case / "main.zen", case / "main.expected", b"", is_dir=True)
        with patch.object(runner, "_modules_named_in", wraps=runner._modules_named_in) as scan:
            tool = runner.Toolchain("fixture", ["unused"], src_root=sources)
            scans = scan.call_count
            first = runner.stage(test, tool, self.root / "first")
            second = runner.stage(test, tool, self.root / "second")
            # Each test's own namespace is scanned once; src modules are not.
            self.assertEqual(scan.call_count, scans + 2)
        self.assertTrue((first / "std/parse/parse.zen").is_file())
        self.assertTrue((first / "std/lex/lex.zen").is_file())
        self.assertFalse((first / "std/ast").exists())
        self.assertEqual((first / "shadow/shadow.zen").read_text(), "Mine = {}\n")
        self.assertEqual((first / "worker/linked.zen").read_text(), shared.read_text())
        self.assertFalse((first / "worker/linked.zen").is_symlink())
        staged = lambda root: {path.relative_to(root): path.read_bytes()
                               for path in root.rglob("*") if path.is_file()}
        self.assertEqual(staged(first), staged(second))
        (first / "worker/worker.zen").write_text("changed privately\n")
        self.assertEqual((second / "worker/worker.zen").read_text(), files["worker/worker.zen"])
        self.assertEqual((sources / "worker/worker.zen").read_text(), files["worker/worker.zen"])
        tool.check_source_state()
        # A source edit during the invocation invalidates shared import facts.
        (sources / "worker/worker.zen").write_text("New = missing_module\n")
        with self.assertRaisesRegex(runner.HarnessError, "sources changed"):
            tool.check_source_state()

    @unittest.skipUnless((runner.REPO_ROOT / "zen").is_file(), "requires built Zen compiler")
    def test_staged_library_outranks_library_beside_compiler(self):
        staged = self.root / "staged"
        staged.mkdir()
        shutil.copytree(runner.REPO_ROOT / "src/std", staged / "std")
        (staged / "std/runner_probe.zen").write_text(
            'value* = () str { "staged-library" }\n')
        source = staged / "main.zen"
        source.write_text('value = std.runner_probe\n'
                          'main = (env: Env) Res<i32, AllocError> { '
                          'println("{}", value()); Ok(0) }\n')
        compiler = runner.REPO_ROOT / "zen"
        tool = runner.Toolchain("zen", [str(compiler)])
        output = self.root / "staged.c"
        command = tool.command(source, output, staged, "main.zen")
        environment = dict(os.environ)
        environment.pop("ZEN_STD", None)
        compiled = subprocess.run(command, capture_output=True, text=True,
                                  env=environment, timeout=30)
        self.assertEqual(compiled.returncode, 0, compiled.stderr + compiled.stdout)
        self.assertIn("staged-library", output.read_text())
        # Removing explicit library selection reproduces the old behavior:
        # this module does not exist beside the compiler executable.
        offset = command.index("--std")
        control = command[:offset] + command[offset + 2:]
        rejected = subprocess.run(control, capture_output=True, text=True,
                                  env=environment, timeout=30)
        self.assertNotEqual(rejected.returncode, 0, rejected.stdout)
        self.assertIn("runner_probe", rejected.stderr + rejected.stdout)

    def test_harness_errors_and_report_write_errors_are_exit_two(self):
        def broken(*_):
            raise runner.HarnessError("fixture unavailable")
        code, output, _ = self.invoke("--shard", "1/2", outcome=broken)
        self.assertEqual(code, 2, output)
        code, output, _ = self.invoke("--shard", "1/2", "--timings-json", str(self.root))
        self.assertEqual(code, 2, output)
        self.assertIn("cannot write timing report", output)
        with patch.object(runner.Toolchain, "check_source_state",
                          side_effect=runner.HarnessError("compiler sources changed")):
            code, output, calls = self.invoke("--shard", "1/2")
        self.assertEqual(code, 2, output)
        self.assertGreater(calls, 0)
        self.assertIn("compiler sources changed", output)


@unittest.skipUnless(shutil.which("cc") and shutil.which("ccache"), "requires cc and ccache")
class NativeCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="zen-native-check-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        environment = patch.dict(os.environ, {"CCACHE_DIR": str(self.root / "ccache")})
        environment.start()
        self.addCleanup(environment.stop)
        self.compiler = runner.CCompiler("cc", ["-O0", "-g"], shutil.which("ccache"),
                                         self.root / "stable", 20)
        self.count = 0

    def compile(self, content, native=()):
        self.count += 1
        work = self.root / f"invocation-{self.count}"
        work.mkdir()
        source, binary = work / "out.c", work / "prog"
        source.write_text(content)
        result = self.compiler.build("corpus/fixture/same-test", source, binary, list(native))
        return result, binary

    def cache_hits(self):
        stats = subprocess.check_output(["ccache", "--print-stats"], text=True)
        counts = dict(line.split() for line in stats.splitlines())
        return int(counts["direct_cache_hit"]) + int(counts["preprocessed_cache_hit"])

    def test_objects_reuse_across_invocations_and_track_headers_flags_sources_and_native(self):
        header = self.root / "value.h"
        header.write_text("#define VALUE 1\n")
        # A relative flag keeps its original meaning: cache compilation must
        # not change cwd to the stable C scratch directory.
        self.compiler.flags += ["-include", os.path.relpath(header)]
        native = self.root / "native.c"
        native.write_text("int native_value(void) { return 2; }\n")
        source = ("#ifndef EXTRA\n#define EXTRA 0\n#endif\n"
                  "int native_value(void); int main(void) { return VALUE + EXTRA + native_value(); }\n")
        first, binary = self.compile(source, [str(native)])
        self.assertEqual(first.code, 0, first.stderr)
        self.assertEqual(subprocess.run([str(binary)]).returncode, 3)
        hits = self.cache_hits()
        second, binary = self.compile(source, [str(native)])
        self.assertEqual(second.code, 0, second.stderr)
        self.assertEqual(subprocess.run([str(binary)]).returncode, 3)
        self.assertGreater(self.cache_hits(), hits)
        header.write_text("#define VALUE 4\n")
        changed, binary = self.compile(source, [str(native)])
        self.assertEqual(changed.code, 0, changed.stderr)
        self.assertEqual(subprocess.run([str(binary)]).returncode, 6)
        self.compiler.flags += ["-DEXTRA=1"]
        changed, binary = self.compile(source, [str(native)])
        self.assertEqual(changed.code, 0, changed.stderr)
        self.assertEqual(subprocess.run([str(binary)]).returncode, 7)
        hits = self.cache_hits()
        native.write_text("int native_value(void) { return 3; }\n")
        changed, binary = self.compile(source, [str(native)])
        self.assertEqual(changed.code, 0, changed.stderr)
        self.assertEqual(subprocess.run([str(binary)]).returncode, 8)
        self.assertGreater(self.cache_hits(), hits)
        rejected, binary = self.compile(source + "this is invalid C\n", [str(native)])
        self.assertNotEqual(rejected.code, 0)
        self.assertFalse(binary.exists())

    def test_success_without_new_object_does_not_reuse_stale_output(self):
        result, _ = self.compile("int main(void) { return 0; }\n")
        self.assertEqual(result.code, 0, result.stderr)
        liar = self.root / "empty-cache"
        liar.write_text("#!/bin/sh\nexit 0\n")
        liar.chmod(0o755)
        self.compiler.cache = str(liar)
        with self.assertRaisesRegex(runner.HarnessError, "without producing an object"):
            self.compile("int main(void) { return 1; }\n")

    def test_path_sensitive_c_keeps_original_include_and_file_semantics(self):
        source = self.root / "original.c"
        (self.root / "local.h").write_text("#define VALUE 3\n")
        source.write_text('#include "local.h"\n#include <stdio.h>\n'
                          'int main(void) { puts(__FILE__); return VALUE; }\n')
        binary = self.root / "prog"
        result = self.compiler.build("corpus/fixture/path", source, binary, [])
        self.assertEqual(result.code, 0, result.stderr)
        program = subprocess.run([str(binary)], capture_output=True, text=True)
        self.assertEqual(program.returncode, 3)
        self.assertEqual(program.stdout, str(source) + "\n")
        self.assertFalse(self.compiler.work_dir.exists())

    def test_cached_diagnostics_and_link_failures_are_preserved(self):
        source = '#warning fixture-warning\nint main(void) { return 0; }\n'
        for _ in range(2):
            result, binary = self.compile(source)
            self.assertEqual(result.code, 0, result.stderr)
            self.assertIn(b"fixture-warning", result.stderr)
            self.assertTrue(binary.is_file())
        # An object cache hit never bypasses the current link step.
        source = 'void missing(void); int main(void) { missing(); return 0; }\n'
        for _ in range(2):
            result, binary = self.compile(source)
            self.assertNotEqual(result.code, 0)
            self.assertIn(b"missing", result.stderr)
            self.assertFalse(binary.exists())


class ResultCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="zen-verdict-check-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "case.zen"
        self.source.write_text("main = () () {}\n")
        self.expected = self.source.with_suffix(".expected")
        self.expected.write_text("")
        self.test = runner.Test("corpus/fixture/case", runner.CORPUS, "fixture",
                                self.source, self.source, self.expected, b"")
        self.sources = self.root / "sources"
        for name, content in {
            "std/core/core.zen": "Core = {}\n",
            "std/parse/parse.zen": "Parser = {}\n",
            "api/api.zen": "Worker = worker\n",
            "worker/worker.zen": "Worker = {}\n",
            "unrelated/unrelated.zen": "Other = {}\n",
        }.items():
            path = self.sources / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.args = runner.parse_args(["--result-cache", str(self.root / "results"), "--stage", "4"])
        self.context = patch.object(runner.ResultCache, "context", return_value="fixture-toolchain")
        self.context.start()
        self.addCleanup(self.context.stop)

    def cache(self):
        tool = runner.Toolchain("fixture", ["unused"], src_root=self.sources)
        return runner.ResultCache(self.args.result_cache, tool, self.args)

    def test_reuses_only_passes_and_corrupt_records_miss(self):
        cache = self.cache()
        key = cache.key(self.test)
        self.assertIsNone(cache.lookup(self.test, key))
        cache.remember(runner.Result(self.test, False, ["deliberately broken"]), key)
        cache.publish()
        self.assertFalse(self.args.result_cache.exists())
        cache.remember(runner.Result(self.test, True, cacheable=False), key)
        cache.publish()
        self.assertFalse(self.args.result_cache.exists())
        cache.remember(runner.Result(self.test, True, detail="compiler note"), key)
        cache.publish()
        hit = self.cache().lookup(self.test, key)
        self.assertTrue(hit.cached)
        self.assertEqual(hit.detail, "compiler note")
        path = self.args.result_cache / (key + ".json")
        path.write_text("interrupted write")
        self.assertIsNone(cache.lookup(self.test, key))
        path.write_text(json.dumps({"version": 1, "key": key, "passed": False, "detail": ""}))
        self.assertIsNone(cache.lookup(self.test, key))
        self.test.stage_at = 5
        self.assertIsNone(cache.key(self.test))

    def test_source_sidecar_additions_deletions_and_modes_invalidate(self):
        baseline = self.cache().key(self.test)
        original = self.source.read_bytes()
        before = self.source.stat()
        self.source.write_bytes(original.replace(b"main", b"fail"))
        os.utime(self.source, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertNotEqual(self.cache().key(self.test), baseline)
        self.source.write_bytes(original)
        self.assertEqual(self.cache().key(self.test), baseline)
        for suffix in ("expected", "stdin", "args", "env", "stderr", "count", "exit", "stage"):
            with self.subTest(sidecar=suffix):
                sidecar = self.source.with_suffix("." + suffix)
                prior = sidecar.read_bytes() if sidecar.exists() else None
                sidecar.write_text("changed\n")
                self.assertNotEqual(self.cache().key(self.test), baseline)
                if prior is None:
                    sidecar.unlink()
                else:
                    sidecar.write_bytes(prior)
                self.assertEqual(self.cache().key(self.test), baseline)
        self.source.chmod(0o700)
        self.assertNotEqual(self.cache().key(self.test), baseline)

    def test_exact_staged_closure_includes_transitive_dependencies_not_pruned_modules(self):
        baseline = self.cache().key(self.test)
        for name in ("unrelated/unrelated.zen", "std/parse/parse.zen"):
            path = self.sources / name
            path.write_text(path.read_text() + "New = {}\n")
            self.assertEqual(self.cache().key(self.test), baseline)
        self.source.write_text("Api = api\nmain = () () {}\n")
        imported = self.cache().key(self.test)
        worker = self.sources / "worker/worker.zen"
        worker.write_text(worker.read_text() + "New = {}\n")
        self.assertNotEqual(self.cache().key(self.test), imported)
        prelude = self.sources / "std/core/core.zen"
        previous = self.cache().key(self.test)
        prelude.write_text(prelude.read_text() + "New = {}\n")
        self.assertNotEqual(self.cache().key(self.test), previous)
        extra = self.sources / "worker/new.zen"
        previous = self.cache().key(self.test)
        extra.write_text("Added = {}\n")
        self.assertNotEqual(self.cache().key(self.test), previous)

    def test_directory_resources_and_local_module_overrides_enter_keys(self):
        case = self.root / "directory"
        (case / "worker").mkdir(parents=True)
        (case / "main.zen").write_text("Api = api\n")
        (case / "worker/worker.zen").write_text("Mine = {}\n")
        (case / "main.expected").write_text("")
        test = runner.Test("corpus/fixture/directory", runner.CORPUS, "fixture", case,
                           case / "main.zen", case / "main.expected", b"", is_dir=True)
        baseline = self.cache().key(test)
        (self.sources / "worker/worker.zen").write_text("Ignored = {}\n")
        self.assertEqual(self.cache().key(test), baseline)
        (case / "resource.bin").write_bytes(b"resource")
        self.assertNotEqual(self.cache().key(test), baseline)

    def test_input_edits_during_run_never_publish_and_cached_hits_are_rechecked(self):
        cache = self.cache()
        key = cache.key(self.test)
        cache.lookup(self.test, key)
        cache.remember(runner.Result(self.test, True), key)
        self.expected.write_text("changed during execution")
        with self.assertRaisesRegex(runner.HarnessError, "inputs changed"):
            cache.publish()
        self.assertFalse(self.args.result_cache.exists())
        self.expected.write_text("")
        cache = self.cache()
        key = cache.key(self.test)
        cache.lookup(self.test, key)
        cache.remember(runner.Result(self.test, True), key)
        cache.publish()
        warm = self.cache()
        self.assertTrue(warm.lookup(self.test, warm.key(self.test)).cached)
        self.source.write_text("changed during warm lookup")
        with self.assertRaisesRegex(runner.HarnessError, "inputs changed"):
            warm.publish()

    def test_artifacts_reuse_compilation_but_execute_and_assert_again(self):
        from types import SimpleNamespace
        tool = runner.Toolchain("fixture", ["unused"], src_root=self.sources)
        compiled, executed = [], []
        stdout = [b""]
        def process(argv, *args, **kwargs):
            if argv[0] == "unused":
                compiled.append("zen")
                Path(argv[-1]).write_text("int main(void) { return 0; }\n")
            else:
                executed.append(argv)
            return runner.Run(argv, 0, b"" if argv[0] == "unused" else stdout[0], b"", False, False)
        def build(tid, source, binary, native):
            compiled.append("cc")
            binary.write_bytes(b"fixture executable")
            binary.chmod(0o755)
            return runner.Run([], 0, b"", b"", False, False)
        tool.c_compiler = SimpleNamespace(build=build)
        for index in range(3):
            cache = runner.ResultCache(self.args.result_cache, tool, self.args)
            self.args.verdict_cache = cache
            key = cache.key(self.test)
            self.assertIsNone(cache.lookup(self.test, key))
            work = self.root / f"work-{index}"
            work.mkdir()
            if index == 2:
                stdout[0] = b"changed external state"
            with patch.object(runner, "run_process", side_effect=process), \
                 patch.object(runner, "deterministic_binary", return_value=False):
                result = runner.run_corpus(self.test, tool, work, self.args)
            self.assertEqual(result.artifact_cached, index > 0)
            self.assertEqual(result.ok, index < 2)
            cache.remember(result, key)
            cache.publish()
        self.assertEqual(compiled, ["zen", "cc"])
        self.assertEqual(len(executed), 3)
        self.assertIn("stdout does not match", result.reasons[0])
        self.assertFalse((self.args.result_cache / (key + ".json")).exists())

    def test_artifact_corruption_modes_refresh_and_path_sensitive_c(self):
        cache = self.cache()
        key = cache.key(self.test)
        cache.lookup(self.test, key)
        work = self.root / "work"
        work.mkdir()
        (work / "out.c").write_text("int main(void) { return 0; }\n")
        (work / "prog").write_bytes(b"executable bytes")
        (work / "prog").chmod(0o755)
        cache.remember_binary(self.test, work)
        cache.publish()
        destination = self.root / "restored"
        destination.mkdir()
        self.assertTrue(cache.restore_binary(self.test, destination))
        artifact = self.args.result_cache / (key + ".artifact")
        for corrupt in (lambda: (artifact / "prog").chmod(0o644),
                        lambda: (artifact / "prog").write_bytes(b"wrong")):
            corrupt()
            self.assertFalse(cache.restore_binary(self.test, destination))
            repaired = self.cache()
            repaired.lookup(self.test, key)
            repaired.remember_binary(self.test, work)
            repaired.publish()
            self.assertTrue(repaired.restore_binary(self.test, destination))
        self.args.refresh_result_cache = True
        self.assertFalse(cache.restore_binary(self.test, destination))
        self.args.refresh_result_cache = False
        for marker in ('__FILE__', '__DATE__', str(work), '#include "relative.h"'):
            (work / "out.c").write_text(marker)
            fresh = self.cache()
            fresh.lookup(self.test, key)
            fresh.remember_binary(self.test, work)
            self.assertEqual(fresh.artifacts, [])

    def test_shared_source_snapshots_avoid_repeated_reads_and_reject_midrun_edits(self):
        self.source.write_text("Api = api\nmain = () () {}\n")
        cache = self.cache()
        with patch.object(cache, "file_digest", wraps=cache.file_digest) as digest, \
             patch.object(runner, "sublayers_named_in", wraps=runner.sublayers_named_in) as votes:
            key = cache.key(self.test)
            cache.key(self.test)
        self.assertTrue(all(not call.args[0].is_relative_to(self.sources)
                            for call in digest.call_args_list))
        self.assertTrue(all(not call.args[0].is_relative_to(self.sources)
                            for call in votes.call_args_list))
        cache.lookup(self.test, key)
        cache.remember(runner.Result(self.test, True), key)
        (self.sources / "worker/worker.zen").write_text("changed during invocation")
        with self.assertRaisesRegex(runner.HarnessError, "sources changed"):
            cache.publish()
        self.assertFalse(self.args.result_cache.exists())

    def test_non_zen_source_inventory_edits_are_detected(self):
        tool = runner.Toolchain("fixture", ["unused"], src_root=self.sources)
        (self.sources / "worker/new.h").write_text("new native header")
        with self.assertRaisesRegex(runner.HarnessError, "sources changed"):
            tool.check_source_state()

    @unittest.skipUnless(shutil.which("cc") and sys.platform.startswith("linux"),
                         "requires Linux native toolchain")
    def test_native_context_tracks_compiler_harness_environment_flags_stage_and_floor(self):
        self.context.stop()
        compiler = self.root / "compiler"
        shutil.copy2("/bin/true", compiler)
        harness = self.root / "runner.py"
        harness.write_text("harness version one")
        floor = self.root / "native.c"
        floor.write_text("native floor one")
        tool = runner.Toolchain("fixture", [str(compiler)])
        with patch.object(runner, "__file__", str(harness)), \
             patch.object(runner, "NATIVE_FLOORS", ((b"probe", (floor,), ()),)):
            cache = runner.ResultCache(self.args.result_cache, tool, self.args)
            baseline = cache.identity
            self.assertIsNotNone(baseline)
            changes = (
                (lambda: compiler.write_bytes(compiler.read_bytes() + b"changed"),
                 lambda: shutil.copy2("/bin/true", compiler)),
                (lambda: harness.write_text("harness version two"),
                 lambda: harness.write_text("harness version one")),
                (lambda: floor.write_text("native floor two"),
                 lambda: floor.write_text("native floor one")),
                (lambda: setattr(self.args, "cc_flags", "-std=c11 -O2"),
                 lambda: setattr(self.args, "cc_flags", "-std=c11 -O0 -g -Werror=return-type")),
                (lambda: setattr(self.args, "stage", 5),
                 lambda: setattr(self.args, "stage", 4)),
            )
            for change, restore in changes:
                change()
                self.assertNotEqual(cache.context(), baseline)
                restore()
            with patch.dict(os.environ, {"ZEN_CACHE_SENTINEL": "private-value"}):
                self.assertNotEqual(cache.context(), baseline)
            # Executable scripts can have arbitrary undeclared dependencies.
            compiler.write_text("#!/bin/sh\nexec /bin/true\n")
            self.assertIsNone(cache.context())

    @unittest.skipUnless(shutil.which("cc") and shutil.which("nm"), "requires native toolchain")
    def test_unknown_clock_and_process_symbols_bypass_verdict_cache(self):
        source, binary = self.root / "native.c", self.root / "native"
        for body, allowed in (
            ('#include <stdio.h>\nint main(void) { puts("hello"); }', True),
            ('#include <time.h>\nint main(void) { return time(0) == 0; }', False),
            ('#include <stdlib.h>\nint main(void) { return system("true"); }', False),
        ):
            source.write_text(body)
            subprocess.run(["cc", str(source), "-o", str(binary)], check=True)
            self.assertEqual(runner.deterministic_binary(binary, 10), allowed)


if __name__ == "__main__":
    unittest.main()
