# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A multi-tenant, white-label **Point-of-Sale SaaS** built for the Saudi/Arabic market (bilingual EN/AR with RTL, ZATCA VAT e-invoicing). Originally generated from a MetaGPT/MGX full-stack template (so much of the structure is convention-driven scaffolding — see "Code generation conventions"), it has since been **decoupled from atoms.dev/MGX and made standalone** (local auth, no external identity provider, runs on your own server — see `RUN.md`).

The product has a **three-tier tenancy hierarchy**: **master** (platform owner) → **agent** (white-label reseller, sets branding, owns client slots) → **client** (the merchant running a POS terminal). A user's tier is **not stored in the JWT** — it is derived at request time from DB membership (see `backend/routers/tenant.py::get_user_role`): the seeded admin account is **master**, a user linked to an `Agents` row is **agent**, a `Clients` row makes them **client**, and any other account defaults to least-privilege **client**.

- `backend/` — FastAPI + SQLAlchemy (async) API
- `frontend/` — Vite + React + TypeScript + shadcn/ui

## Commands

### Frontend (`frontend/`, package manager is **pnpm**)
```shell
pnpm i           # install
pnpm run dev     # Vite dev server (default port 3000)
pnpm run build   # production build to dist/
pnpm run lint    # eslint --quiet ./src
pnpm run preview # preview built output
```

### Backend (`backend/`)
```shell
pip install -r requirements.txt
cp .env.example .env   # set JWT_SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD, DATABASE_URL
python main.py         # runs uvicorn on settings.port (default 8000)
```
`DATABASE_URL` defaults to `sqlite:///./app.db` (auto-rewritten to `sqlite+aiosqlite://`); use Postgres for production. On startup the app creates all tables, seeds empty tables from `backend/mock_data/*.json`, and seeds the **master/admin** account from `ADMIN_EMAIL`/`ADMIN_PASSWORD`. Full run instructions: `RUN.md`.

### Tests
`pytest` + `pytest-asyncio` + `httpx` are declared in `requirements.txt`, but there is **no test suite or config in the repo yet**. There is no committed `alembic` migration history despite `alembic/` existing — schema is created/patched at runtime, not via migrations.

### Full-stack launch
`start_app_v2.sh` is the orchestration script used by the MGX platform: it auto-assigns a free backend/frontend port pair (starting 8000/3000), rewrites `$$BACKEND_DOMAIN$$`/`$$FRONTEND_DOMAIN$$` placeholders in env files, and waits on `/health`. It's a bash script — on this Windows box, run backend and frontend manually as above instead.

## Backend architecture

### Router auto-discovery
`main.py::include_routers_from_package` walks the `routers` package at startup and includes **every** module-level `router` or `admin_router` (`APIRouter` instance, or list of them). **To add an endpoint group, just drop a module in `routers/` exposing `router` — no manual registration.** The `MODULE_*` comment markers in `main.py` and `lambda_handler.py` are template injection points; preserve them.

### The per-entity triad (the dominant pattern)
Most domain objects follow an identical three-file shape — `routers/<entity>.py`, `services/<entity>.py`, `models/<entity>.py` (e.g. products, customers, expenses, discounts, categories, suppliers, staff_members, transactions, agents, clients, …). The generated CRUD router:
- mounts at `prefix="/api/v1/entities/<entity>"`,
- defines local Pydantic `…Data` / `…UpdateData` / `…Response` / batch schemas inline,
- exposes list / get / create / update / delete **plus** `/batch` create/update/delete and an unauthenticated `/all`,
- scopes every operation to the caller via `user_id=str(current_user.id)` — **ownership is enforced in the service layer**, where `get_by_id`/`update`/`delete` filter on `user_id`. The matching `…/all` route deliberately omits the auth dependency and the user filter.

When editing one entity, the same change usually applies across all of them — they are near-identical copies. `models/base.py::BaseModel` provides `id`/`created_at`/`updated_at`, but note many generated models (e.g. `models/products.py`) redeclare these columns directly and use `extend_existing=True` rather than inheriting `BaseModel`.

