"""Seed one complete demo tenant so every workflow can be tried end-to-end.

Out of the box the app only seeds the platform master (ADMIN_EMAIL/ADMIN_PASSWORD,
see services/auth.py::initialize_admin_user) and has no business data — so you can
log in as the master but can't exercise the POS / restaurant / staff-role flows.

This standalone CLI builds the full object graph the tenancy layer expects
(agent -> client/merchant -> branch -> categories -> products -> customers ->
restaurant tables) plus a login per role, then prints a credentials table.

How the logins resolve to a tenant (dependencies/tenancy.py::resolve_tenant_scope):
  * the AGENT login owns an ``agents`` row     -> agent / reseller scope
  * the MERCHANT login owns a ``clients`` row  -> client scope; owns the catalog
  * the MANAGER / CASHIER logins each own a ``staff_members`` row whose *email*
    matches the login and whose ``user_id`` is the MERCHANT's id, so they share
    the merchant's catalog/customers/sales (staff -> owner resolution)
  * the existing master (users.role == "admin") stays unrestricted

Usage (from the backend/ directory, with backend/.env configured):

    python seed_demo.py              # seed the demo tenant into the current DB
    python seed_demo.py --rebuild    # first drop+recreate the schema, then seed

Use ``--rebuild`` when the local app.db was built by an older model version and
is missing columns the current models need (create_all never ALTERs existing
tables). It backs the DB up to ``app.db.bak``, drops + recreates the full schema,
restores the admin account + reference packages, then seeds the demo tenant.

Idempotent: re-running (without --rebuild) reuses existing rows (reports "exists"
vs "created") and never duplicates. Credentials are overridable via env vars.
"""
import asyncio
import os
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Load backend/.env into the environment BEFORE importing any app module.
#    core/config.py only auto-loads .env under a debugger (see run.ps1 notes),
#    so a plain `python seed_demo.py` would otherwise start with the insecure
#    defaults and possibly the wrong DATABASE_URL. We mirror run.ps1's loader.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent
# chdir so a relative sqlite URL (sqlite:///./app.db) resolves to backend/app.db,
# exactly like run.ps1 (which Push-Locations into backend/ before uvicorn).
os.chdir(_BACKEND_DIR)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        print(f"WARNING: {path} not found; relying on the current environment.")
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
            val = val[1:-1]
        # Real environment variables already set win over the .env file.
        os.environ.setdefault(key, val)


_load_env_file(_BACKEND_DIR / ".env")

# Now it's safe to import the app's config/db/models.
from core.config import settings  # noqa: E402
from core.database import Base, db_manager  # noqa: E402
from models.agents import Agents  # noqa: E402
from models.branches import Branches  # noqa: E402
from models.categories import Categories  # noqa: E402
from models.clients import Clients  # noqa: E402
from models.customers import Customers  # noqa: E402
from models.packages import Packages  # noqa: E402
from models.permissions import Permissions  # noqa: E402
from models.products import Products  # noqa: E402
from models.restaurant import RestaurantTables  # noqa: E402
from models.staff_members import Staff_members  # noqa: E402
from services.auth import AuthService, initialize_admin_user  # noqa: E402
from services.database import initialize_database  # noqa: E402
from services.mock_data import initialize_mock_data  # noqa: E402
from sqlalchemy import select  # noqa: E402

# ---------------------------------------------------------------------------
# 2. Demo credentials (overridable via env vars).
# ---------------------------------------------------------------------------
PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo12345")
AGENT_EMAIL = os.environ.get("DEMO_AGENT_EMAIL", "agent@demo.pos")
MERCHANT_EMAIL = os.environ.get("DEMO_MERCHANT_EMAIL", "merchant@demo.pos")
MANAGER_EMAIL = os.environ.get("DEMO_MANAGER_EMAIL", "manager@demo.pos")
CASHIER_EMAIL = os.environ.get("DEMO_CASHIER_EMAIL", "cashier@demo.pos")

# Track what we created vs reused, for the final summary.
_log: list[str] = []


def _note(action: str, what: str) -> None:
    _log.append(f"  [{action:>7}] {what}")


# ---------------------------------------------------------------------------
# 3. get-or-create helpers (idempotency).
# ---------------------------------------------------------------------------
async def ensure_user(auth: AuthService, email: str, name: str, role: str = "user"):
    """Return the User for ``email``, creating it (hashed password) if absent."""
    existing = await auth.get_user_by_email(email)
    if existing:
        _note("exists", f"user {email} (id={existing.id})")
        return existing
    user = await auth.create_user(email=email, password=PASSWORD, name=name, role=role)
    _note("created", f"user {email} (id={user.id})")
    return user


async def get_or_create(db, model, lookup: dict, defaults: dict, label: str):
    """Generic single-row get-or-create keyed on ``lookup`` field equality."""
    stmt = select(model)
    for field, value in lookup.items():
        stmt = stmt.where(getattr(model, field) == value)
    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        _note("exists", f"{label} (id={existing.id})")
        return existing
    obj = model(**{**lookup, **defaults})
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    _note("created", f"{label} (id={obj.id})")
    return obj


