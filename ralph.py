#!/usr/bin/env python3
"""
ralph.py - Cross-platform Ralph loop for Claude Code, wired to a GitHub-issues kanban.

A Python port of Matt Pocock's "Ralph Wiggum" loops
(https://www.aihero.dev/getting-started-with-ralph). Runs identically on
Linux, macOS, and Windows.

Two modes:

* ISSUE MODE (default) - the GitHub issue tracker is the single source of
  truth. Each iteration, Claude grabs the next UNBLOCKED open issue carrying
  the trigger label (default ``ready-for-agent``), implements it end-to-end,
  runs tests, commits, then comments on and CLOSES the issue. The loop ends
  when no labelled open issues remain (Claude emits <promise>COMPLETE</promise>).
  This is what `/to-prd` -> `/to-issues` feed into.

* FILE MODE (--from-file) - the original behaviour: Claude works a local PRD
  checklist file + progress file, ONE task per iteration.

Usage:
    python ralph.py --once                 # one supervised iteration (issue mode)
    python ralph.py 20                      # up to 20 autonomous iterations
    python ralph.py 20 --sandbox           # ... inside `docker sandbox`
    python ralph.py 20 --yolo              # ... no Docker, bypass ALL prompts
    python ralph.py 20 --allow "Bash(gh:*)" "Bash(git commit:*)" "Bash(npm test:*)"
    python ralph.py 20 --label ready-for-agent --repo zmomz/jast
    python ralph.py 20 --from-file --prd REMEDIATION_PRD.md   # legacy file mode

Unattended runs (going to sleep) need prompts bypassed, since the Ralph prompt
runs Bash (gh, tests, git commit) which `--permission-mode acceptEdits` does
NOT auto-approve. Choose ONE of:
    --sandbox   run inside `docker sandbox` (needs Docker Desktop) - safest
    --yolo      --dangerously-skip-permissions on your real machine - riskiest
    --allow ... scoped allowlist; only the listed commands auto-run. In issue
                mode you MUST include the gh + git + test commands, e.g.
                --allow "Bash(gh:*)" "Bash(git:*)" "Bash(npm test:*)" "Bash(npx tsc:*)"
Without one of these, an autonomous loop will stall on the first Bash prompt.

For unattended modes the script first creates a `ralph/run-<timestamp>` git
branch so your main branch is never touched (disable with --no-branch).

Requirements:
    - Python 3.8+
    - The `claude` CLI on PATH (https://docs.claude.com/claude-code)
    - The `gh` CLI installed + authenticated (issue mode). It need not be on
      PATH globally; this script locates a Windows install and injects it.
    - Docker Desktop, only if you pass --sandbox
    - git, for branch safety / per-iteration commits
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# On Windows the console streams default to the locale codec (cp1252) and blow
# up echoing Claude's UTF-8 output. Re-pin our own stdout/stderr to UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass  # not a reconfigurable stream (e.g. redirected to a non-TTY pipe)

COMPLETE_SENTINEL = "<promise>COMPLETE</promise>"

PRD_STUB = """# PRD

Describe the product / feature you want built. Break it into a checklist of
small, independently-shippable tasks. Ralph implements ONE per iteration.

