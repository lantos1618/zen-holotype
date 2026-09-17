#!/usr/bin/env python3
"""Exercise the real LSP process, including document ownership and lifecycle."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
ZEN = ROOT / "zen"


class Client:
    def __init__(self, root=None, initialize=True, leak_check=False):
        environment = dict(os.environ)
        if leak_check:
            environment["ASAN_OPTIONS"] = "detect_leaks=1"
        self.process = subprocess.Popen([str(ZEN), "lsp"], cwd=ROOT, env=environment,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
        self.messages = queue.Queue()
        self.diagnostics = {}
        self.counter = 0
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        if initialize:
            self.request("initialize", {"rootUri": root})
            self.send("initialized")

    def read(self):
        try:
            while line := self.process.stdout.readline():
                if not line.startswith(b"Content-Length:"):
                    raise AssertionError(f"non-protocol stdout: {line!r}")
                length = int(line.partition(b":")[2])
                if self.process.stdout.readline() != b"\r\n":
                    raise AssertionError("invalid header separator")
                self.messages.put(json.loads(self.process.stdout.read(length)))
        except Exception as error:
            self.messages.put(error)

    def send(self, method, params=None, ident=None):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if ident is not None:
            message["id"] = ident
        self.raw(message)

    def raw(self, message):
        body = json.dumps(message).encode()
        self.process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        self.process.stdin.flush()

    def response(self, ident):
        while True:
            message = self.messages.get(timeout=20)
            if isinstance(message, Exception):
                raise message
            if message.get("method") == "textDocument/publishDiagnostics":
                params = message["params"]
                self.diagnostics[params["uri"]] = params["diagnostics"]
            elif message.get("id") == ident:
                return message

    def request(self, method, params=None):
        self.counter += 1
        self.send(method, params, self.counter)
        return self.response(self.counter)

    def open(self, uri, text, version=1):
        self.send("textDocument/didOpen", {"textDocument": {
            "uri": uri, "text": text, "version": version, "languageId": "zen"}})

    def change(self, uri, changes, version=2):
        self.send("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": version}, "contentChanges": changes})

    def symbols(self, uri):
        response = self.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
        return [entry["name"] for entry in response["result"]]

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=10)
        self.reader.join(timeout=5)
        self.process.stdin.close()
        self.process.stdout.close()
        errors = self.process.stderr.read().decode(errors="replace")
        self.process.stderr.close()
        if "AddressSanitizer" in errors or "runtime error:" in errors:
            raise AssertionError(errors)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="zen-lsp-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def client(self, root=None, initialize=True, leak_check=False):
        client = Client(root, initialize, leak_check)
        self.addCleanup(client.close)
        return client

    def test_shutdown_waits_for_exit_and_rejects_requests(self):
        client = self.client()
        self.assertIsNone(client.request("shutdown")["result"])
        with self.assertRaises(subprocess.TimeoutExpired):
            client.process.wait(timeout=0.1)
        self.assertEqual(client.request("unknown")["error"]["code"], -32600)
        client.send("exit")
        self.assertEqual(client.process.wait(timeout=5), 0)

    def test_exit_without_shutdown_terminates_before_initialization(self):
        client = self.client(initialize=False)
        client.send("exit")
        self.assertEqual(client.process.wait(timeout=5), 1)

    def test_full_changes_apply_in_order_and_empty_changes_preserve_text(self):
        client = self.client()
        uri = (self.root / "buffer.zen").as_uri()
        client.open(uri, "original = 1\n")
        client.change(uri, [{"text": "first = 1\n"}, {"text": "last = 2\n"}])
        self.assertEqual(client.symbols(uri), ["last"])
        client.change(uri, [], version=3)
        self.assertEqual(client.symbols(uri), ["last"])

    def test_malformed_change_is_atomic(self):
        client = self.client()
        uri = (self.root / "buffer.zen").as_uri()
        client.open(uri, "original = 1\n")
        client.change(uri, [{"text": "partial = 1\n"}, {"text": 123}])
        self.assertEqual(client.symbols(uri), ["original"])
        client.change(uri, [{"text": "incremental = 1", "range": {}}], version=3)
        self.assertEqual(client.symbols(uri), ["original"])

    def test_stale_version_cannot_replace_newer_buffer(self):
        client = self.client()
        uri = (self.root / "buffer.zen").as_uri()
        client.open(uri, "original = 1\n", version=5)
        client.change(uri, [{"text": "stale = 1\n"}], version=4)
        self.assertEqual(client.symbols(uri), ["original"])

    def test_changes_cannot_open_documents(self):
        client = self.client()
        uri = (self.root / "buffer.zen").as_uri()
        client.change(uri, [{"text": "unexpected = 1\n"}])
        self.assertEqual(client.request("textDocument/documentSymbol", {
            "textDocument": {"uri": uri}})["error"]["code"], -32602)

    def test_independent_diagnostics_survive_other_document_changes(self):
        client = self.client(self.root.as_uri())
        uris = []
        for name in ("a", "b"):
            path = self.root / f"{name}.zen"
            text = f"{name}* = () i32 {{ missing_{name} }}\n"
            path.write_text(text)
            uris.append(path.as_uri())
            client.open(path.as_uri(), text)
            client.symbols(path.as_uri())
        self.assertTrue(client.diagnostics[uris[0]])
        self.assertTrue(client.diagnostics[uris[1]])
        client.change(uris[1], [{"text": "b* = () i32 { 1 }\n"}])
        client.symbols(uris[1])
        self.assertTrue(client.diagnostics[uris[0]])
        self.assertEqual(client.diagnostics[uris[1]], [])
        client.send("textDocument/didClose", {"textDocument": {"uri": uris[0]}})
        client.symbols(uris[1])
        self.assertEqual(client.diagnostics[uris[0]], [])

    def test_escaped_workspace_imports_and_definition_uris(self):
        workspace = self.root / "space % # café"
        (workspace / "app").mkdir(parents=True)
        target = workspace / "app/shape.zen"
        target.write_text("Point* = { x*: i32, }\n")
        path = workspace / "app/app.zen"
        text = "Point = app.shape\nnear* = (p: Point) i32 { p.x }\n"
        path.write_text(text)
        client = self.client(workspace.as_uri())
        client.open(path.as_uri(), text)
        result = client.request("textDocument/definition", {
            "textDocument": {"uri": path.as_uri()}, "position": {"line": 1, "character": 13}})
        self.assertEqual(result["result"]["uri"], target.as_uri())
        self.assertEqual(client.diagnostics[path.as_uri()], [])
        # The checked build may borrow this unchanged buffer's storage.
        client.change(path.as_uri(), [{"text": text}])
        again = client.request("textDocument/definition", {
            "textDocument": {"uri": path.as_uri()}, "position": {"line": 1, "character": 13}})
        self.assertEqual(again["result"], result["result"])

    def test_invalid_envelope_returns_invalid_request(self):
        client = self.client()
        for message in ([], {"id": {}, "method": "initialize", "jsonrpc": "2.0"},
                        {"id": 3, "jsonrpc": "2.0"}):
            client.raw(message)
            self.assertEqual(client.response(None)["error"]["code"], -32600)

    def test_invalid_positions_are_rejected(self):
        client = self.client()
        uri = (self.root / "buffer.zen").as_uri()
        client.open(uri, "original = 1\n")
        for position in ({}, {"line": -1, "character": 0}, {"line": 0, "character": "0"}):
            result = client.request("textDocument/hover", {
                "textDocument": {"uri": uri}, "position": position})
            self.assertEqual(result["error"]["code"], -32602)

    def test_transport_refuses_oversized_and_malformed_frames(self):
        for data in (b"Content-Length: 999999999999\r\n\r\n",
                     b"Content-Length: nope\r\n\r\n", b"x" * 8194):
            with self.subTest(data=data[:50]):
                client = self.client(initialize=False)
                client.process.stdin.write(data)
                client.process.stdin.flush()
                self.assertEqual(client.process.wait(timeout=5), 1)
                client.reader.join(timeout=5)
                self.assertTrue(client.messages.empty())

    def test_document_retirement_is_leak_free_at_graceful_exit(self):
        client = self.client(leak_check=True)
        left = (self.root / "left.zen").as_uri()
        right = (self.root / "right.zen").as_uri()
        client.open(left, "left = 1\n")
        client.open(right, "right = 1\n")
        for version in range(2, 12):
            client.change(left, [{"text": f"left_{version} = {version}\n"}], version)
            self.assertEqual(client.symbols(left), [f"left_{version}"])
        client.send("textDocument/didClose", {"textDocument": {"uri": left}})
        self.assertEqual(client.symbols(right), ["right"])
        client.request("shutdown")
        client.send("exit")
        self.assertEqual(client.process.wait(timeout=10), 0)

    def test_repeated_edits_and_close_reopen_keep_buffers_independent(self):
        client = self.client()
        left = (self.root / "left.zen").as_uri()
        right = (self.root / "right.zen").as_uri()
        client.open(left, "left = 1\n")
        client.open(right, "right = 1\n")
        for version in range(2, 32):
            client.change(left, [{"text": f"left_{version} = {version}\n"}], version)
            self.assertEqual(client.symbols(right), ["right"])
            self.assertEqual(client.symbols(left), [f"left_{version}"])
        client.send("textDocument/didClose", {"textDocument": {"uri": left}})
        client.open(left, "reopened = 1\n")
        self.assertEqual(client.symbols(left), ["reopened"])
        self.assertEqual(client.symbols(right), ["right"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zen", type=Path, default=ZEN)
    args, rest = parser.parse_known_args()
    ZEN = args.zen.resolve()
    unittest.main(argv=[__file__, *rest])
