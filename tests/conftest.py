"""Shared pytest configuration for the zen test suite.

Stage D deleted the Python reference frontend (zen/*.py); the surviving suite is driven entirely
by the self-hosted `zenc` BINARY (built from the committed bootstrap C by `cc`) via tests/_oracle.py
— so this conftest imports NOTHING from `zen.*`. It only puts tests/ on sys.path so the binary-only
helpers (_oracle, _oracle_corpus) import cleanly.

(The old Python-frontend fixtures — compile_main / namespace / scope / EXAMPLES — went away with the
tests that used them. The binary-driven tests pass Zen source strings directly, no fixture needed.)
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
