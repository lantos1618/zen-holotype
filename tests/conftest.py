"""Shared pytest configuration for the zen test suite.

The suite is driven entirely by the self-hosted `zenc` BINARY (built from the committed bootstrap C by
`cc`) via tests/_oracle.py, so this conftest imports NOTHING from `zen.*`. It only puts tests/ on
sys.path so the binary-only helpers (_oracle, _oracle_corpus) import cleanly.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