## Tasks
- [ ] First task
- [ ] Second task
"""

# ---------------------------------------------------------------------------
# ISSUE MODE prompts - the GitHub kanban is the source of truth.
# ---------------------------------------------------------------------------
PROMPT_ISSUES_ONCE = (
    "You are working a GitHub-issues kanban for THIS repo (gh infers the repo "
    "from the git remote{repo_note}). The issue tracker is the single source of truth. "
    "Use the `gh` CLI for all tracker operations. "
    # (6) Cross-iteration memory: each iteration starts with a FRESH context, so the
    #     git log is your record of what previous iterations already did.
    "0. CONTEXT: review the last few commits before doing anything "
    "(`git log -n 10 --stat`). The commit history is your memory of prior iterations. "
    "1. List open issues labelled '{label}': "
    "`gh issue list --label {label} --state open --json number,title,body,labels`. "
    # (2) AFK-only: the trigger label IS the AFK marker; never touch human-in-the-loop work.
    "These carry the AFK (agent-runnable) label. Do NOT work on HITL issues: SKIP any "
    "issue that also carries a 'ready-for-human'/HITL label or whose body marks itself "
    "as needing human interaction (an architectural decision or design review). "
    "2. Discard BLOCKED and non-implementable issues: an issue is blocked if its body's "
    "'Blocked by' section references another issue that is still OPEN. SKIP any "
    "issue that is itself a PRD/epic rather than an implementable slice (its body "
    "contains a '## User Stories' or '## Implementation Decisions' heading, or it "
    "is referenced as a 'Parent' by other issues). "
    # (3) Priority ladder (from Matt Pocock's ralph/prompt.md), not just lowest-number.
    "3. From what remains, pick ONE issue in this PRIORITY order: (a) critical "
    "bugfixes; (b) development infrastructure — tests, type-checking, dev scripts "
    "(a precursor to building features); (c) tracer bullets for new features (build a "
    "tiny end-to-end slice through all layers first, then expand); (d) polish and "
    "quick wins; (e) refactors. Break ties by lowest issue number. BEFORE starting a "
    "new slice on an epic, FIRST check whether that epic's written Acceptance criteria "
    "are ALREADY satisfied by prior iterations (read its '## Acceptance' section against "
    "the recent git log); if they are, prefer to VERIFY and CLOSE it (step 8) rather than "
    "mine another slice — finishing an acceptance-met issue outranks starting new breadth. "
    "If there are NO "
    "eligible open '{label}' slices, print " + COMPLETE_SENTINEL + " and stop. "
    "4. Read that ONE issue in full (`gh issue view <n>`) and explore the repo. "
    # (1) Explicitly invoke the /tdd skill, with the anti-horizontal-slicing rule inline.
    "5. IMPLEMENT it using the `/tdd` skill (red -> green -> refactor): treat each "
    "acceptance criterion as a behavior; for EACH behavior write ONE failing test "
    "through the public interface (RED), then the minimal code to pass it (GREEN), "
    "then refactor. Do NOT write all tests up front (no horizontal slicing). Follow "
    "the repo's conventions and domain vocabulary. "
    "6. FEEDBACK LOOPS: run the project's tests and type checks; make them pass "
    "before committing. "
    # (4) Structured commit = the handoff the next fresh-context iteration reads.
    "7. COMMIT with a message that references the issue (e.g. '... (#<n>)') and "
    "records, for the next iteration: the key decisions made, the files changed, and "
    "any blockers or notes. "
    # (5) Partial-progress path: don't close an unfinished issue; leave a resume note.
    "8. THE ISSUE: if its written Acceptance criteria are ALL satisfied, comment a short "
    "summary and CLOSE it — bias toward closing: do NOT keep an issue open for imaginable "
    "polish or scope beyond what its '## Acceptance' lists; file genuinely-additional scope "
    "as a NEW ready-for-agent issue instead. To close, use "
    "(`gh issue close <n> --comment \"...\"`). If you could NOT finish it this "
    "iteration, do NOT close it — comment what was done, what remains, and any "
    "blockers, and leave it OPEN so the next iteration resumes it. "
    # (7) HEADLESS contract: -p print-mode has no next turn and no background-task
    #     notification will ever reach you, so any 'I'll wait for the monitor' yield
    #     silently abandons the iteration (edits uncommitted, issue left open).
    "9. HEADLESS EXECUTION: you are running non-interactively with NO next turn and NO "
    "background-task notifications. Do EVERYTHING synchronously within THIS single "
    "response: run tests in the FOREGROUND and wait for them inline (you MAY scope to "
    "the relevant test subset for speed, but never start a background job or say you "
    "will wait for a notification). Finish implementation, get tests to green, COMMIT, "
    "and comment/close the issue all before you stop responding. "
    "ONLY WORK ON A SINGLE ISSUE THIS ITERATION."
)

PROMPT_ISSUES_LOOP = PROMPT_ISSUES_ONCE  # identical contract; loop re-invokes per issue

# ---------------------------------------------------------------------------
# FILE MODE prompts (legacy --from-file) - a local PRD checklist + progress file.
# ---------------------------------------------------------------------------
PROMPT_FILE_ONCE = (
    "@{prd} @{progress} "
    "1. Read the PRD and progress file. "
    "2. Find the next incomplete task and implement it. "
    "3. Commit your changes. "
    "4. Update {progress} with what you did. "
    "ONLY DO ONE TASK AT A TIME."
)

PROMPT_FILE_LOOP = (
    "@{prd} @{progress} "
    "1. Find the highest-priority task and implement it. "
    "2. Run your tests and type checks. "
    "3. Update the PRD with what was done. "
    "4. Append your progress to {progress}. "
    "5. Commit your changes. "
    "ONLY WORK ON A SINGLE TASK. "
    "If the PRD is complete, output " + COMPLETE_SENTINEL + "."
)


def resolve(cmd: str) -> str:
    """Find an executable on PATH (handles claude.cmd / docker.exe on Windows)."""
    path = shutil.which(cmd)
    if not path:
        sys.exit(
            f"error: '{cmd}' not found on PATH. "
            f"Install it or check your PATH before running ralph.py."
        )
    return path


def find_gh_dir() -> str | None:
    """Locate the gh CLI directory even if it isn't on the global PATH.

    On Windows gh installs to 'C:\\Program Files\\GitHub CLI\\gh.exe' but is
    often absent from the shell PATH that Claude's Bash tool inherits, so we
    find it and inject its directory into the child environment.
    """
    found = shutil.which("gh")
    if found:
        return str(Path(found).parent)
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "GitHub CLI" / "gh.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "GitHub CLI" / "gh.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "GitHub CLI" / "gh.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c.parent)
    return None


def child_env(issue_mode: bool) -> dict:
    """Environment for the Claude subprocess, with gh injected onto PATH in issue mode."""
    env = os.environ.copy()
    if issue_mode:
        gh_dir = find_gh_dir()
        if gh_dir and gh_dir not in env.get("PATH", ""):
            env["PATH"] = gh_dir + os.pathsep + env.get("PATH", "")
        elif not gh_dir:
            print(
                "warning: gh CLI not found. Issue mode needs an authenticated gh "
                "('gh auth status'). Install it or run with --from-file.",
                file=sys.stderr,
            )
    return env


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command, capturing output."""
    return subprocess.run(
        [resolve("git"), *args], text=True, capture_output=True, check=check
    )


