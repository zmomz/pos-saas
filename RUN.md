# Running the POS standalone

This app no longer depends on atoms.dev. It is a plain FastAPI backend + a Vite/React
frontend that you can run on any server.

## 1. Backend

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/mac: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then edit .env
```

Edit `backend/.env` and set at least:

- `JWT_SECRET_KEY` — a long random string.
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — the initial **master** account, created on first startup.
- `DATABASE_URL` — `sqlite:///./app.db` works for a single server; use Postgres for production
  (`postgresql://user:pass@host:5432/dbname`).

Start the API:

```bash
python main.py            # serves on http://0.0.0.0:8000
# or: uvicorn main:app --host 0.0.0.0 --port 8000
```

On first run it creates the database tables, seeds mock data into empty tables, and seeds
the master account from `ADMIN_EMAIL`/`ADMIN_PASSWORD`.

## 2. Frontend

```bash
cd frontend
pnpm install              # or: npm install
cp .env.example .env      # set VITE_API_BASE_URL to your backend URL
```

Development (with hot reload; Vite proxies `/api` to the backend on port 8000):

```bash
pnpm run dev              # http://localhost:3000
```

Production build (static files in `frontend/dist/`):

```bash
pnpm run build
```

Serve `frontend/dist/` with any static host (nginx, Caddy, `pnpm run preview`, etc.) and
point `VITE_API_BASE_URL` at the backend before building, or terminate `/api` to the backend
via your reverse proxy.

## 3. Logging in

- Open the site and go to `/login`.
- Sign in with the `ADMIN_EMAIL` / `ADMIN_PASSWORD` you configured → you land on the master dashboard.
- New self-service accounts can be created at `/login` (Register) while `ALLOW_REGISTRATION=true`.
  Set `ALLOW_REGISTRATION=false` in production once your accounts exist.

## Authentication model

Auth is local **email + password**. The backend issues a JWT (`POST /api/v1/auth/login`),
the frontend stores it in `localStorage` and sends it as `Authorization: Bearer <token>`.
There is no external identity provider.

Tenancy roles are derived per request:
- the seeded admin account → **master**;
- a user linked to an `agents` row → **agent**;
- a user linked to a `clients` row → **client**;
- any other account → least-privilege **client**.

> Note: agent/client *login accounts* are not yet auto-created by the provisioning endpoints
> (those create the tenant data rows only). To give an agent/client a login today, create the
> account via registration and link it, or extend the tenant provisioning to also create a `User`.

## Production hardening (Phase 3)

These knobs are read from the environment. Sensible, safe defaults apply when unset.

| Env var | Default | Purpose |
|---------|---------|---------|
| `RATE_LIMIT_ENABLED` | `false` | Turn on the per-user/IP token-bucket rate limiter (429 + `Retry-After` when drained). |
| `MAX_BODY_SIZE_MB` | `10` | Reject request bodies larger than this with `413`. |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_USE_TLS` | — | Real email transport. With no `SMTP_HOST`, email **falls back to logging** (dev mode) and never blocks the request. |
| `SENTRY_DSN` / `SENTRY_TRACES_SAMPLE_RATE` | — | Backend error tracking. No-op unless `sentry-sdk` is installed **and** a DSN is set. |
| `RUN_MIGRATIONS_ON_BOOT` | `false` | Run `alembic upgrade head` at startup before `create_all`. Enable in production to use the migration history; dev/CI keep `create_all`. |
| `API_METERING_ENABLED` | `false` | Write an `api_usage` row per authenticated API call so `GET /api/v1/production/api-usage/stats` reflects real traffic. |
| `LOG_FORMAT` / `LOG_LEVEL` | `text` / `INFO` | Set `LOG_FORMAT=json` for structured one-line-JSON logs (correlation IDs) suited to log aggregators. |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM` | — | SMS receipts (`POST /pos/transactions/{id}/sms`, feature-gated by `sms_receipts`). Without them, SMS **falls back to logging**. |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | — | Subscription charges via the agent's Stripe Connect account (`agents.stripe_account_id`). With no key, payment is recorded as `manual`. The billing webhook (`POST /api/v1/tenant/billing/webhook`) auto-suspends a client on `*.payment_failed`; signature is verified when `STRIPE_WEBHOOK_SECRET` is set. |
| `VITE_SENTRY_DSN` / `VITE_SENTRY_TRACES_SAMPLE_RATE` | — | **Frontend** error tracking (build-time). No-op when unset. |

