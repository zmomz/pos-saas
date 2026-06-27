"""ARC-02 — declared backend deps must not include the removed aihub stack.

The AI Hub module (routers/services/schemas ``aihub.py``) was removed as orphan
surface (see ``test_orphan_routers.py``'s ``REMOVED_BACKEND``). Its three runtime
dependencies — ``openai``, ``sse-starlette`` and ``PyMuPDF`` — had no remaining
import anywhere under ``backend/`` (only ``.venv`` site-packages), so they are
dead declarations. Removing them shrinks the install/attack surface; this guard
keeps them from creeping back into the authoritative ``requirements.txt``.
"""
import re
from pathlib import Path

_REQUIREMENTS = Path(__file__).resolve().parent.parent / "requirements.txt"

# The aihub stack: pip-distribution names exactly as they were declared.
_REMOVED_AIHUB_DEPS = ("openai", "sse-starlette", "pymupdf")


def _declared_packages(requirements: Path) -> set[str]:
    """Lower-cased distribution names declared in a requirements file.

    Strips comments, blank lines, version specifiers and extras so a line like
    ``sse-starlette>=1.6.0`` or ``uvicorn[standard]>=0.29.0`` reduces to its
    bare package name.
    """
    names: set[str] = set()
    for raw in requirements.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name = re.split(r"[<>=!~\[\s]", line, 1)[0]
        if name:
            names.add(name.lower())
    return names


def test_requirements_omit_removed_aihub_deps():
    declared = _declared_packages(_REQUIREMENTS)
    leaked = sorted(declared & set(_REMOVED_AIHUB_DEPS))
    assert not leaked, (
        f"requirements.txt still declares removed aihub deps {leaked}; the "
        "aihub module is gone and nothing under backend/ imports them."
    )
