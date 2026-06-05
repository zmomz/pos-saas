"""F-054 — orphan-lint: every backend router must have a frontend caller.

The IB §8 "orphan ledger" finding: MGX scaffolding (AI Hub, the Stripe Checkout
router, the duplicate ``integrations.py``, the blog, the OAuth callback) shipped
mounted but unreachable — dead surface that widens the audit/attack surface and
confuses maintenance. This is the "make it catchable forever" guard the finding
named: a CI lint that flags **any backend router with no frontend caller**.

How it works (pure static analysis — no DB/app boot, fully deterministic):

  1. For every module in ``backend/routers`` we extract the concrete route paths
     it mounts (``APIRouter(prefix=...)`` + each ``@router.<method>("...")``).
  2. We concatenate ``frontend/src`` and ask, per module, whether the frontend
     references any of its paths — either a literal ``/api/v1/...`` URL (custom
     routers, called via ``client.apiCall.invoke({url})``) or, for the generic
     entity triads at ``/api/v1/entities/<name>``, the ``client.entities.<name>``
     SDK form.
  3. The set of **unreferenced** routers must equal the documented ``ALLOWLIST``
     exactly. A newly-added router with no caller grows the set → this test
     fails until it is wired into ``src/lib/api.ts`` or consciously allowlisted
     with a reason. Wiring an allowlisted router shrinks the set → also fails,
     forcing the allowlist to stay honest.

The allowlist is intentionally small and reasoned: the generic entity-CRUD
triads (a documented convention in CLAUDE.md — they expose ``/all`` + ``/batch``
scaffolding reachable via ``client.entities`` even where the live UI drives them
through a domain router), two backend-internal routers, and the two modules the
operator kept for a later AG-07 wire-up (object storage + receipt templates).
"""
import re
from pathlib import Path

# Repo layout: this file is backend/tests/test_orphan_routers.py
_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
_ROUTERS_DIR = _BACKEND / "routers"
_FRONTEND_SRC = _REPO / "frontend" / "src"


# --- The documented allowlist: routers with no frontend caller, on purpose. ---
# Keep each entry justified. To clear one, wire it into the frontend and delete
# the line; to add one, wire it OR add it here with an honest reason.
ALLOWLIST = {
    # Generic entity-CRUD triads (CLAUDE.md convention): list/get/create/update/
    # delete + /batch + an unauthenticated /all, available via client.entities.
    # The live UI reaches these entities through domain routers (tenant/pos/…),
    # so they carry no dedicated literal caller — but they are the convention,
    # not dead code.
    "agent_features.py": "generic entity triad (white-label feature flags)",
    "agents.py": "generic entity triad (managed via /api/v1/tenant)",
    "api_usage.py": "generic entity triad (API metering, backend-written)",
    "client_features.py": "generic entity triad (per-client feature flags)",
    "clients.py": "generic entity triad (provisioned via /api/v1/tenant)",
    "loyalty_points.py": "generic entity triad (loyalty driven by /api/v1/pos)",
    "loyalty_programs.py": "generic entity triad (loyalty config)",
    "permissions.py": "generic entity triad (RBAC enforced via dependencies)",
    "shifts.py": "generic entity triad (shift ops via /api/v1/production + pos)",
    "transactions.py": "generic entity triad (sales written via /api/v1/pos)",
    # Backend-internal: no frontend caller by design.
    "health.py": "liveness/DB probe (/database/health), ops-internal",
    "settings.py": "admin runtime key-value settings (/api/v1/admin/settings)",
    # Wire-later (F-054 operator decision; IB §8 orphan ledger):
    "storage.py": "object storage — kept for a later AG-07 exports wire-up",
    "receipt_templates.py": "AG-07 branded-printables editor — WIRE-UP gap (not dead)",
}

