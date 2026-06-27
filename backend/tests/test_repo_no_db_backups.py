"""ARC-01 — no SQLite backup files are tracked, and the ignore rule covers them.

The audit (§ARC-01) flagged ``backend/app.db.bak``: a ~1 MB SQLite backup with
real rows tracked in git. ``.gitignore`` ignored ``*.db`` but NOT ``*.bak`` /
``*.db.bak``, and ``seed_demo.py --rebuild`` writes ``app.db.bak`` on every
rebuild — so the backup kept reappearing in ``git status`` and could be
re-committed. This guard makes the regression catchable forever:

  1. No ``*.bak`` / ``*.db.bak`` file may be tracked by git.
  2. ``.gitignore`` must ignore a representative backup path so a fresh
     ``seed_demo.py --rebuild`` artifact stays untracked.

Pure static checks over the working tree — no DB/app boot.
"""
import subprocess
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_no_db_backup_files_are_tracked():
    """No ``*.bak`` SQLite backup (e.g. ``backend/app.db.bak``) is git-tracked."""
    tracked = _git("ls-files").splitlines()
    backups = [p for p in tracked if p.endswith(".bak")]
    assert not backups, (
        "SQLite backup file(s) are tracked in git — untrack them "
        "(`git rm --cached <path>`); they are local rebuild artifacts:\n  "
        + "\n  ".join(backups)
    )


def test_gitignore_covers_db_backups():
    """The ignore rules keep a ``seed_demo --rebuild`` ``app.db.bak`` untracked."""
    out = _git("check-ignore", "backend/app.db.bak").strip()
    assert out, (
        ".gitignore does not ignore backend/app.db.bak — add a `*.bak` (or "
        "`*.db.bak`) rule so rebuild backups never get committed"
    )
