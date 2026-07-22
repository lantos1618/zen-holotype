// Minimal VS Code client for the Zen language server: `zen lsp` speaks JSON-RPC over stdio
// and pushes diagnostics on open/change (full-document sync). No other features yet.
const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

let client;

function activate(context) {
  const serverPath = vscode.workspace.getConfiguration("zen").get("serverPath", "zen");
  client = new LanguageClient(
    "zen-lsp",
    "Zen Language Server",
    {
      command: serverPath,
      args: ["lsp"],
      transport: TransportKind.stdio,
    },
    {
      documentSelector: [{ scheme: "file", language: "zen" }],
    }
  );
  client.start();
  context.subscriptions.push({ dispose: () => client && client.stop() });
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