**Sessions / logout.** JWTs now carry a `jti` and `POST /api/v1/auth/logout` blocklists it
server-side (table `revoked_tokens`), so a logged-out token is rejected before it expires.
Pass the refresh token in the logout body to revoke it too. Prune expired rows periodically
(their `expires_at` is past the JWT `exp`, so they would be rejected on `exp` regardless).

**Permissions.** `dependencies/permissions.py::require_permission("<key>")` gates a route.
Policy is **grant-by-default, explicit deny wins**; the platform master bypasses all gates.
Write a `permissions` row with `is_granted = false` to revoke a capability (e.g. `pos.refund`)
from a sub-account; the frontend reads `GET /api/v1/auth/me/permissions` to hide/disable it.

**Webhooks.** Registered `webhooks` rows are POSTed real, HMAC-SHA256-signed payloads
(`X-Webhook-Signature: sha256=…`) with retry-on-5xx, fired out-of-band on `sale.completed`
and `refund.created`. A failing endpoint never affects the originating sale/refund.

### Backups & restore (Postgres)

Run regular logical backups and verify restores:

```bash
# Nightly dump (cron): keep N days of compressed snapshots.
pg_dump "$DATABASE_URL" -Fc -f "/backups/pos_$(date +%F).dump"

# Restore into a fresh database:
createdb pos_restore
pg_restore --clean --if-exists -d "postgresql://user:pass@host:5432/pos_restore" /backups/pos_YYYY-MM-DD.dump
```

For SQLite (single-server/dev) snapshot the file with the app stopped, or use
`sqlite3 app.db ".backup '/backups/app_$(date +%F).db'"` for an online copy.
Signed ZATCA documents must be retained for `ZATCA_RETENTION_YEARS` (default 6) — ensure
backups cover the `zatca_documents` table for that period.

**Migrations.** With `RUN_MIGRATIONS_ON_BOOT=true` the app runs `alembic upgrade head`
at startup. The head revision `e4f5a6b7c8d9_sync_models_baseline` reconciles the hand-written
chain with the current ORM models (Phases 2–6 columns/tables); a CI check asserts the
autogenerate diff is empty. Generate new migrations with `alembic revision --autogenerate`.

### Testing

```bash
# Backend (135 tests)
cd backend && python -m pytest -q

# Frontend unit (Vitest + RTL + MSW) and E2E (Playwright smoke)
cd frontend && pnpm test          # vitest run
cd frontend && pnpm build && pnpm test:e2e
```

CI (`.github/workflows/ci.yml`) runs all three on every push/PR to `main`.

### Deferrals — closed

The Phase 0–6 deferrals (frontend test harness + CI, deep `get_tenant_scope`, Alembic
migrations-on-boot, Twilio SMS, API-usage metering, audit diffs + failed-auth logging,
structured JSON logging, Stripe Connect subscription charge + auto-suspend webhook, the
per-branch stock ledger, the Arabic-glyph PDF, frontend Sentry, the shared `LanguageProvider`,
the locale-aware date helper, the SAR sweep, POS loyalty/branch/camera controls, the
first-login language step, and PO-receiving) are **all implemented and tested** — see the
"DEFERRALS CLOSEOUT" entry in `ACTION_PLAN.md`. **Phase 7 (native mobile)** remains a
separate track; the recommendation is to ship the existing responsive PWA as the mobile
answer and schedule a native app as a follow-on.
