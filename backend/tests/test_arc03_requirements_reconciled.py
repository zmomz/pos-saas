"""ARC-03 — a single authoritative requirements file, no dead Lambda branch.

Two backend requirements files had drifted: the authoritative ``requirements.txt``
(installed by ``run.ps1`` and CI) carried the real dependency set, while the stale
``requirements.default`` was a strict subset that still declared the AWS-Lambda
adapter ``mangum`` and the already-removed aihub stack, yet was missing six
genuinely-imported deps (bcrypt, qrcode, Pillow, fpdf2, arabic-reshaper,
python-bidi). Nothing referenced ``requirements.default``.

Lambda is unsupported — there is no ``mangum`` handler, serverless config, or
Lambda entrypoint anywhere under ``backend/`` — so the ``IS_LAMBDA`` /
``AWS_LAMBDA_FUNCTION_NAME`` engine/logging branches were dead code. These guards
keep the second file from reappearing and the dead Lambda branch from creeping
back into the source.
"""
import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent


def test_requirements_default_is_gone():
    """Only requirements.txt remains; the drifted second file is deleted."""
    assert (_BACKEND / "requirements.txt").exists(), "the authoritative file must stay"
    assert not (_BACKEND / "requirements.default").exists(), (
        "requirements.default was a stale, drifted subset referenced by nothing "
        "(run.ps1 and CI install requirements.txt); it must be deleted so there is "
        "a single authoritative requirements file."
    )


# Tokens that only exist to support an AWS-Lambda deployment that does not exist.
_LAMBDA_TOKENS = ("IS_LAMBDA", "AWS_LAMBDA_FUNCTION_NAME", "mangum", "Mangum")
# Backend source packages (the app), excluding vendored envs and the tests.
_SOURCE_DIRS = ("core", "routers", "services", "models", "middlewares", "schemas")


def _source_files() -> list[Path]:
    files = [_BACKEND / "main.py"]
    for d in _SOURCE_DIRS:
        files.extend((_BACKEND / d).rglob("*.py"))
    return [f for f in files if f.exists()]


def test_no_source_references_dead_lambda_branch():
    """No backend source file references the dead AWS-Lambda branch."""
    offenders: list[str] = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for token in _LAMBDA_TOKENS:
            if re.search(rf"\b{re.escape(token)}\b", text):
                offenders.append(f"{path.relative_to(_BACKEND)}: {token}")
    assert not offenders, (
        "Lambda is unsupported (no mangum handler / serverless config); the "
        "IS_LAMBDA branch is dead and must be removed: " + "; ".join(offenders)
    )
