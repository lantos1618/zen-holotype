# Code generation backends

Zen currently implements the C backend. `std.build.Codegen` selects the
source generator; `std.build.Emission` describes delivery:

```zen
Codegen = | C
Emission = Check | Stdout | File(str) | Directory(str)
```

`BuildArgs.backend` and `Exe.backend` default to `Codegen.C`. Existing
`--emit-c` and `--emit-c-dir` flags retain their output behavior. Explicit
source-generator selection is also supported:

```sh
zen build src --backend c --entry main.zen -o main.c
mkdir -p build/c
zen build src --backend c --entry main.zen --emit-c-dir build/c
```

With no output path, `--backend c` selects source output on stdout. This is
part of the raw source compilation interface; executable names in project
commands remain a separate selection. Unknown or unavailable names, including
`js` and `asm`, produce an explicit error before compilation or output writes.
There is no fallback to C and no dynamic plugin loader.

Build files may select the implemented generator per executable:

```zen
Builder, BuildError, Codegen = std.build

build = (builder :: Builder) Res<(), BuildError> {
    builder.exe("app", {
        src: Path("src/main.zen"),
        deps: [],
        backend: Codegen.C,
    }).try();
    Ok(())
}
```

Project recipe dispatch also matches the selected backend explicitly. A future
generator must supply its build/link recipe rather than inheriting `.c` output
and `cc` invocation.

The build interpreter accepts the checked Codegen constant and local bindings
of it. An explicit expression outside the interpreter's supported subset is
refused; it does not become the default backend.

## Generator and driver boundary

`gen.Generation` receives the checked program, caller allocator, scratch-memory
capability, entry module, generator choice, output layout and runtime options.
It owns backend construction and lowering. `zen.zen_write.Publisher` owns stdout and
filesystem destinations.

Generation publishes `gen.Artifact` values through a synchronous callback.
An artifact contains a kind, name and borrowed bytes. The callback must consume
or copy those bytes before returning; retaining the record extends no lifetime.
Allocation failures remain typed. Backend diagnostics suppress publication;
publication failures are counted and reported by the driver.

The C adapter preserves single-file output and the split layout: lower once,
render the shared header, render used modules in stable order using a fresh
scratch arena per module, then render a requested symbol map only if all source
writes succeeded. Direct CBackend entry points remain available to compiler
internals and backend-specific tools.

A future backend belongs in its own generator module with an explicit dispatch
case and artifact rendering implementation. It must implement real behavior
before selection is advertised. C-only details such as declarators, the shared
header and the C runtime floor remain in the C adapter.

## Platform targets and remaining work

`std.build.Target` means OS, architecture and ABI. A project command's target
name means a selected executable. Neither is a synonym for a backend.

The current project driver still selects a Linux/x86_64/GNU host and invokes
`cc`; backend selection does not implement cross compilation. JavaScript and
native machine-code generation are not implemented.

A future native backend can share a typed lowered IR, but needs target-specific
instruction selection, layout, register allocation, calling conventions and
object/link handling. Current monomorphization, callback expansion and cleanup
lowering are intertwined with C emission. Extracting reusable lowering requires
behavioral comparisons against C. A generic assembly vocabulary alone does not
supply these semantics or a complete actor/allocator runtime.
