# Docker Agent coding team

A coordinator and four specialists (architecture, security, testing, product/UX)
share `stealth/space-bunny-alpha` through OpenRouter. The coordinator can start
specialists concurrently with `background_agents`. Substantial reviews request
parallel work; simple questions do not need all five agents.

## Start on macOS

Install Docker Agent using [the official installation options](https://github.com/docker/docker-agent#install):

```sh
brew install docker-agent
```

In your Mac's default zsh terminal, enter your OpenRouter key without displaying
it or putting the value in shell history:

```zsh
read -rs 'OPENROUTER_API_KEY?OpenRouter API key: '
printf '\n'
export OPENROUTER_API_KEY
```

From your clone of this repository:

```sh
git pull --ff-only
./scripts/docker-agent.sh
```

The launcher uses the current directory as the project. To build something in a
new directory using the same team, use the launcher's absolute path:

```sh
mkdir -p ~/projects/my-app
cd ~/projects/my-app
/path/to/zen-holotype/scripts/docker-agent.sh
```

Try: “Build [your idea]. Delegate independent work to specialists in parallel,
assign separate files, then integrate and test the result.”

For a review: “Review this repository using all four specialists in parallel.
Read the files directly and report findings with file references.”

Approve agent-start or other tool prompts when shown. The coordinator waits for
results and reports which specialists actually ran. Restart existing sessions
to load configuration changes. More simultaneous agents use more requests and
may hit provider rate limits.

## Configuration and credentials

- `team.yaml` contains the model, roles, tools, and delegation instructions.
- The key comes only from `OPENROUTER_API_KEY`; no credentials are stored here.
- The built-in `openrouter` provider supplies the API endpoint.
- The launcher accepts Docker Agent run flags, such as `--dry-run` or
  `--working-dir /path/to/project`.
- Balanced safety mode asks about calls it cannot classify as safe. It does not
  automatically approve every command.

Validated with Docker Agent v1.144.0 on Linux, including two concurrent specialist
file reads. The launcher supports both the standalone `docker-agent` command
(Homebrew) and the `docker agent` CLI plugin. macOS execution still needs to be
checked on a Mac.
