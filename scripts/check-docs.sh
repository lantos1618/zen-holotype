#!/bin/sh

# Keep the maintained documentation set deliberate and verify every local Markdown link.
# Historical plans and reports belong in Git history, not as unlabelled live documents.

expected='./README.md
./bootstrap/README.md
./docs/ARCHITECTURE.md
./docs/MEMORY_MODEL.md
./docs/SPEC.md
./docs/STATUS.md
./docs/memory-usage-map.md
./docs/metaprogramming-vision.md
./docs/name-interning-design.md
./docs/profiling.md
./editor/nvim/README.md
./editor/vscode/README.md
./examples/README.md
./scripts/alloc-fuzz/README.md'

actual=$(find . -name .git -prune -o -path './.claude' -prune -o -name '*.md' -type f -print | LC_ALL=C sort)

if [ "$actual" != "$expected" ]; then
    echo "documentation inventory changed; consolidate it or update scripts/check-docs.sh intentionally" >&2
    printf 'expected:\n%s\nactual:\n%s\n' "$expected" "$actual" >&2
    exit 1
fi

failed=0
for file in $actual; do
    # grep exit 1 = "no links in this file" (fine); anything else (2 = unreadable/permission) means
    # the link scan did not run, and `|| true` used to turn that into zero link checks and a pass.
    links=$(grep -Eo '\]\([^)]*\)' "$file") || {
        rc=$?
        [ "$rc" -eq 1 ] || { echo "$file: cannot scan for links (grep exit $rc)" >&2; exit 2; }
        links=''
    }
    old_ifs=$IFS
    IFS='
'
    for link in $links; do
        target=${link#']('}
        target=${target%')'}
        case "$target" in
            ''|'#'*|http://*|https://*|mailto:*) continue ;;
        esac
        target=${target%%#*}
        target=${target#'<'}
        target=${target%>}
        dir=${file%/*}
        if [ "$dir" = "$file" ]; then
            dir=.
        fi
        if [ ! -e "$dir/$target" ]; then
            echo "$file: missing local link target: $target" >&2
            failed=1
        fi
    done
    IFS=$old_ifs
done

exit "$failed"
