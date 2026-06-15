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
    "api_usage.py": "generic entity triad (API metering, backend-written)",
    "loyalty_points.py": "generic entity triad (loyalty driven by /api/v1/pos)",
    "loyalty_programs.py": "generic entity triad (loyalty config)",
    "transactions.py": "generic entity triad (sales written via /api/v1/pos)",
    # Backend-internal: no frontend caller by design.
    "health.py": "liveness/DB probe (/database/health), ops-internal",
    "settings.py": "admin runtime key-value settings (/api/v1/admin/settings)",
    # Wire-later (F-054 operator decision; IB §8 orphan ledger):
    "storage.py": "object storage — kept for a later AG-07 exports wire-up",
    # receipt_templates.py was wired into the frontend by the ReceiptTemplateDesigner
    # page (#48, /api/v1/entities/receipt_templates), so its allowlist entry is no
    # longer stale-honest — it is now a referenced router and must not be listed.
}

# Files this finding (and F-006) removed; re-mounting any of them is a regression.
REMOVED_BACKEND = [
    _ROUTERS_DIR / "aihub.py",
    _BACKEND / "services" / "aihub.py",
    _BACKEND / "schemas" / "aihub.py",
    _ROUTERS_DIR / "integrations.py",
    _ROUTERS_DIR / "payment.py",  # F-006 (Stripe Checkout orphan)
    # H1: the orphaned packages CRUD scaffold shipped full create/update/delete
    # + /batch at /api/v1/entities/packages with NO auth on the write verbs. The
    # only package surface is the master-gated soft-delete path in features.py.
    _ROUTERS_DIR / "packages.py",
    # H2: the agents/agent_features CRUD scaffolds let any authenticated user
    # create/update/HARD-DELETE branding + feature-flag rows keyed on their own
    # user_id. The real surface is tenant.py/features.py; the SQLAlchemy models
    # (models/agents.py, models/agent_features.py) are kept — only the orphaned
    # routers/services are removed.
    _ROUTERS_DIR / "agents.py",
    _BACKEND / "services" / "agents.py",
    _ROUTERS_DIR / "agent_features.py",
    _BACKEND / "services" / "agent_features.py",
    # H13: the generic permissions CRUD scaffold scoped every op on
    # Permissions.user_id == current_user.id — a contradictory self-ownership
    # model (a user could only ever see/edit grants about themselves) with no
    # frontend caller. RBAC is enforced through dependencies/permissions.py; the
    # Permissions model (models/permissions.py) is kept — only the orphaned
    # router/service are removed.
    _ROUTERS_DIR / "permissions.py",
    _BACKEND / "services" / "permissions.py",
    # H14/H15: the clients/client_features CRUD scaffolds scoped every op on
    # user_id == current_user.id (a merchant could only ever touch grants about
    # its own login — structurally incapable of managing another tenant), and
    # clients.py additionally exposed an admin /clients/all cross-tenant read
    # (H15). No frontend caller; the live per-client toggle is tenant.py +
    # features.py (AgentDashboard). The models (models/clients.py,
    # models/client_features.py) are kept — only the orphaned routers/services
    # are removed.
    _ROUTERS_DIR / "clients.py",
    _BACKEND / "services" / "clients.py",
    _ROUTERS_DIR / "client_features.py",
    _BACKEND / "services" / "client_features.py",
    # H20: the generic shifts CRUD scaffold mounted full create/update/HARD-DELETE
    # + /batch at /api/v1/entities/shifts, letting any authenticated client PUT/
    # DELETE arbitrary shift fields. The real shift lifecycle (open/close/
    # movements/reconciliation) lives in production.py and is the only path the UI
    # calls; the model (models/shifts.py) is kept — only the orphaned router/
    # service are removed.
    _ROUTERS_DIR / "shifts.py",
    _BACKEND / "services" / "shifts.py",
]
REMOVED_FRONTEND = [
    _FRONTEND_SRC / "pages" / "AuthCallback.tsx",
    _FRONTEND_SRC / "pages" / "AuthError.tsx",
    _FRONTEND_SRC / "blog-routes.tsx",
    _FRONTEND_SRC / "lib" / "blog.ts",
    _FRONTEND_SRC / "pages" / "blog",
    _FRONTEND_SRC / "components" / "blog",
]

# F-004 / §4 dead code (#8): the ``data_models/*.json`` generator artifacts whose
# entity routers were deleted as dead/unused (#1–#4 + H20). Nothing in the
# codebase reads ``data_models/`` at runtime (it is pure scaffold metadata), so a
# JSON whose router is gone only advertises surface that isn't real. These must
# stay deleted; the live entity triads still on the ALLOWLIST keep their JSON.
_DATA_MODELS = _BACKEND / "data_models"
REMOVED_DATA_MODELS = [
    _DATA_MODELS / "packages.json",        # router removed in #1
    _DATA_MODELS / "agents.json",          # router removed in #2
    _DATA_MODELS / "agent_features.json",  # router removed in #2
    _DATA_MODELS / "permissions.json",     # router + json removed in #3
    _DATA_MODELS / "clients.json",         # router removed in #4
    _DATA_MODELS / "client_features.json", # router removed in #4
    _DATA_MODELS / "shifts.json",          # router removed (H20)
]
# Sanity anchor: a live entity triad whose JSON must NOT be swept up. products.py
# is a referenced router, so its generator JSON stays.
_LIVE_DATA_MODEL = _DATA_MODELS / "products.json"


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


def test_orphaned_data_models_deleted():
    """§4 (#8): generator JSON for deleted/unused entity routers is gone, but the
    JSON for live entity triads on the allowlist is left untouched."""
    present = [str(p.relative_to(_REPO)) for p in REMOVED_DATA_MODELS if p.exists()]
    assert not present, (
        "Orphaned data_models JSON reappeared — these advertise surface whose "
        "router was deleted as dead code (#1–#4, H20):\n  " + "\n  ".join(present)
    )
    # Guard against over-deletion: a live triad keeps its scaffold JSON.
    assert _LIVE_DATA_MODEL.exists(), (
        "products.json (a live entity triad) must not be deleted — only the "
        "JSON for deleted/unused routers is in scope for #8"
    )


def test_packages_service_class_gone_helpers_kept():
    """H1: the CRUD PackagesService is deleted; the two feature-tier helpers,
    consumed by features.py/tenant.py, are preserved in services/packages.py."""
    import services.packages as pkg

    assert not hasattr(pkg, "PackagesService"), (
        "PackagesService (orphaned CRUD) must be deleted; only the feature-tier "
        "helpers may remain in services/packages.py"
    )
    # The helpers the master-gated path depends on must still be importable.
    from services.packages import normalize_feature_tier, parse_feature_tier

    assert callable(normalize_feature_tier) and callable(parse_feature_tier)
