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