def in_git_repo() -> bool:
    try:
        r = git("rev-parse", "--is-inside-work-tree", check=False)
        return r.returncode == 0 and r.stdout.strip() == "true"
    except SystemExit:
        return False  # git not on PATH


def current_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip()


def make_ralph_branch() -> None:
    """Create and switch to a fresh ralph/run-<timestamp> branch."""
    if not in_git_repo():
        print("warning: not a git repo - skipping branch safety. "
              "Ralph's commit/reset safety net won't exist.")
        return
    name = "ralph/run-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    r = git("switch", "-c", name, check=False)
    if r.returncode != 0:  # older git without `switch`
        r = git("checkout", "-b", name, check=False)
    if r.returncode != 0:
        sys.exit(f"error: could not create branch {name}:\n{r.stderr.strip()}")
    print(f"ralph: working on branch '{name}' (was on '{current_branch()}' parent)")


def ensure_files(prd: Path, progress: Path) -> None:
    if not prd.exists():
        prd.write_text(PRD_STUB, encoding="utf-8")
        print(f"created {prd.name} (stub) - fill it in before a real run")
    if not progress.exists():
        progress.write_text("", encoding="utf-8")
        print(f"created {progress.name} (empty)")


def build_command(
    prompt: str,
    *,
    sandbox: bool,
    interactive: bool,
    yolo: bool = False,
    allow: list[str] | None = None,
) -> list[str]:
    claude_args = ["claude"]
    if yolo:
        # Bypass ALL prompts (file edits AND bash). No isolation - use a branch.
        claude_args += ["--dangerously-skip-permissions"]
    else:
        claude_args += ["--permission-mode", "acceptEdits"]
        if allow:
            # Pre-approve specific tools so the loop doesn't stall on them.
            claude_args += ["--allowedTools", *allow]
    if not interactive:
        claude_args += ["-p"]  # print mode: run headless and exit
    claude_args += [prompt]

    if sandbox:
        # docker sandbox run claude ...
        return [resolve("docker"), "sandbox", "run"] + claude_args
    claude_args[0] = resolve("claude")
    return claude_args


