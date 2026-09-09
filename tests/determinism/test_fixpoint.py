"""The fixpoint gate must reject missing, empty, or changed compiler output."""
from pathlib import Path
import fcntl
import os
import signal
import time
import select
import subprocess
import sys
import tempfile
import unittest

from fixpoint import compare, emission, workspace


class FixpointGate(unittest.TestCase):
    def test_changed_output_is_rejected(self):
        original = {'zen.h': b'typedef int value;', 'compiler.c': b'int x = 1;'}
        compare(original, dict(original))
        for changed in (
            {'zen.h': b'typedef long value;', 'compiler.c': original['compiler.c']},
            {'zen.h': original['zen.h'], 'compiler.c': b'int x = 2;'},
            {'zen.h': original['zen.h']},
            {**original, 'extra.c': b'int y;'},
        ):
            with self.subTest(changed=changed), self.assertRaises(RuntimeError):
                compare(original, changed)

    def test_workspace_is_stable_but_never_reuses_output(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            interrupted = directory / 'stage'
            interrupted.mkdir()
            (interrupted / 'stale.c').write_text('stale compiler output')
            with workspace(directory) as (first, _):
                self.assertEqual(list(first.iterdir()), [])
                (first / 'unit.c').write_text('new compiler output')
            self.assertFalse(first.exists())
            with self.assertRaisesRegex(RuntimeError, 'failed compiler'):
                with workspace(directory) as (second, _):
                    self.assertEqual(first, second)
                    self.assertEqual(list(second.iterdir()), [])
                    (second / 'partial.c').write_text('partial compiler output')
                    raise RuntimeError('failed compiler')
            self.assertFalse(second.exists())

    def test_workspace_serializes_processes_before_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            child = None
            try:
                with workspace(directory) as (stage, _):
                    marker = stage / 'active.c'
                    marker.write_text('active compiler output')
                    code = ("from pathlib import Path; from fixpoint import workspace; "
                            "import sys; print('waiting', flush=True)\n"
                            "with workspace(Path(sys.argv[1])) as (stage, _):\n"
                            " assert not list(stage.iterdir())\n"
                            " print('entered', flush=True)\n")
                    child = subprocess.Popen([sys.executable, '-c', code, str(directory)],
                                             cwd=Path(__file__).resolve().parent,
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                             text=True)
                    self.assertEqual(child.stdout.readline().strip(), 'waiting')
                    self.assertEqual(select.select([child.stdout], [], [], 0.1)[0], [])
                    self.assertEqual(marker.read_text(), 'active compiler output')
                stdout, stderr = child.communicate(timeout=10)
                self.assertEqual(child.returncode, 0, stderr)
                self.assertEqual(stdout.strip(), 'entered')
                self.assertFalse(stage.exists())
            finally:
                if child is not None:
                    if child.poll() is None:
                        child.kill()
                    child.communicate()

    def test_compiler_child_keeps_workspace_locked_after_owner_is_killed(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            scratch = directory / 'scratch'
            ready, release, completed = (directory / name for name in ('ready', 'release', 'completed'))
            writer = (
                "from pathlib import Path; import os,sys,time\n"
                "ready = Path(sys.argv[2]); ready.with_suffix('.tmp').write_text(str(os.getpid()))\n"
                "ready.with_suffix('.tmp').replace(ready)\n"
                "deadline = time.monotonic() + 10\n"
                "while not Path(sys.argv[3]).exists():\n"
                " if time.monotonic() > deadline: raise SystemExit(2)\n"
                " time.sleep(0.01)\n"
                "Path(sys.argv[1]).write_text('old compiler output')\n"
                "Path(sys.argv[4]).write_text('completed')\n"
            )
            owner_code = (
                "from pathlib import Path; import sys; from fixpoint import run,workspace\n"
                "with workspace(Path(sys.argv[1])) as (stage, lock_fd):\n"
                " run([sys.executable, '-c', sys.argv[2], str(stage/'old.c'), "
                "*sys.argv[3:]], pass_fds=(lock_fd,))\n"
            )
            owner = subprocess.Popen(
                [sys.executable, '-c', owner_code, str(scratch), writer,
                 str(ready), str(release), str(completed)],
                cwd=Path(__file__).resolve().parent,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            writer_pid = None
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and owner.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(ready.exists(), 'compiler child did not start')
                writer_pid = int(ready.read_text())
                owner.kill()
                owner.communicate(timeout=10)
                # This is deterministic: the child waits for release, so the
                # old owner is gone but a new owner must still be refused.
                with (scratch / 'fixpoint.lock').open('a') as contender:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                release.touch()
                with workspace(scratch) as (stage, _):
                    self.assertTrue(completed.exists())
                    self.assertEqual(list(stage.iterdir()), [])
                self.assertFalse(stage.exists())
                writer_pid = None
            finally:
                release.touch()
                if owner.poll() is None:
                    owner.kill()
                owner.communicate()
                if writer_pid is not None:
                    try:
                        os.kill(writer_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_empty_emission_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for files in ({}, {'zen.h': b'header'}, {'unit.c': b'body'},
                          {'zen.h': b'header', 'unit.c': b''}):
                for path in directory.iterdir():
                    path.unlink()
                for name, content in files.items():
                    (directory / name).write_bytes(content)
                with self.subTest(files=files), self.assertRaises(RuntimeError):
                    emission(directory)


if __name__ == '__main__':
    unittest.main()
