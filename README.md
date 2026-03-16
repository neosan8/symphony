# Symphony

`symphony.py` is a Python daemon that polls the Paperclip issues API every 30 seconds, finds issues
whose state is `todo`, and launches up to 5 concurrent `codex exec` workers.

`symphony_v2.py` is the preferred dual-source daemon. It keeps the worker dispatch model, adds
Linear support, and now sends real wake notifications to the OpenClaw gateway for terminal worker
outcomes.

## Behavior

- Polls a configured Paperclip issues API endpoint (for example `http://127.0.0.1:3100/api/companies/<company-id>/issues`)
- Filters issues whose normalized state is exactly `todo`
- Creates a workspace per issue at `/tmp/symphony/<issue-id>/`
- Writes raw issue payloads to `/tmp/symphony/<issue-id>/issue.json`
- Starts `codex exec` in that workspace
- Logs daemon events to stdout and `/tmp/symphony/symphony.log`
- Logs each worker's stdout/stderr to per-issue `stdout.log` and `stderr.log`
- Stops active workers if an issue is no longer `todo`
- Handles `SIGINT` and `SIGTERM` for graceful shutdown

## Symphony V2 Notifications

- `symphony_v2.py` sends a `symphony.task.wake` POST to the configured OpenClaw gateway URL when a
  worker finishes successfully (`outcome=completed`) or exits non-zero (`outcome=failed`).
- Configure the gateway with `--wake-event-url` or `OPENCLAW_GATEWAY_WAKE_URL`.
- A fallback check runs every 120 seconds by default (`--fallback-poll-interval 120`) and scans
  active runs for finished or stalled workers.
- If the fallback sweep sees a worker with no new output for the full cadence window, it emits a
  one-shot `outcome=stalled` wake event so the task can be investigated instead of silently hanging.
- Completion still updates the issue state to `done` and adds the normal completion comment before
  the wake event is delivered.

## Milestone 11: Auditable Task Closure

Milestone 11 adds a file-backed closure flow for agent work. The goal is simple:

**An agent saying "done" is not proof.**

Symphony v2 now persists explicit execution and review artifacts so an operator can inspect a constrained decision package instead of trusting chat-only state.

What this adds:

- explicit execution artifact metadata:
  - `summary_path`
  - `verification_path`
  - `review_path`
- Human Gate decision package artifacts:
  - `human_gate_package.json`
  - `human_gate_package.md`
- package inspection CLI:
  - `python3 symphony_v2.py human-gate show-package --run <run>`
- guarded merge-preparation CLI:
  - `python3 symphony_v2.py pr-opened prepare-merge --run <run>`

### Why this exists

This flow is meant to keep task closure auditable and explicit:

- execution evidence is persisted to run artifacts
- Human Gate reviews a compact package instead of raw worker output
- merge preparation is gated on review state, acknowledgement state, and artifact consistency
- the source of truth is persisted run state, not hidden chat context

### CLI examples

```bash
python3 symphony_v2.py human-gate show-package --run <run>
python3 symphony_v2.py pr-opened prepare-merge --run <run>
```

### Non-goals

Milestone 11 does **not** add:

- auto-merge
- autonomous review resolution
- direct-to-main shipping
- hidden chat-state as a source of truth

## Repo Map Config

Task 3 expects a repo map JSON contract. The live runtime config is intentionally machine-local and is not tracked in this repository.

For reproducibility, this repository tracks the contract shape at:

- `config/repos.example.json`

Copy the example to your own local runtime config path and replace `repo_path` with your real checkout path.

## Requirements

- Python 3.10+
- `requests`
- `codex` available on `PATH`

Install `requests` if needed:

```bash
python3 -m pip install requests
```

## Run

```bash
python3 symphony.py
```

```bash
python3 symphony_v2.py \
  --source both \
  --wake-event-url http://127.0.0.1:8080/wake \
  --fallback-poll-interval 120
```

Useful overrides:

```bash
python3 symphony.py \
  --poll-interval 30 \
  --concurrency 5 \
  --workspace-root /tmp/symphony \
  --log-path /tmp/symphony/symphony.log \
  --codex-bin codex
```

## Notes

- The daemon uses only the Python standard library plus `requests`.
- If the Paperclip API payload shape changes, `symphony.py` attempts to normalize common issue list
  layouts such as top-level arrays and objects with `issues`, `data`, `results`, or `items`.
- The state parser accepts `state` or `status`, including nested objects like
  `{"state": {"name": "todo"}}`.
