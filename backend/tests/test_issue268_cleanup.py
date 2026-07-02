"""ISSUE-268 — triage cleanups (from #239/#240/#241).

Two backend tidy-ups pinned here:

* The raw master/agent-only RBAC primitives
  ``/api/v1/production/permissions/{check,list,grant,revoke}`` have zero frontend
  consumers — merchants edit staff access through the owner-scoped
  ``/staff-permissions/*`` editor instead. They are marked platform-internal
  (a distinct route tag) so their orphaned status is explicit and reviewable,
  while the owner-scoped editor stays merchant-facing and untouched.

* The generic ``/api/v1/storage/*`` HTTP router has no product HTTP consumer
  (the real caller is the ``StorageService`` class, used directly by the CSV
  export path). Rather than trim it — its ``list-buckets`` 503-when-unconfigured
  guard is exercised by ISSUE-030 — it is documented as an intentional optional
  cloud-backend surface, and ``StorageService`` remains load-bearing.
"""
from routers import production, storage

PLATFORM_INTERNAL = "platform-internal"

PRIMITIVE_PATHS = {
    "/api/v1/production/permissions/check",
    "/api/v1/production/permissions/list",
    "/api/v1/production/permissions/grant",
    "/api/v1/production/permissions/revoke",
}


def _routes_by_path(router):
    return {r.path: r for r in router.routes if hasattr(r, "path")}


def test_rbac_primitives_marked_platform_internal():
    routes = _routes_by_path(production.router)
    for path in PRIMITIVE_PATHS:
        assert path in routes, f"expected primitive route {path} to still exist"
        assert PLATFORM_INTERNAL in (routes[path].tags or []), (
            f"{path} is an orphaned RBAC primitive (no FE consumer) and should be "
            f"tagged {PLATFORM_INTERNAL!r}"
        )


def test_staff_permissions_editor_left_merchant_facing():
    # The owner-scoped editor merchants actually use must NOT be flagged internal.
    routes = _routes_by_path(production.router)
    staff_routes = [r for p, r in routes.items() if "/staff-permissions/" in p]
    assert staff_routes, "expected the owner-scoped staff-permissions editor routes"
    for r in staff_routes:
        assert PLATFORM_INTERNAL not in (r.tags or []), (
            f"{r.path} is the merchant-facing editor and must stay untouched"
        )


def test_storage_router_documented_as_optional_surface():
    doc = (storage.__doc__ or "").lower()
    assert "optional" in doc, "storage router should document itself as optional"
    assert "storage" in doc
    # StorageService stays load-bearing (the CSV export path calls it directly).
    from services.storage import StorageService

    assert StorageService is not None
