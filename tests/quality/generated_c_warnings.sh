#!/usr/bin/env bash
set -euo pipefail

# This gate supports GCC and Clang warning classes with equivalent C99 intent.
# Explicit classes avoid compiler-specific warnings hidden inside -Wall/-Wextra.
readonly warning_flags=(
    -std=c99
    -Wpedantic
    -Wconversion
    -Wsign-conversion
    -Wsign-compare
    -Wunused-function
    -Wunused-label
    -Wunused-parameter
    -Wunused-variable
    -Wunused-but-set-variable
    -fdiagnostics-color=never
    -fsyntax-only
)
# Clang enables its parenthesized-equality diagnostic by default; GCC does not
# implement the option. Excluding it keeps both tools on the classes above.
readonly clang_warning_flags=(-Wno-parentheses-equality)

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd "$script_dir/../.." && pwd)"
readonly baseline_file="$script_dir/generated_c_warnings.baseline"
readonly fixture_dir="$script_dir/fixtures/generated_c"
readonly positive_control="$script_dir/fixtures/unused_variable.c"
readonly zen="${ZEN:-$repo_root/zen}"
readonly gcc_bin="${GCC:-gcc}"
readonly clang_bin="${CLANG:-clang}"
readonly work_dir="$(mktemp -d "${TMPDIR:-/tmp}/zen-generated-c-warnings.XXXXXX")"
trap 'rm -rf -- "$work_dir"' EXIT

fail() {
    printf 'generated-c-warnings: %s\n' "$*" >&2
    exit 1
}

for required in "$zen" "$gcc_bin" "$clang_bin"; do
    command -v "$required" >/dev/null 2>&1 || fail "required tool not found: $required"
done

mkdir -p "$work_dir/tree"
cp -R "$fixture_dir/." "$work_dir/tree/"
cp -R "$repo_root/src/std" "$work_dir/tree/std"
"$zen" build "$work_dir/tree" --emit-c -o "$work_dir/emitted.c"

baseline_for() {
    local compiler="$1"
    local artifact="$2"
    awk -v compiler="$compiler" -v artifact="$artifact" '
        $1 == compiler && $2 == artifact { print $3; found = 1 }
        END { if (!found) exit 1 }
    ' "$baseline_file"
}

check_positive_control() {
    local compiler="$1"
    local binary="$2"
    local log="$work_dir/$compiler-positive-control.log"

    local -a compiler_flags=()
    [[ "$compiler" == clang ]] && compiler_flags=("${clang_warning_flags[@]}")

    if LC_ALL=C "$binary" "${warning_flags[@]}" "${compiler_flags[@]}" \
        -Werror=unused-variable \
        "$positive_control" >"$log" 2>&1; then
        fail "$compiler did not reject the unused-variable positive control"
    fi
    grep -q -- 'unused-variable' "$log" || {
        sed -n '1,20p' "$log" >&2
        fail "$compiler failed the positive control without the expected diagnostic"
    }
}

check_artifact() {
    local compiler="$1"
    local artifact="$2"
    local log="$work_dir/$compiler-$artifact.log"
    local expected actual

    expected="$(baseline_for "$compiler" "$artifact")" || \
        fail "missing baseline for $compiler $artifact"
    actual="$(grep -c ': warning:' "$log" || true)"

    if [[ "$actual" -gt "$expected" ]]; then
        sed -n '1,40p' "$log" >&2
        fail "$compiler $artifact warnings increased: expected at most $expected, found $actual"
    fi
    if [[ "$actual" -lt "$expected" ]]; then
        fail "$compiler $artifact warnings fell from $expected to $actual; lower the baseline"
    fi
    printf 'generated-c-warnings: %s %s: %s warnings\n' \
        "$compiler" "$artifact" "$actual"
}

declare -a jobs=()
declare -a job_names=()
for compiler in gcc clang; do
    compiler_flags=()
    if [[ "$compiler" == gcc ]]; then
        binary="$gcc_bin"
    else
        binary="$clang_bin"
        compiler_flags=("${clang_warning_flags[@]}")
    fi
    check_positive_control "$compiler" "$binary"
    for artifact in seed emitted; do
        if [[ "$artifact" == seed ]]; then
            input="$repo_root/seed/zen.c"
        else
            input="$work_dir/emitted.c"
        fi
        LC_ALL=C "$binary" "${warning_flags[@]}" "${compiler_flags[@]}" "$input" \
            >"$work_dir/$compiler-$artifact.log" 2>&1 &
        jobs+=("$!")
        job_names+=("$compiler $artifact")
    done
done

for index in "${!jobs[@]}"; do
    wait "${jobs[$index]}" || fail "${job_names[$index]} did not compile cleanly"
done

check_artifact gcc seed
check_artifact clang seed
check_artifact gcc emitted
check_artifact clang emitted
