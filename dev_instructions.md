# Dev Instructions — Matt Pocock's AI Engineering Workflow

This project uses [Matt Pocock's skills](https://github.com/mattpocock/skills) for Claude Code.
The idea: stop "vibe coding" and put the AI inside real engineering constraints. You think and
decide; the agent builds in small, verifiable slices.

The flow is a pipeline:

```
grill-me  →  PRD  →  issues (kanban)  →  TDD  →  Ralph loop
 (decide)   (spec)   (slice the work)   (build)  (run unattended)
```

---

## 1. `/grill-me` — pin down the decisions

Before any code, get interviewed about the plan. The skill asks **one question at a time**,
walks every branch of the design tree, and won't let you hand-wave — for each question it gives
its recommended answer and explores the codebase instead of asking when it can.

**Use it for:** stress-testing an idea until every decision is explicit. Output is a shared
understanding, not code.

## 2. `/to-prd` — turn the conversation into a spec

Once the grilling settles the decisions, this synthesizes the conversation + codebase into a
**PRD** (Product Requirements Document) and publishes it to your issue tracker. It does **not**
re-interview you — it just writes down what you already decided.

> Run `/setup-matt-pocock-skills` once first, so it knows your issue tracker (GitHub / GitLab /
> local files) and triage labels.

## 3. `/to-issues` — slice the PRD into a kanban backlog

Breaks the PRD into **independently-grabbable issues** using **tracer-bullet vertical slices** —
each issue ships a thin end-to-end piece of value, *not* horizontal "frontend then backend"
layers. The result is your **kanban board**: a backlog of small tickets anyone (or the loop) can
pull one at a time.

## 4. `/tdd` — build each slice test-first

Implement issues with **red → green → refactor**:
1. **Red** — write a failing test that describes the behavior through the *public interface*.
2. **Green** — write the minimum code to pass.
3. **Refactor** — clean up with the test as a safety net.

Tests verify *what* the system does, not *how* — so they survive refactors. See the reference
notes in the `tdd` skill (`tests.md`, `mocking.md`, `refactoring.md`, etc.).

## 5. The Ralph loop — run it while you sleep

[Ralph](https://www.aihero.dev/getting-started-with-ralph) ("Ralph Wiggum") is a dead-simple
loop: call Claude Code repeatedly against the PRD + a progress file, doing **one task per
iteration**, until the work is done. This repo's `ralph.py` is a cross-platform (Linux/macOS/
Windows) port.

```bash
python ralph.py --once          # one supervised iteration (you watch)
python ralph.py 20              # up to 20 iterations; stops when the PRD is complete
```

**To run unattended ("go to sleep"),** the loop must be allowed to run Bash (tests, commits),
which the default edit-only permission does NOT auto-approve. Pick one:

```bash
python ralph.py 20 --sandbox    # safest: inside `docker sandbox` (needs Docker Desktop)
python ralph.py 20 --yolo       # no Docker: bypass ALL prompts on the real machine
python ralph.py 20 --allow "Bash(git commit:*)" "Bash(npm test:*)" "Bash(npx tsc:*)"
```

For unattended runs the script auto-creates a `ralph/run-<timestamp>` git branch first, so
`main` is never touched — review and merge the commits when you wake up, or delete the branch
if it went sideways. `--yolo` runs any shell command with no isolation, so prefer `--sandbox`
or `--allow` unless you trust the task.

---

## TL;DR

1. `/grill-me` — decide everything.
2. `/to-prd` — write the spec.
3. `/to-issues` — slice into a kanban backlog.
4. `/tdd` — build each slice red-green-refactor.
5. `python ralph.py 20 --yolo` (on a branch) — let it grind through the backlog.

The skill is to **front-load the thinking** so the agent's autonomous work is bounded by a clear
spec, small slices, and tests — not vibes.
