# duo

Duo is a two-agent Codex loop for a coding task. One agent implements; the
other privately tries to break the result. Duo stops when the verifier has
evidence that the task is complete, or when it reaches the iteration limit.

## How it works

1. The verifier reads the task and repository, then forms a private view of the
   required final state and likely failure cases.
2. The developer receives the task and edits the project.
3. The verifier inspects the actual result, runs tests or disposable probes,
   and returns structured output: `{"passed": boolean, "feedback": string}`.
4. On rejection, only the feedback goes to the developer. The loop repeats.

The two Codex threads do not know about each other. The verifier never edits
project files; it may use `/tmp` for scratch probes. It must keep checking the
whole task, not stop after finding one bug.

## Requirements

- Python 3.13+
- Codex authentication, normally `~/.codex/auth.json`
- A project directory for `--workdir`

The current runner uses Codex auto-approval and full filesystem access. Run it
only in a workspace you are comfortable letting the developer modify.

## Install

```sh
uv tool install git+https://github.com/ExpressGradient/duo.git
```

For development from a local checkout, use `uv run duo ...` instead.

## Run

```sh
# Give the task directly.
duo "add pagination" -C /path/to/project

# Put a long task in a file.
duo -f task.md -C /path/to/project --max-iterations 6

# Choose different developer and verifier models or reasoning effort.
duo -f task.md -C /path/to/project \
  --developer-model gpt-5.6-terra --developer-effort xhigh \
  --verifier-model gpt-5.6-sol --verifier-effort max
```

## Options

| Option | Meaning |
|---|---|
| `prompt` or `-f, --prompt-file` | The task. Choose one. |
| `-C, --workdir` | Project the developer edits and verifier reviews. |
| `-n, --max-iterations` | Maximum developer → verifier cycles. Default: 3. |
| `--developer-model`, `--developer-effort` | Developer Codex configuration. |
| `--verifier-model`, `--verifier-effort` | Verifier Codex configuration. |

Run `duo --help` for the current defaults.

## Output and exit status

Duo writes the verifier's initial assessment, each developer response, and
every raw JSON verdict to stdout. Capture it with `tee` if you want a file
outside an evaluation harness.

| Exit | Meaning |
|---:|---|
| `0` | The verifier returned `passed: true`. |
| `1` | The iteration limit was reached. |
| Other non-zero | Duo or Codex failed before a verdict. |

For DeepSWE, the Pier adapter lives in
`ants-deepswe-bench/duo_agent.py`. It uploads the wheel from `dist/` into each
task and saves this output as `agent/duo.txt`.
