"""Issue #211 — the DR runbook is present and documents the recovery targets.

The backup *automation* and *indicator* are only operable against documented
RPO/RTO targets and a written recovery procedure. This guard keeps the runbook
honest: it must exist and cover the targets, the region-failover plan, the
offline-queue-drain validation, and the restore-drill procedure named in the
issue's acceptance criteria. Pure static check over the working tree.
"""
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_RUNBOOK = _REPO / "DR_RUNBOOK.md"


def test_dr_runbook_exists_and_documents_recovery():
    assert _RUNBOOK.is_file(), "DR_RUNBOOK.md is missing at the repo root"
    text = _RUNBOOK.read_text(encoding="utf-8").lower()

    for term in ("rpo", "rto", "region failover", "offline-queue-drain", "restore drill"):
        assert term in text, f"DR runbook does not document '{term}'"


def test_dr_runbook_rpo_rto_match_the_indicator():
    """The documented targets must match the constants the health endpoint uses."""
    from routers.tenant import BACKUP_RPO_TARGET_SECONDS, BACKUP_RTO_TARGET_SECONDS

    text = _RUNBOOK.read_text(encoding="utf-8")
    assert f"{BACKUP_RPO_TARGET_SECONDS // 3600}h" in text  # 24h RPO
    assert f"{BACKUP_RTO_TARGET_SECONDS // 3600}h" in text  # 4h RTO
