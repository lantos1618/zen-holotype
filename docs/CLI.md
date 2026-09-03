# Declarative command lines

`std.cli.Command<T>` is the terminal-facing command builder. A command's
parameters and subcommands are the single source for parsing, validation,
diagnostics, and help text. The original `Options<T>` scanner remains available
for small and compatibility-sensitive callers.

```zen
app ::= command<Id>(a, "tool", "Build things");
app.set_version("1.0");
app.flag("--verbose", Id.Verbose, "Print more detail").try();
app.alias("--verbose", "-v").try();
app.option("--jobs", Id.Jobs, "N", ValueType.Usize, "Worker count").try();
app.default_value("--jobs", "2");

build ::= command<Id>(a, "build", "Build one input");
build.positional("input", Id.Input, "INPUT", ValueType.Text, "Input path").try();
build.required("input");
app.subcommand(build).try();

parsed = app.parse(argv, 1).try();
```

Parameters may be switches, typed value options, or typed positionals. Value
types are `Text`, `I32`, `I64`, `U16`, and `Usize`. Aliases, `--name=value`, an
attached short value such as `-Dname`, defaults, repeatable parameters,
conflicts, dependencies, required values, required subcommands, nested
subcommands, and `--` are supported. `trailing_args()` makes the words after
`--` an untouched tail whose first index is returned as `Matches.options_end`.

Constraints use explicit command-line presence. A default satisfies
`required`, but it does not trigger or satisfy `conflicts` and `requires`.
Matches retain their full command path; `count_in` and `last_in` disambiguate a
spelling reused by parent and child commands.

`declaration_error()` checks the grammar before use, and both `parse()` and
help generation invoke that check. It rejects duplicate names and aliases,
reserved built-ins, missing or self-referential constraint targets, ill-shaped
options, invalid defaults, ambiguous command/positional roots, and unreachable
positional layouts. Parse failures are structured `Diagnostic` values; use
`message(a)` for stable terminal text.

Options declared on a parent are not global: place them before its subcommand.
Short flag clustering such as `-abc`, automatic typo suggestions, shell
completion generation, and derive-style mapping directly into an application
record are not currently part of the surface.
