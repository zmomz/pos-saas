#!/usr/bin/env python3
"""
ralph.py - Cross-platform Ralph loop for Claude Code.

A Python port of Matt Pocock's "Ralph Wiggum" bash loops
(https://www.aihero.dev/getting-started-with-ralph). Runs identically on
Linux, macOS, and Windows.

The loop repeatedly invokes Claude Code against a PRD + progress file, doing
ONE task per iteration, until the PRD is complete (Claude emits the sentinel
<promise>COMPLETE</promise>) or the iteration cap is hit.

Usage:
    python ralph.py --once                 # one supervised iteration
    python ralph.py 20                      # up to 20 autonomous iterations
    python ralph.py 20 --sandbox           # ... inside `docker sandbox`
    python ralph.py 20 --yolo              # ... no Docker, bypass ALL prompts
    python ralph.py 20 --allow "Bash(git commit:*)" "Bash(npm test:*)"
    python ralph.py 20 --prd SPEC.md       # custom PRD file

Unattended runs (going to sleep) need prompts bypassed, since the Ralph prompt
runs Bash (tests, git commit) which `--permission-mode acceptEdits` does NOT
auto-approve. Choose ONE of:
    --sandbox   run inside `docker sandbox` (needs Docker Desktop) - safest
    --yolo      --dangerously-skip-permissions on your real machine - riskiest
    --allow ... scoped allowlist; only the listed commands auto-run
Without one of these, an autonomous loop will stall on the first Bash prompt.

For unattended modes the script first creates a `ralph/run-<timestamp>` git
branch so your main branch is never touched (disable with --no-branch).

Requirements:
    - Python 3.8+
    - The `claude` CLI on PATH (https://docs.claude.com/claude-code)
    - Docker Desktop, only if you pass --sandbox
    - git, for branch safety / per-iteration commits
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Windows consoles default to cp1252; Claude's output contains Arabic, arrows
# (→) and box-drawing. Force UTF-8 so printing captured output can't crash.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

COMPLETE_SENTINEL = "<promise>COMPLETE</promise>"

PRD_STUB = """# PRD

Describe the product / feature you want built. Break it into a checklist of
small, independently-shippable tasks. Ralph implements ONE per iteration.

## Tasks
- [ ] First task
- [ ] Second task
"""

# Supervised single-iteration prompt (mirrors Matt's ralph-once.sh).
PROMPT_ONCE = (
    "@{prd} @{progress} "
    "1. Read the PRD and progress file. "
    "2. Find the next incomplete task and implement it. "
    "3. Commit your changes. "
    "4. Update {progress} with what you did. "
    "ONLY DO ONE TASK AT A TIME."
)

# Autonomous loop prompt (mirrors Matt's afk-ralph.sh).
PROMPT_LOOP = (
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


def run_iteration(cmd: list[str], *, capture: bool) -> str:
    """Run one Claude invocation. Returns captured stdout (or '' if streaming)."""
    if capture:
        # Decode as UTF-8 (not the Windows cp1252 default) so Arabic / box-drawing
        # / emoji in Claude's output don't crash the reader thread. stdin=DEVNULL
        # stops `claude -p` from waiting on stdin it will never receive.
        proc = subprocess.run(
            cmd,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            encoding="utf-8",
            errors="replace",
        )
        out = proc.stdout or ""
        if out:
            print(out)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        return out
    # Interactive / streaming: let Claude inherit the terminal.
    subprocess.run(cmd)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-platform Ralph loop for Claude Code."
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
        help='Scoped allowlist, e.g. --allow "Bash(git commit:*)" "Bash(npm test:*)".',
    )
    parser.add_argument(
        "--no-branch",
        action="store_true",
        help="Skip auto-creating a ralph/run-* branch for unattended runs.",
    )
    parser.add_argument("--prd", default="PRD.md", help="PRD file (default: PRD.md)")
    parser.add_argument(
        "--progress",
        default="progress.txt",
        help="Progress file (default: progress.txt)",
    )
    args = parser.parse_args()

    prd = Path(args.prd)
    progress = Path(args.progress)
    ensure_files(prd, progress)

    unattended = args.sandbox or args.yolo or bool(args.allow)

    if args.once:
        prompt = PROMPT_ONCE.format(prd=prd.name, progress=progress.name)
        cmd = build_command(
            prompt, sandbox=args.sandbox, interactive=True,
            yolo=args.yolo, allow=args.allow,
        )
        print(f"ralph: single supervised iteration on {prd.name}")
        run_iteration(cmd, capture=False)
        return 0

    if args.iterations < 1:
        sys.exit("error: iterations must be >= 1")

    if not unattended:
        print(
            "warning: no --sandbox/--yolo/--allow given. The loop runs Bash "
            "(tests, git commit) which acceptEdits does NOT auto-approve, so it "
            "will likely STALL on the first prompt. Not safe to leave unattended."
        )
    elif not args.no_branch:
        make_ralph_branch()

    prompt = PROMPT_LOOP.format(prd=prd.name, progress=progress.name)
    for i in range(1, args.iterations + 1):
        print(f"\n=== ralph iteration {i}/{args.iterations} ===")
        cmd = build_command(
            prompt, sandbox=args.sandbox, interactive=False,
            yolo=args.yolo, allow=args.allow,
        )
        out = run_iteration(cmd, capture=True)
        if COMPLETE_SENTINEL in out:
            print(f"\nPRD complete after {i} iteration(s).")
            return 0

    print(f"\nReached iteration cap ({args.iterations}) without completion signal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
