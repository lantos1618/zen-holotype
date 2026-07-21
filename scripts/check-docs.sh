#!/bin/sh

# Keep the maintained documentation set deliberate and verify every local Markdown link.
# Historical plans and reports belong in Git history, not as unlabelled live documents.

expected='./ARCHITECTURE.md
./MEMORY_MODEL.md
./README.md
./SPEC.md
./STATUS.md
./bootstrap/README.md
./examples/README.md'

# Inventory TRACKED docs only: a dirty working tree (gitignored build/zen-context.md,
# .pytest_cache/, worktrees) must not trip the gate locally — CI's clean checkout never sees
# those files, and they are not maintained documentation. Fall back to plain find outside a repo.
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    actual=$(git ls-files -- '*.md' | sed 's|^|./|' | LC_ALL=C sort)
else
    actual=$(find . -name .git -prune -o -name '*.md' -type f -print | LC_ALL=C sort)
fi

if [ "$actual" != "$expected" ]; then
    echo "documentation inventory changed; consolidate it or update scripts/check-docs.sh intentionally" >&2
    printf 'expected:\n%s\nactual:\n%s\n' "$expected" "$actual" >&2
    exit 1
fi

failed=0
for file in $actual; do
    links=$(grep -Eo '\]\([^)]*\)' "$file" 2>/dev/null || true)
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
