// editors/vscode/src/extension.ts
//
// Launch `zen lsp` and speak LSP to it.
//
// This file does one thing and refuses to do a second: it resolves the
// server command, starts a LanguageClient over its stdio, and — the part
// that earns its length — SAYS WHAT WENT WRONG WHEN THAT FAILS. As of this
// commit it always fails, because the transport does not exist yet (see
// `editors/README.md`), so the failure path is the path a user is actually
// going to walk and it may not be a silent one.
//
// THIS IS A REMOTE WORKSPACE. `package.json` declares
// `"extensionKind": ["workspace"]`, so this code runs on the machine that
// holds the source and the compiler — not on the machine showing the
// window. Every path below is therefore a remote path, `vscode.workspace.fs`
// is the only correct way to stat one, and `require("fs")` would silently
// look at the wrong disk. `console.log` from here lands in the REMOTE
// extension host log, which is why everything user-facing goes to the
// output channel instead.

import * as path from "path";
import * as vscode from "vscode";
import {
  CloseAction,
  ErrorAction,
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;
let output: vscode.OutputChannel;

// The one thing this extension knows how to explain. It is written once,
// here, because it is the answer to every startup failure this extension
// can currently produce and repeating it would let the copies drift.
const NO_TRANSPORT_YET =
  "The most likely cause, and the one to rule out first:\n" +
  "\n" +
  "  As of the commit this extension was written against, `zen lsp` CANNOT BE\n" +
  "  SPOKEN TO OVER A PIPE. It takes two FILE arguments — a file of requests\n" +
  "  and a file to write replies into — because `Env` has no capability that\n" +
  "  reads a byte stream (src/std/env/env.zen lists argv, vars, out, mem, fs,\n" +
  "  net and threads, and nothing else). docs/design_lsp.md section 4 prices\n" +
  "  the missing `Stdin.read`. The protocol, the framing and hover are all\n" +
  "  real; only the pipe is missing.\n" +
  "\n" +
  "  Check it in one command: run `zen lsp` with no arguments. If it prints a\n" +
  "  usage message and exits 2, that is this, and nothing here is broken.\n" +
  "\n" +
  "If the transport HAS landed, then this is a genuine server failure and the\n" +
  "trace above is the evidence — set `zen.trace.server` to `verbose` and\n" +
  "reload. If the launch shape landed differently, change `zen.server.args`\n" +
  "and nothing else.";

export async function activate(context: vscode.ExtensionContext) {
  output = vscode.window.createOutputChannel("Zen");
  context.subscriptions.push(output);

  const config = vscode.workspace.getConfiguration("zen");
  const configured = config.get<string>("server.path", "./zen");
  const args = config.get<string[]>("server.args", ["lsp"]);

  const command = resolveServerPath(configured);
  output.appendLine(`zen: server command: ${command} ${args.join(" ")}`);

  // Stat it before starting. A LanguageClient handed a nonexistent command
  // reports ENOENT as a crash, and "the server crashed" is the wrong thing
  // to tell someone who has simply not run `make build` — which is the
  // single most likely reason to land here on a fresh checkout.
  if (!(await exists(command))) {
    const message =
      `zen: no server binary at ${command}. ` +
      "Run `make build` in the Zen checkout, or set `zen.server.path`.";
    output.appendLine(message);
    void vscode.window.showErrorMessage(message, "Open Settings").then((pick) => {
      if (pick === "Open Settings") {
        void vscode.commands.executeCommand(
          "workbench.action.openSettings",
          "zen.server.path",
        );
      }
    });
    return;
  }

  const serverOptions: ServerOptions = {
    command,
    args,
    transport: TransportKind.stdio,
    options: { cwd: workspaceRoot() },
  };

  // `documentSelector` carries no `scheme`. Over a remote connection a
  // document's URI is `vscode-remote://…` and not `file://`, so pinning the
  // scheme to "file" is the classic way to make an extension that installs
  // correctly and then never attaches to anything.
  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ language: "zen" }],
    outputChannel: output,
    // The server neither watches files nor reads a configuration section,
    // so nothing is synchronised to it. Adding either would be advertising
    // a capability it does not have.
    errorHandler: {
      error: (error, _message, count) => {
        output.appendLine(`zen: transport error (${count}): ${error.message}`);
        return { action: ErrorAction.Shutdown };
      },
      closed: () => {
        // The server exited. Do not let vscode-languageclient restart it
        // four times and then declare it broken — say the observation once,
        // and name the cause that is overwhelmingly likely without claiming
        // to know it. Reload the window to try again.
        output.appendLine("zen: the server process exited.");
        output.appendLine(NO_TRANSPORT_YET);
        void vscode.window
          .showWarningMessage(
            "Zen: the language server exited. It will not be restarted automatically.",
            "Details",
          )
          .then((pick) => {
            if (pick === "Details") {
              output.show(true);
            }
          });
        return { action: CloseAction.DoNotRestart };
      },
    },
  };

  client = new LanguageClient("zen", "Zen Language Server", serverOptions, clientOptions);

  try {
    await client.start();
    output.appendLine("zen: server started. `hover` is the one query it answers;");
    output.appendLine(
      "zen: definition, completion, symbols, formatting and rename are refused by name with -32601.",
    );
  } catch (err) {
    output.appendLine(`zen: the server failed to start: ${String(err)}`);
    output.appendLine(NO_TRANSPORT_YET);
    output.show(true);
  }
}

export function deactivate(): Thenable<void> | undefined {
  return client?.stop();
}

// A relative `zen.server.path` — and the default `./zen` is one, because
// `make build` writes the binary to the root of the checkout — is resolved
// against the workspace folder. An absolute path is taken as written, and a
// bare name with no separator is left alone so it can be found on PATH.
function resolveServerPath(configured: string): string {
  const root = workspaceRoot();
  if (path.isAbsolute(configured)) return configured;
  if (!configured.includes(path.sep) && !configured.includes("/")) return configured;
  if (!root) return configured;
  return path.join(root, configured);
}

function workspaceRoot(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

// `vscode.workspace.fs`, not `node:fs`. On a remote connection this asks the
// extension host's own filesystem, which is the one the server has to be on.
async function exists(fsPath: string): Promise<boolean> {
  if (!fsPath.includes(path.sep) && !fsPath.includes("/")) {
    // A bare name is looked up on PATH by the spawn, and this extension has
    // no business guessing what is on the remote PATH.
    return true;
  }
  try {
    await vscode.workspace.fs.stat(vscode.Uri.file(fsPath));
    return true;
  } catch {
    return false;
  }
}
