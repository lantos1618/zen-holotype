#!/bin/sh
# Run the shared team against the caller's current project directory.
set -eu

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
config="$script_dir/../tools/docker-agent/team.yaml"

if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    printf '%s\n' 'Set OPENROUTER_API_KEY before starting. See tools/docker-agent/README.md.' >&2
    exit 1
fi

if command -v docker-agent >/dev/null 2>&1; then
    exec docker-agent run "$config" --safety balanced "$@"
elif command -v docker >/dev/null 2>&1 && docker agent version >/dev/null 2>&1; then
    exec docker agent run "$config" --safety balanced "$@"
fi

printf '%s\n' 'Docker Agent is missing. On macOS: brew install docker-agent' >&2
exit 1
