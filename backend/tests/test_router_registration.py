"""ISSUE-009 — explicit router-registration allowlist.

`include_routers_from_package` used to blanket-discover every `routers/*.py`
exposing `router`/`admin_router` via `pkgutil.walk_packages`, which is exactly
how the orphaned auto-CRUD scaffolds shipped live (the §4 / theme-#1 finding).

The fix replaces blanket discovery with an explicit, reviewed allowlist
(`routers.REGISTERED_MODULES`): a module is mounted ONLY if it is named there,
so a newly-generated router cannot auto-ship on the API without a conscious
decision. These tests pin that contract:

  1. The function mounts exactly the routes contributed by REGISTERED_MODULES,
     and that list covers every current router module — so the live mounted-route
     set is unchanged versus the post-purge blanket-discovery state.
  2. A `routers/*.py` that is NOT in the allowlist is never mounted, even though
     it exposes a valid `router`.
"""
import importlib
import sys
from pathlib import Path

from fastapi import APIRouter, FastAPI

from main import include_routers_from_package
from routers import REGISTERED_MODULES

_ROUTERS_DIR = Path(__file__).resolve().parents[1] / "routers"


def _router_module_files() -> set[str]:
    """Every leaf module in `routers/` that exposes an APIRouter (`router`)."""
    names: set[str] = set()
    for f in _ROUTERS_DIR.glob("*.py"):
        if f.name == "__init__.py":
            continue
        module = importlib.import_module(f"routers.{f.stem}")
        if any(isinstance(getattr(module, a, None), APIRouter) for a in ("router", "admin_router")):
            names.add(f.stem)
    return names


def _paths_for_modules(module_names) -> set[str]:
    """Concrete route paths contributed by the given router modules."""
    paths: set[str] = set()
    for name in module_names:
        module = importlib.import_module(f"routers.{name}")
        for attr in ("router", "admin_router"):
            r = getattr(module, attr, None)
            if isinstance(r, APIRouter):
                paths.update(route.path for route in r.routes)
    return paths


def test_mounted_routers_match_explicit_list():
    """The include function mounts exactly REGISTERED_MODULES' routes, and the
    list covers every current router module (route set unchanged vs discovery)."""
    # The allowlist must enumerate every router module currently in the package,
    # so switching off blanket discovery drops nothing that was live post-purge.
    assert set(REGISTERED_MODULES) == _router_module_files()

    app = FastAPI()
    before = {r.path for r in app.routes}
    include_routers_from_package(app, "routers")
    mounted = {r.path for r in app.routes} - before

    assert mounted == _paths_for_modules(REGISTERED_MODULES)
    assert mounted, "no routes were mounted from the explicit allowlist"


def test_unlisted_router_module_is_not_mounted():
    """A router file present in the package but absent from the allowlist must
    NOT be mounted — the auto-ship gate the finding asked for."""
    probe = _ROUTERS_DIR / "_issue009_probe.py"
    probe_path = "/api/v1/__issue009_probe__/ping"
    probe.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        f"@router.get('{probe_path}')\n"
        "def _ping():\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )
    try:
        assert "_issue009_probe" not in REGISTERED_MODULES

        app = FastAPI()
        include_routers_from_package(app, "routers")
        mounted = {r.path for r in app.routes}

        assert probe_path not in mounted, (
            "an unlisted routers/*.py was auto-mounted — the explicit allowlist "
            "is not gating registration"
        )
    finally:
        probe.unlink(missing_ok=True)
        sys.modules.pop("routers._issue009_probe", None)
