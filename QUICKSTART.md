# Zen in 5 minutes

Zen is a small, self-hosted systems language: explicit allocators, `.match`-only control flow,
monomorphized generics, traits with UFCS — compiled to C.

## Build the compiler

```sh
git clone <this repo> && cd zenc
make -f bootstrap/Makefile zenc     # cc compiles the committed C seed → ./zenc  (~1s)
./zenc --version
```

`zenc` finds the stdlib relative to its own location; if you move the binary, set `ZEN_ROOT=/path/to/zenc-checkout`.

## Hello, world

```sh
cat > hello.zen <<'EOF'
{ println, println_int } = std.text.fmt

main = () i32 {
    println("hello, zen")
    println_int(6 * 7)
    0                              // main's value is the exit code
}
EOF
./zenc run hello.zen
```

`zenc run` type-checks, compiles via cc, and runs. `zenc build hello.zen -o hello` makes a binary;
`zenc check` type-checks only.

## Multiple files

A bare module name imports a **sibling file**: `{ helper } = geometry` loads `geometry.zen` from the
importing program's own directory (dotted names stay reserved for `std.` / `compiler.`). Helpers can
import the stdlib and other siblings; cycles are fine.

```sh
cat > geometry.zen <<'EOF'
{ println_int } = std.text.fmt

area*  = (w: i32, h: i32) i32 { w * h }       // `*` exports the name
show*  = (n: i32) i64 { println_int(n) }
EOF

cat > main.zen <<'EOF'
{ area, show } = geometry

main = () i32 {
    show(area(6, 7))
    0
}
EOF
./zenc run main.zen           # prints 42
```

Importing a module that doesn't exist, a name the module doesn't define, or the same name from two
sibling files is a compile error (`zenc: main.zen: error: unknown module 'geometr' (no geometr.zen
next to main.zen)`), not a linker failure.

## The language on one page

```zen
// bindings & types: i32 i64 u8 f64 bool str. `:=` binds, `=` reassigns.
x := 41
x = x + 1

// floats are f64 (C double). A float literal is digits '.' digits (no exponent form — write
// 0.001). STRICT: no implicit int<->float mixing, even for literals — `1.5 + 1` and
// `x: f64 := 1` are type errors; cross explicitly with to_f64 / to_i64 / to_i32 (C truncation).
// f64 supports + - * / and comparisons; % / bitwise / shifts reject. Matching on a float
// literal works but is just an `==` chain — use with care. std.text.fmt prints them (%g-style:
// whole values drop the point, -3.0 prints "-3").
h := 1.5
area := h * h * 0.5                  // f64 * f64 — fine
n := to_i32(area * 100.0)            // explicit float -> int (truncates toward zero)

// control flow is .match — there is no if/while statement.
sign = (n: i32) str {
    (n < 0).match ({ true => "neg", false => (n == 0).match ({ true => "zero", false => "pos" }) })
}

// structs construct with parens; fields mutate directly.
Point*: { x: i32, y: i32 }            // `*` exports the name
p := Point(x: 3, y: 4)
p.x = 5

// enums carry payloads; match must be exhaustive (or end with `_`).
Shape*: Circle(i32) | Square(i32) | Dot
area = (s: Shape) i32 {
    s.match ({ .Circle(r) => 3 * r * r, .Square(w) => w * w, .Dot => 0 })
}

// generics monomorphize; UFCS makes x.f(a) = f(x, a).
id<T> = (v: T) T { v }
seven := 7.id()

// loops: slice .loop, @while, or recursion. The loop HANDLER `h` carries the
// controls: `h.break` stops the loop, `h.continue` skips to the next element.
sum = (xs: [i32]) i32 {
    acc := 0
    xs.loop((h, i, v) {
        (v < 0).match ({ true => { h.break }, false => { acc = acc + v } })
    })
    acc
}

// collections take an EXPLICIT allocator — nothing hides a malloc.
// m := Malloc(_: 0)
// v := m.addr().vec_of([1, 2, 3])      // Vec<i32> backed by m
// v2 := m.addr().vpush(v, 4)
```

## A real program

`examples/stats.zen` computes sum/max/even-count over a `Vec<i32>` with enum-dispatched queries:

```sh
./zenc run examples/stats.zen
```

Browse `examples/` for more, and `zen/std/` for the stdlib (fmt, vec, str, string, result, io,
rc, arena, coroutine, …). Errors print as `file: error: <message>`; line/column info is in progress.

## Run the test suite

```sh
python3 -m pytest tests/ -q          # the binary-only oracle (~650 cases)
make -f bootstrap/Makefile regen     # regenerate the C seed; must be byte-identical (self-host gate)
```