# Files this finding (and F-006) removed; re-mounting any of them is a regression.
REMOVED_BACKEND = [
    _ROUTERS_DIR / "aihub.py",
    _BACKEND / "services" / "aihub.py",
    _BACKEND / "schemas" / "aihub.py",
    _ROUTERS_DIR / "integrations.py",
    _ROUTERS_DIR / "payment.py",  # F-006 (Stripe Checkout orphan)
]
REMOVED_FRONTEND = [
    _FRONTEND_SRC / "pages" / "AuthCallback.tsx",
    _FRONTEND_SRC / "pages" / "AuthError.tsx",
    _FRONTEND_SRC / "blog-routes.tsx",
    _FRONTEND_SRC / "lib" / "blog.ts",
    _FRONTEND_SRC / "pages" / "blog",
    _FRONTEND_SRC / "components" / "blog",
]


def _frontend_source() -> str:
    parts = []
    for p in _FRONTEND_SRC.rglob("*"):
        if p.is_file() and p.suffix in (".ts", ".tsx"):
            parts.append(p.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def _route_paths(src: str) -> list[str]:
    """Extract the concrete route paths a router module mounts."""
    prefixes: dict[str, str] = {}
    for var, args in re.findall(r"(\w+)\s*=\s*APIRouter\(([^)]*)\)", src):
        m = re.search(r'prefix=["\']([^"\']*)["\']', args)
        prefixes[var] = m.group(1) if m else ""
    paths: list[str] = []
    for var, _method, path in re.findall(
        r'@(\w+)\.(get|post|put|patch|delete)\(\s*["\']([^"\']*)["\']', src
    ):
        paths.append(prefixes.get(var, "") + path)
    if not paths and prefixes:
        paths = list(prefixes.values())
    return paths


def _is_referenced(full_path: str, frontend: str) -> bool:
    full = full_path.split("{")[0].rstrip("/")
    entity = re.match(r"/api/v1/entities/(\w+)", full)
    if entity:
        name = entity.group(1)
        return (f"entities.{name}" in frontend) or (f"entities/{name}" in frontend)
    return bool(full) and full in frontend


def _unreferenced_routers() -> dict[str, list[str]]:
    """Map each router module with NO frontend caller to its sample paths."""
    frontend = _frontend_source()
    orphans: dict[str, list[str]] = {}
    for f in sorted(_ROUTERS_DIR.glob("*.py")):
        if f.name == "__init__.py":
            continue
        paths = _route_paths(f.read_text(encoding="utf-8", errors="ignore"))
        if paths and not any(_is_referenced(p, frontend) for p in paths):
            orphans[f.name] = paths[:3]
    return orphans


def test_no_backend_router_is_orphaned():
    """Every mounted router has a frontend caller, or is a documented exception."""
    orphans = _unreferenced_routers()

    # A new orphan: a router with no frontend caller that nobody allowlisted.
    undocumented = {name: paths for name, paths in orphans.items() if name not in ALLOWLIST}
    assert not undocumented, (
        "Backend router(s) with no frontend caller and not in the allowlist — "
        "wire them into frontend/src/lib/api.ts or add a justified ALLOWLIST entry:\n"
        + "\n".join(f"  routers/{n}: {p}" for n, p in undocumented.items())
    )

    # A stale allowlist entry: it is now referenced (wire-up done) or removed.
    # Force the allowlist to shrink as orphans get wired or deleted.
    stale = sorted(set(ALLOWLIST) - set(orphans))
    assert not stale, (
        "Stale ALLOWLIST entries — these routers are now referenced or removed; "
        "drop them from the allowlist:\n  " + ", ".join(stale)
    )


def test_removed_orphans_stay_removed():
    """The dead MGX scaffolding this finding (and F-006) deleted must not return."""
    present = [str(p.relative_to(_REPO)) for p in REMOVED_BACKEND + REMOVED_FRONTEND if p.exists()]
    assert not present, (
        "Removed orphan(s) reappeared — these were deleted as dead code "
        "(F-054 / F-006):\n  " + "\n  ".join(present)
    )