# ---------------------------------------------------------------------------
# 4. Optional schema rebuild (--rebuild).
#    A local app.db built by an older model version can be missing columns the
#    current models require (create_all never ALTERs existing tables). Rebuilding
#    drops every table and recreates the full current schema, then restores the
#    admin account and the reference packages. Backs the old file up first.
# ---------------------------------------------------------------------------
def _sqlite_file_path() -> Path | None:
    """Return the on-disk path of the configured sqlite DB, or None if not sqlite."""
    url = os.environ.get("DATABASE_URL") or getattr(settings, "database_url", "") or ""
    if not url.startswith("sqlite"):
        return None
    # sqlite:///./app.db  or  sqlite:////abs/path.db (strip the scheme + slashes).
    tail = url.split(":///", 1)[-1] if ":///" in url else url.split("://", 1)[-1]
    return Path(tail).resolve()


async def rebuild_schema() -> None:
    await db_manager.init_db()  # set up engine/session

    db_path = _sqlite_file_path()
    if db_path and db_path.exists():
        backup = db_path.with_suffix(db_path.suffix + ".bak")
        shutil.copy2(db_path, backup)
        _note("backup", f"{db_path.name} -> {backup.name}")

    async with db_manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    db_manager._initialized = True
    _note("rebuilt", "schema dropped + recreated from current models")

    await initialize_admin_user()   # restore the platform master from ADMIN_*
    _note("reseeded", f"admin account ({os.environ.get('ADMIN_EMAIL', 'admin@example.com')})")
    await initialize_mock_data()    # restore the reference packages
    _note("reseeded", "reference packages (mock_data)")


# ---------------------------------------------------------------------------
# 5. Build the demo tenant.
# ---------------------------------------------------------------------------
async def seed() -> None:
    await initialize_database()  # create_all (matches the default run.ps1 path)

    async with db_manager.async_session_maker() as db:
        auth = AuthService(db)

        # A package gives the agent a feature-entitlement tier (3 are pre-seeded).
        # Select only the id: an older app.db may lack newer Packages columns
        # (create_all never alters existing tables), so loading the full row fails.
        package_id = (await db.execute(select(Packages.id).order_by(Packages.id))).scalars().first()

        # --- Agent (reseller) ---------------------------------------------
        agent_user = await ensure_user(auth, AGENT_EMAIL, "Demo Agent", role="user")
        agent = await get_or_create(
            db, Agents,
            lookup={"user_id": agent_user.id},
            defaults={
                "company_name": "Demo Agent Co.",
                "email": AGENT_EMAIL,
                "phone": "+966500000001",
                "package_type": 10,
                "package_id": package_id,
                "used_slots": 1,
                "is_active": True,
                "default_language": "en",
            },
            label="agent (Demo Agent Co.)",
        )

        # --- Client / merchant (owns the catalog) -------------------------
        merchant_user = await ensure_user(auth, MERCHANT_EMAIL, "Demo Merchant", role="user")
        mid = merchant_user.id  # every catalog row is owner-scoped by this id
        client = await get_or_create(
            db, Clients,
            lookup={"user_id": mid},
            defaults={
                "agent_id": agent.id,
                "business_name": "Demo Merchant Shop",
                "email": MERCHANT_EMAIL,
                "phone": "+966500000002",
                "subscription_fee": 100.0,
                "billing_cycle": "monthly",
                "subscription_status": "active",
                "is_active": True,
                # "both" so BOTH the retail and restaurant verticals are available.
                "business_type": "both",
                "zatca_enabled": True,
                "invoice_counter": 0,
            },
            label="client (Demo Merchant Shop)",
        )

        # --- Branch -------------------------------------------------------
        branch = await get_or_create(
            db, Branches,
            lookup={"user_id": mid, "name": "Main Branch"},
            defaults={
                "client_id": client.id,
                "address": "123 King Fahd Rd",
                "city": "Riyadh",
                "phone": "+966500000003",
                "is_active": True,
                "is_main": True,
            },
            label="branch (Main Branch)",
        )

        # --- Categories ---------------------------------------------------
        categories = ["Beverages", "Food", "Retail"]
        for i, cat in enumerate(categories):
            await get_or_create(
                db, Categories,
                lookup={"user_id": mid, "name": cat},
                defaults={"sort_order": i},
                label=f"category ({cat})",
            )

        # --- Products (mix of normal, weighted, open-price) ---------------
        products = [
            # name, price, category, extras
            ("Espresso", 12.0, "Beverages", {"quantity": 200}),
            ("Cappuccino", 16.0, "Beverages", {"quantity": 200}),
            ("Fresh Orange Juice", 18.0, "Beverages", {"quantity": 80}),
            ("Cheeseburger", 28.0, "Food", {"quantity": 60}),
            ("Margherita Pizza", 39.0, "Food", {"quantity": 40}),
            ("Loose Dates", 45.0, "Retail",
             {"quantity": 25.0, "is_weighted": True, "unit_label": "kg"}),
            ("Gift Hamper (custom)", 0.0, "Retail", {"is_open_price": True, "quantity": 15}),
            ("Bottled Water", 3.0, "Retail", {"quantity": 500}),
        ]
        for name, price, cat, extras in products:
            await get_or_create(
                db, Products,
                lookup={"user_id": mid, "client_id": client.id, "name": name},
                defaults={"price": price, "category": cat, "vat_rate": 15.0,
                          "is_active": True, **extras},
                label=f"product ({name})",
            )

        # --- Customers ----------------------------------------------------
        customers = [
            ("Walk-in Customer", "+966511111111", "walkin@demo.pos"),
            ("Acme Corp (B2B)", "+966522222222", "ap@acme.demo"),
        ]
        for name, phone, email in customers:
            extra = {"phone": phone, "email": email}
            if "B2B" in name:
                extra["vat_number"] = "300000000000003"  # routes to ZATCA B2B
            await get_or_create(
                db, Customers,
                lookup={"user_id": mid, "name": name},
                defaults=extra,
                label=f"customer ({name})",
            )

        # --- Restaurant tables (business_type "both") ---------------------
        for n in range(1, 5):
            await get_or_create(
                db, RestaurantTables,
                lookup={"user_id": mid, "name": f"T{n}"},
                defaults={"client_id": client.id, "branch_id": branch.id,
                          "seats": 4, "state": "free"},
                label=f"table (T{n})",
            )

        # --- Staff logins (manager + cashier) -----------------------------
        # Each needs (a) a User to log in with and (b) a staff_members row whose
        # email matches that login and whose user_id is the MERCHANT's id, so
        # tenancy resolves them into the merchant tenant (shared catalog).
        for email, name, role in [
            (MANAGER_EMAIL, "Demo Manager", "manager"),
            (CASHIER_EMAIL, "Demo Cashier", "cashier"),
        ]:
            staff_user = await ensure_user(auth, email, name, role="user")
            await get_or_create(
                db, Staff_members,
                lookup={"email": email},
                defaults={"user_id": mid, "name": name, "role": role, "is_active": True},
                label=f"staff_member ({role}: {email})",
            )
            # Demonstrate a restricted role: deny the cashier the refund capability
            # (permissions are grant-by-default; an explicit deny wins).
            if role == "cashier":
                await get_or_create(
                    db, Permissions,
                    lookup={"user_id": staff_user.id, "permission_key": "pos.refund"},
                    defaults={"role": "cashier", "is_granted": False,
                              "granted_by": "seed_demo"},
                    label="permission deny (cashier: pos.refund)",
                )