def run_iteration(cmd: list[str], *, capture: bool, env: dict | None = None) -> str:
    """Run one Claude invocation. Returns captured stdout (or '' if streaming)."""
    if capture:
        # Claude emits UTF-8; Windows would otherwise decode the captured pipes
        # with the locale codec (cp1252) and the reader thread dies on bytes like
        # 0x90. Pin UTF-8 and replace undecodable bytes instead of crashing.
        proc = subprocess.run(
            cmd, text=True, capture_output=True, env=env,
            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
        )
        out = proc.stdout or ""
        if out:
            print(out)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        return out
    # Interactive / streaming: let Claude inherit the terminal.
    subprocess.run(cmd, env=env)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-platform Ralph loop for Claude Code (GitHub-issues kanban)."
    )
    parser.add_argument(
        "iterations",
        nargs="?",
        type=int,
        default=1,
        help="Max autonomous iterations (ignored with --once). Default: 1.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single supervised iteration (streams to your terminal).",
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Wrap Claude in `docker sandbox run` (needs Docker Desktop).",
    )
    parser.add_argument(
        "--yolo",
        action="store_true",
        help="--dangerously-skip-permissions: bypass ALL prompts, no isolation.",
    )
    parser.add_argument(
        "--allow",
        nargs="+",
        metavar="TOOL",
        help='Scoped allowlist. Issue mode needs gh+git+tests, e.g. '
             '--allow "Bash(gh:*)" "Bash(git:*)" "Bash(npm test:*)".',
    )
    parser.add_argument(
        "--no-branch",
        action="store_true",
        help="Skip auto-creating a ralph/run-* branch for unattended runs.",
    )
    # Issue mode (default) options
    parser.add_argument(
        "--label",
        default="ready-for-agent",
        help="Trigger label Ralph pulls from the issue tracker (default: ready-for-agent).",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Override repo slug for gh (default: inferred from the git remote).",
    )
    # File mode (legacy)
    parser.add_argument(
        "--from-file",
        action="store_true",
        help="Use the legacy local PRD-checklist + progress-file mode instead of issues.",
    )
    parser.add_argument("--prd", default="PRD.md", help="(file mode) PRD file. Default: PRD.md")
    parser.add_argument(
        "--progress",
        default="progress.txt",
        help="(file mode) progress file. Default: progress.txt",
    )
    args = parser.parse_args()

    issue_mode = not args.from_file
    env = child_env(issue_mode)

    # Select prompts for the chosen mode.
    if issue_mode:
        repo_note = f"; pass --repo to gh as {args.repo}" if args.repo else ""
        once_prompt = PROMPT_ISSUES_ONCE.format(label=args.label, repo_note=repo_note)
        loop_prompt = PROMPT_ISSUES_LOOP.format(label=args.label, repo_note=repo_note)
        source_desc = f"GitHub issues labelled '{args.label}'"
    else:
        prd = Path(args.prd)
        progress = Path(args.progress)
        ensure_files(prd, progress)
        once_prompt = PROMPT_FILE_ONCE.format(prd=prd.name, progress=progress.name)
        loop_prompt = PROMPT_FILE_LOOP.format(prd=prd.name, progress=progress.name)
        source_desc = f"{prd.name} + {progress.name}"

    unattended = args.sandbox or args.yolo or bool(args.allow)

    if args.once:
        cmd = build_command(
            once_prompt, sandbox=args.sandbox, interactive=True,
            yolo=args.yolo, allow=args.allow,
        )
        print(f"ralph: single supervised iteration against {source_desc}")
        run_iteration(cmd, capture=False, env=env)
        return 0

    if args.iterations < 1:
        sys.exit("error: iterations must be >= 1")

    if not unattended:
        print(
            "warning: no --sandbox/--yolo/--allow given. The loop runs Bash "
            "(gh, tests, git commit) which acceptEdits does NOT auto-approve, so "
            "it will likely STALL on the first prompt. Not safe to leave unattended."
        )
    elif not args.no_branch:
        make_ralph_branch()

    print(f"ralph: autonomous loop against {source_desc}")
    for i in range(1, args.iterations + 1):
        print(f"\n=== ralph iteration {i}/{args.iterations} ===")
        cmd = build_command(
            loop_prompt, sandbox=args.sandbox, interactive=False,
            yolo=args.yolo, allow=args.allow,
        )
        out = run_iteration(cmd, capture=True, env=env)
        if COMPLETE_SENTINEL in out:
            print(f"\nBacklog complete after {i} iteration(s).")
            return 0

    print(f"\nReached iteration cap ({args.iterations}) without completion signal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
