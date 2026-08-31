// editors/vscode/src/extension.ts
//
// Launch `zen lsp` and speak LSP to it.
//
// This file does one thing and refuses to do a second: it resolves the
// server command, starts a LanguageClient over its stdio, restarts it on
// demand, and — the part that earns its length — SAYS WHAT WENT WRONG WHEN
// THAT FAILS. The
// transport now exists, so the happy path is reachable; the failure path
// keeps its length because the most likely failure left is a `zen` binary
// older than the transport, which looks exactly like a crash from here.
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
let sourceEvents: vscode.FileSystemWatcher;
let restarts: Promise<void> = Promise.resolve();

// The one thing this extension knows how to explain. It is written once,
// here, because it is the answer to every startup failure this extension
// can currently produce and repeating it would let the copies drift.
const STARTUP_FAILED =
  "Things to rule out, in the order they are worth checking:\n" +
  "\n" +
  "  1. THE BINARY IS STALE. `zen lsp` speaks over a pipe only if it was\n" +
  "     built after the `Stdin` capability landed. An older `zen` prints a\n" +
  "     usage message and exits 2 — which looks exactly like a crash from\n" +
  "     here. Run `zen lsp` in a terminal: if it prints usage, rebuild.\n" +
  "     Note `make build` alone is not enough if the seed predates it.\n" +
  "\n" +
  "  2. THE PATH IS WRONG. `zen.server.path` defaults to `./zen`, resolved\n" +
  "     against the workspace folder, with a fallback to `zen` on PATH.\n" +
  "     A checkout that has never been built has no `zen` at all.\n" +
  "\n" +
  "  3. A GENUINE SERVER FAILURE, in which case the trace above is the\n" +
  "     evidence — set `zen.trace.server` to `verbose` and reload.\n" +
  "\n" +
  "Worth knowing before you file anything: this server answers hover,\n" +
  "definition, completion, document symbols, semantic tokens and\n" +
  "formatting, publishes diagnostics, and refuses everything else with\n" +
  "`-32601`.\n" +
  "\n" +
  "Colour comes from `textDocument/semanticTokens`, which is why this\n" +
  "extension ships no TextMate grammar — see editors/README.md for that\n" +
  "argument. It is the one answer that needs no build and no workspace,\n" +
  "so if hover and diagnostics are quiet, colour should still work.\n" +
  "\n" +
  "Diagnostics are lex's, parse's and sema's, grouped per file — an error\n" +
  "in a module you are not looking at is reported against that module —\n" +
  "and a file you have fixed is cleared rather than left underlined. They\n" +
  "need a workspace folder: with no `rootUri` the server publishes nothing\n" +
  "at all, on purpose, because the only thing it could check without a\n" +
  "root is the open file alone, and that calls every imported name\n" +
  "undefined. A build runs per change, so squiggles lag your typing in a\n" +
  "large module — about a second — and are instant in a small one.\n" +
  "\n" +
  "Hover answers on an identifier's use, on a parameter or local at its\n" +
  "declaration, on a written type name, and on a function's name — where\n" +
  "it hands the declaration back. With a workspace it answers imported\n" +
  "names too. It answers nothing on a struct's own name, a pattern binder,\n" +
  "or anything whose type did not resolve.";

export async function activate(context: vscode.ExtensionContext) {
  output = vscode.window.createOutputChannel("Zen");
  context.subscriptions.push(output);
  sourceEvents = vscode.workspace.createFileSystemWatcher("**/*.zen");
  context.subscriptions.push(sourceEvents);

  context.subscriptions.push(
    vscode.commands.registerCommand("zen.restartServer", () =>
      restartServer("restart requested"),
    ),
    vscode.workspace.onDidChangeConfiguration((change) => {
      if (
        change.affectsConfiguration("zen.server.path") ||
        change.affectsConfiguration("zen.server.args")
      ) {
        void restartServer("server configuration changed");
      }
    }),
  );

  await startClient();
}

// The server's `closed` handler returns `DoNotRestart` — crashing in a loop
// is worse than lying still — so a dead server used to mean a window reload.
// This command is the reload without the window: stop what is left, then go
// through the whole lookup again, because the two reasons to reach for it
// are "I rebuilt the binary" and "I changed the setting".
function restartServer(reason: string): Promise<void> {
  const next = restarts.then(async () => {
    output.appendLine(`zen: ${reason}.`);
    await stopClient();
    await startClient();
  });
  // Keep one failed launch from poisoning every later restart while still
  // returning that failure to the command which requested it.
  restarts = next.catch((err) => {
    output.appendLine(`zen: restart failed: ${String(err)}`);
  });
  return next;
}