# ---------------------------------------------------------------------------
# 6. CLI entrypoint + summary.
# ---------------------------------------------------------------------------
def _print_summary() -> None:
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
    admin_pw = os.environ.get("ADMIN_PASSWORD", "changeme123")
    rows = [
        ("Master / admin", admin_email, admin_pw, "unrestricted platform owner"),
        ("Agent (reseller)", AGENT_EMAIL, PASSWORD, "reseller view; owns the demo client"),
        ("Merchant (owner)", MERCHANT_EMAIL, PASSWORD, "owns catalog/branch/customers/tables"),
        ("Manager", MANAGER_EMAIL, PASSWORD, "merchant tenant, full staff access"),
        ("Cashier", CASHIER_EMAIL, PASSWORD, "merchant tenant, refund denied"),
    ]
    w_role = max(len(r[0]) for r in rows)
    w_email = max(len(r[1]) for r in rows)
    w_pw = max(len(r[2]) for r in rows)
    print("\n" + "=" * 78)
    print("Demo tenant ready. Log in at http://localhost:8000 with:")
    print("-" * 78)
    print(f"  {'ROLE':<{w_role}}  {'EMAIL':<{w_email}}  {'PASSWORD':<{w_pw}}  NOTES")
    for role, email, pw, note in rows:
        print(f"  {role:<{w_role}}  {email:<{w_email}}  {pw:<{w_pw}}  {note}")
    print("=" * 78)


async def _main(rebuild: bool) -> int:
    if rebuild:
        print("Rebuilding schema (a backup is written first) ...")
    print("Seeding demo tenant ...")
    try:
        if rebuild:
            await rebuild_schema()
        await seed()
    except Exception as exc:  # surface the failing row clearly
        print(f"\nSEED FAILED: {exc}", file=sys.stderr)
        for line in _log:
            print(line, file=sys.stderr)
        return 1
    finally:
        await db_manager.close_db()
    print("\n".join(_log))
    _print_summary()
    return 0


if __name__ == "__main__":
    _rebuild = "--rebuild" in sys.argv[1:]
    raise SystemExit(asyncio.run(_main(_rebuild)))