### Hand-written routers (not the generic triad)
These carry the real business logic and diverge from the CRUD template — read them before assuming behavior:
- `routers/tenant.py` — role detection + master/agent/client dashboards, agent branding, client provisioning against package slots.
- `routers/pos.py` — transaction creation, inventory deduction.
- `routers/auth.py` + `core/auth.py` + `core/security.py` — **local email/password auth**: `POST /register`, `POST /login` (issues an HS256 JWT), `GET /me`, `POST /logout`. Passwords are bcrypt-hashed (`core/security.py`); `services/auth.py` seeds the master account on startup. `dependencies/auth.py` (`get_current_user`, `get_admin_user`) is the auth gate used everywhere.
- `routers/aihub.py` (OpenAI), `routers/storage.py`, `routers/payment.py`/`services/payment.py` (Stripe).

### Config & secrets
`core/config.py::Settings` reads from env. Its `__getattr__` override means **any** `settings.foo` transparently resolves to env var `FOO` even if not declared on the class. Key explicit fields: `database_url`, `jwt_secret_key`/`jwt_algorithm`/`jwt_expire_minutes`, `admin_email`/`admin_password`/`admin_name` (master seed), `allow_registration`. `ENVIRONMENT=dev` makes the global exception handler return full tracebacks.

### Database manager (`core/database.py`)
Single `db_manager` singleton with lazy init (important for Lambda, where the lifespan may not fire — `get_db` self-initializes). Normalizes sync DB URLs to async drivers, strips asyncpg-incompatible params (e.g. Neon's `channel_binding`), uses `NullPool` under Lambda and a `QueuePool` otherwise. Contains a runtime "repair" routine that `ALTER TABLE ADD COLUMN`s missing fields — currently disabled in `create_tables`.

### Deployment
Runs as a standalone uvicorn process (`python main.py`) plus a statically-served frontend build — see `RUN.md`. The former atoms.dev AWS Lambda handler and bash launcher have been removed.

## Frontend architecture

- **API access goes through a local SDK shim, `src/lib/atomsClient.ts`** (a drop-in replacement for the removed `@metagptx/web-sdk`). `src/lib/api.ts` wraps everything via `client.apiCall.invoke({url, method, data})` for custom endpoints and `client.entities.<name>.query/queryAll/create/update/delete` for generic entity CRUD. The shim reads the JWT from `localStorage` (key `pos_auth_token`) and attaches it as a Bearer token. New backend endpoints should get a typed wrapper in `api.ts`.
- `src/lib/config.ts` resolves `API_BASE_URL` at runtime: fetch `/api/config` first (Lambda), then `VITE_API_BASE_URL`, then `http://127.0.0.1:8000`. Don't hardcode the base URL.
- **Routing is role-gated.** `src/App.tsx` groups routes under `<ProtectedRoute allowedRoles={[...]}>` for `master` / `agent` / `client`. When adding a page, place its route in the correct role group and add the page under `src/pages/`.
- `src/contexts/AuthContext.tsx` owns auth state via `authApi` (`src/lib/auth.ts`); `useAuth()` exposes `user`, `login(email, password)`, `register(...)`, `logout`. It fetches the tenancy role (`/tenant/role`) after login and stores it as `user.role` so `ProtectedRoute` (master/agent/client) routes correctly. `App.tsx` wraps routes in `<AuthProvider>`. The login form is `src/pages/Index.tsx` (route `/login`).
- **i18n** lives in `src/lib/i18n.ts` as an in-file translation map (`Language = 'ar' | 'en' | 'hi' | 'ur'`) — add keys to every language object. Arabic implies RTL; check layout.
- shadcn/ui components are pre-generated under `@/components/ui` (alias `@/` → `src/`). React Query is the data-fetching/caching layer.
- **Do not edit `index.html`** — title/description/logo use `%VITE_*%` placeholders substituted at deploy time.

## Code generation conventions

- `backend/data_models/*.json` are the entity schema definitions the MGX platform uses to (re)generate the router/service/model triads; `backend/mock_data/*.json` are seed rows loaded into empty tables on startup. They are largely parallel sets.
- Generated CRUD code is intentionally repetitive and verbose (broad try/except, debug logging on every handler). Match the surrounding style when extending it rather than refactoring a single entity to look different from its siblings.
- `.mgx/config.yaml` (root and `frontend/`) is platform metadata.