async function stopClient(): Promise<void> {
  const stopping = client;
  client = undefined;
  if (!stopping) return;
  try {
    await stopping.stop();
  } catch (err) {
    // Stopping a client whose server already exited throws from here. The
    // exit was reported when it happened; the restart goes ahead anyway.
    output.appendLine(`zen: stopping the old client failed: ${String(err)}`);
  }
}

async function startClient(): Promise<void> {
  const config = vscode.workspace.getConfiguration("zen");
  const configured = config.get<string>("server.path", "./zen");
  const args = config.get<string[]>("server.args", ["lsp"]);

  const command = await resolveServerCommand(configured, isSet(config, "server.path"));
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

  const serverEnv = { ...process.env };
  const stdRoot = await standardLibraryRoot(command);
  if (stdRoot) {
    serverEnv.ZEN_STD = stdRoot;
    output.appendLine(`zen: standard library root: ${stdRoot}`);
  }

  const serverOptions: ServerOptions = {
    command,
    args,
    transport: TransportKind.stdio,
    options: { cwd: workspaceRoot(), env: serverEnv },
  };

  // `documentSelector` carries no `scheme`. Over a remote connection a
  // document's URI is `vscode-remote://…` and not `file://`, so pinning the
  // scheme to "file" is the classic way to make an extension that installs
  // correctly and then never attaches to anything.
  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ language: "zen" }],
    outputChannel: output,
    // Builds read imported modules from disk as well as open overlays. Tell
    // the server when one of those disk inputs changes so it can retire a
    // cached whole-program build instead of keeping stale exports/types.
    synchronize: { fileEvents: sourceEvents },
    errorHandler: {
      error: (error, _message, count) => {
        output.appendLine(`zen: transport error (${count}): ${error.message}`);
        return { action: ErrorAction.Shutdown };
      },
      closed: () => {
        // The server exited. Do not let vscode-languageclient restart it
        // four times and then declare it broken — say the observation once,
        // and name the cause that is overwhelmingly likely without claiming
        // to know it. `zen.restartServer` is the way to try again.
        output.appendLine("zen: the server process exited.");
        output.appendLine(STARTUP_FAILED);
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
    output.appendLine(
      "zen: server started. It answers `hover` — a type, or a function's signature —",
    );
    output.appendLine(
      "zen: `semanticTokens`, which is where colour comes from, definition, completion,",
    );
    output.appendLine(
      "zen: document symbols, and `formatting`; references and rename are refused by",
    );
    output.appendLine(
      "zen: name with -32601.",
    );
    output.appendLine(
      "zen: Formatting is `zen fmt` itself, so `editor.formatOnSave` formats a .zen",
    );
    output.appendLine(
      "zen: buffer exactly as the command line would. A buffer that does not parse is",
    );
    output.appendLine(
      "zen: left alone silently — no edit, and deliberately no error to dismiss.",
    );
    warnIfSemanticHighlightingOff();
  } catch (err) {
    output.appendLine(`zen: the server failed to start: ${String(err)}`);
    output.appendLine(STARTUP_FAILED);
    output.show(true);
  }
}

export function deactivate(): Thenable<void> | undefined {
  return client?.stop();
}

