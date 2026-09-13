const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

// Exercise the compiled extension's activation and configuration listener.
// The host and language client are doubles; no editor or server is restarted.
function host(sourceRoots) {
  const settings = { sourceRoots };
  const clients = [];
  const lifecycle = [];
  const messages = [];
  let configurationChanged;
  let stopGate;
  let startGate;
  const disposable = { dispose() {} };
  const vscode = {
    FileType: { File: 1 },
    Uri: { file: (fsPath) => ({ fsPath }) },
    commands: { registerCommand: () => disposable },
    window: {
      createOutputChannel: () => ({
        appendLine: (text) => messages.push(text),
        show() {},
        dispose() {},
      }),
    },
    workspace: {
      workspaceFolders: [{ uri: { fsPath: "/workspace" } }],
      fs: { stat: async () => ({ type: 1 }) },
      createFileSystemWatcher: () => disposable,
      getConfiguration: (section) => ({
        get: (key, fallback) =>
          section === "zen" && key === "sourceRoots"
            ? settings.sourceRoots ?? fallback
            : fallback,
        inspect: () => ({}),
      }),
      onDidChangeConfiguration: (listener) => {
        configurationChanged = listener;
        return disposable;
      },
    },
  };
  class LanguageClient {
    constructor(_id, _name, serverOptions, clientOptions) {
      this.serverOptions = serverOptions;
      this.clientOptions = clientOptions;
      this.index = clients.length;
      this.active = false;
      clients.push(this);
    }
    async start() {
      assert.ok(!clients.some((client) => client.active), "server starts overlapped");
      this.active = true;
      lifecycle.push(`start ${this.index}`);
      const gate = startGate;
      startGate = undefined;
      if (gate) await gate;
    }
    async stop() {
      lifecycle.push(`stop ${this.index}`);
      const gate = stopGate;
      stopGate = undefined;
      if (gate) await gate;
      this.active = false;
    }
  }
  const exports = {};
  vm.runInNewContext(
    fs.readFileSync(path.join(__dirname, "../out/extension.js"), "utf8"),
    {
      exports,
      process,
      require: (name) => {
        if (name === "vscode") return vscode;
        if (name === "vscode-languageclient/node") {
          return {
            LanguageClient,
            TransportKind: { stdio: 0 },
            ErrorAction: { Shutdown: 1 },
            CloseAction: { DoNotRestart: 0 },
          };
        }
        return require(name);
      },
    },
    { filename: "extension.js" },
  );
  return {
    clients,
    lifecycle,
    messages,
    settings,
    activate: () => exports.activate({ subscriptions: [] }),
    deactivate: () => exports.deactivate(),
    change: (key) => configurationChanged({ affectsConfiguration: (value) => value === key }),
    holdStart: () => {
      let release;
      startGate = new Promise((resolve) => { release = resolve; });
      return release;
    },
    holdStop: () => {
      let release;
      stopGate = new Promise((resolve) => { release = resolve; });
      return release;
    },
  };
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

test("source roots reach initialization, and configuration restarts stay serialized", async () => {
  const initial = [{ path: "scripts/zen_usage.zen", root: "src" }];
  const extension = host(initial);
  await extension.activate();
  assert.equal(extension.clients[0].clientOptions.initializationOptions.sourceRoots, initial);

  const release = extension.holdStop();
  extension.settings.sourceRoots = [{ path: "tools", root: "." }];
  extension.change("zen.sourceRoots");
  await tick();
  extension.settings.sourceRoots = [{ path: "tools/check.zen", root: "src" }];
  extension.change("zen.sourceRoots");
  await tick();
  assert.deepEqual(extension.lifecycle, ["start 0", "stop 0"]);
  assert.equal(extension.clients.length, 1);

  release();
  await tick();
  assert.deepEqual(extension.lifecycle, ["start 0", "stop 0", "start 1", "stop 1", "start 2"]);
  assert.equal(extension.clients[2].clientOptions.initializationOptions.sourceRoots,
    extension.settings.sourceRoots);
  assert.ok(!extension.messages.some((message) => message.includes("restart failed")));

  extension.change("editor.tabSize");
  await tick();
  assert.equal(extension.clients.length, 3);
  await extension.deactivate();
});

test("unconfigured roots leave initialization unchanged; invalid entries reach server validation", async () => {
  const extension = host(undefined);
  await extension.activate();
  assert.equal(extension.clients[0].clientOptions.initializationOptions, undefined);

  const invalid = [{ path: "../outside.zen", root: "src" }];
  extension.settings.sourceRoots = invalid;
  extension.change("zen.sourceRoots");
  await tick();
  assert.equal(extension.clients[1].clientOptions.initializationOptions.sourceRoots, invalid);

  extension.settings.sourceRoots = [];
  extension.change("zen.sourceRoots");
  await tick();
  assert.equal(extension.clients[2].clientOptions.initializationOptions, undefined);
  await extension.deactivate();
});


test("configuration changes wait for initial startup to complete", async () => {
  const extension = host([]);
  const release = extension.holdStart();
  const activating = extension.activate();
  await tick();
  extension.change("zen.sourceRoots");
  await tick();
  assert.deepEqual(extension.lifecycle, ["start 0"]);
  release();
  await activating;
  await tick();
  assert.deepEqual(extension.lifecycle, ["start 0", "stop 0", "start 1"]);
  await extension.deactivate();
});

test("deactivation drains restarts without launching another server", async () => {
  const extension = host([]);
  await extension.activate();
  const release = extension.holdStop();
  extension.change("zen.sourceRoots");
  await tick();
  extension.change("zen.server.args");
  const deactivating = extension.deactivate();
  release();
  await deactivating;
  await tick();
  assert.deepEqual(extension.lifecycle, ["start 0", "stop 0"]);
  assert.ok(extension.clients.every((client) => !client.active));
});