// NO CLIENT CODE REGISTERS SEMANTIC TOKENS, and that is not an omission.
// `vscode-languageclient` registers `SemanticTokensFeature` as one of its
// default features, sends the client half of the capability itself, and —
// on seeing `semanticTokensProvider` come back from `initialize` — calls
// `vscode.languages.registerDocumentSemanticTokensProvider` with the
// server's own legend. It asks for `full/delta` only when the server said
// `full: {delta: true}` and for `range` only when it said `range: true`,
// so advertising a bare `full: true` is what keeps it to the one request
// this server answers.
//
// NOR DOES ANY CLIENT CODE REGISTER THE FORMATTER, for the same reason.
// `registerBuiltinFeatures()` installs `DocumentFormattingFeature`, which
// sends `textDocument.formatting` in the client capabilities and, on
// seeing `documentFormattingProvider` come back from `initialize`, calls
// `vscode.languages.registerDocumentFormattingEditProvider` with this
// extension's own `documentSelector`. A bare `true` from the server is
// enough; VS Code stamps the provider with this extension's identity
// because the call is made from this extension host, so no manifest
// contribution is involved and `contributes.formatters` does not exist.
//
// `contributes.configurationDefaults` sets `editor.defaultFormatter` for
// `[zen]` anyway, and it is polish rather than plumbing. VS Code
// short-circuits when exactly one formatter is registered for a
// document, so the setting is dead weight until a second one competes —
// at which point the alternative is a user whose global default is
// Prettier being told, on every save, that Prettier cannot format .zen.
//
// WHAT CAN STILL LEAVE THE FILE GREY, silently, with a server answering
// perfectly. VS Code applies semantic tokens only when semantic
// highlighting is on: `editor.semanticHighlighting.enabled` defaults to
// `configuredByTheme`, every stock theme turns it on, and a user who has
// set it to `false` — or a theme that leaves it off — gets a correct
// token list that colours nothing, with nothing on screen to say why.
// That is the same shape of failure as the server exiting 2 on `--stdio`:
// invisible from the editor, obvious once named. So it is named, once, in
// the channel where every other startup fact is.
function warnIfSemanticHighlightingOff(): void {
  const setting = vscode.workspace
    .getConfiguration("editor")
    .get<boolean | string>("semanticHighlighting.enabled");
  if (setting === false) {
    output.appendLine(
      "zen: `editor.semanticHighlighting.enabled` is false, so VS Code will discard the",
    );
    output.appendLine(
      "zen: colours this server sends. Set it to true, or to `configuredByTheme`.",
    );
    return;
  }
  if (setting === "configuredByTheme" || setting === undefined) {
    output.appendLine(
      "zen: colour is semantic tokens, which your theme must enable — stock themes do.",
    );
    output.appendLine(
      "zen: If .zen files stay grey, set `editor.semanticHighlighting.enabled` to true.",
    );
  }
}

// The configured path first. If it misses and it was the DEFAULT, `zen` is
// looked up on the extension host's PATH before anyone is told to go and
// build something — a remote host that has zen installed properly should
// not need a setting at all. An EXPLICIT path that misses is reported as
// written instead: silently starting a different binary than the one asked
// for is how "why is it running the old compiler" afternoons begin.
async function resolveServerCommand(configured: string, explicit: boolean): Promise<string> {
  const resolved = resolveServerPath(configured);
  if (await exists(resolved)) return resolved;
  if (explicit) return resolved;
  const onPath = await findOnPath("zen");
  if (onPath) {
    output.appendLine(`zen: ${resolved} is not there; using ${onPath} from PATH.`);
    return onPath;
  }
  return resolved;
}

// Explicit means the value came from settings, not from the default. A user
// who never touched `zen.server.path` gets the fallback; a user who wrote
// one meant that one.
function isSet(config: vscode.WorkspaceConfiguration, key: string): boolean {
  const inspected = config.inspect(key);
  return (
    inspected?.globalValue !== undefined ||
    inspected?.workspaceValue !== undefined ||
    inspected?.workspaceFolderValue !== undefined
  );
}

// A `which` over the extension host's PATH — which, like everything else
// here, is the REMOTE one — asking `vscode.workspace.fs` and never
// `node:fs`, for the reason at the top of this file. Existence is the whole
// test; a PATH entry that holds a non-executable `zen` fails loudly at
// spawn, which is a better report than a guess from here.
async function findOnPath(name: string): Promise<string | undefined> {
  const pathEnv = process.env.PATH;
  if (!pathEnv) return undefined;
  const candidates = process.platform === "win32" ? [name + ".exe", name] : [name];
  for (const dir of pathEnv.split(path.delimiter)) {
    if (!dir) continue;
    for (const candidate of candidates) {
      const full = path.join(dir, candidate);
      try {
        const stat = await vscode.workspace.fs.stat(vscode.Uri.file(full));
        if (stat.type === vscode.FileType.File) return full;
      } catch {
        // Not in this entry; try the next.
      }
    }
  }
  return undefined;
}

// Integrated-terminal environment settings do not reach the extension host.
// Preserve a real process-level override; otherwise a compiler checkout has a
// self-describing layout, and its std marker is stronger evidence than a
// workspace-relative guess. The compiler has the same fallback so non-VS Code
// clients behave identically; doing it here also makes the selected root
// visible in the Zen output channel.
async function standardLibraryRoot(command: string): Promise<string | undefined> {
  const inherited = process.env.ZEN_STD;
  if (inherited) return inherited;

  const executable =
    command.includes(path.sep) || command.includes("/")
      ? command
      : await findOnPath(command);
  if (!executable) return undefined;

  const root = path.join(path.dirname(executable), "src");
  const marker = path.join(root, "std", "std.zen");
  return (await exists(marker)) ? root : undefined;
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
