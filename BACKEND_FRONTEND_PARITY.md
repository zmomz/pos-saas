# Backend ↔ Frontend Parity Audit

_Date: 2026-06-28 · Branch: `main`_

## Question

Is everything in the backend reflected, and in the correct place, in the frontend?

## Method

1. Extracted **every** registered backend route by parsing `backend/routers/*.py`
   (router `prefix` + `@router.<method>(...)` decorators, including multi-line
   decorators). **Total: 433 routes.**
2. Extracted every `/api/v1/...` path the frontend references across
   `frontend/src/**/*.{ts,tsx}` (excluding test files), normalising path params
   and query strings.
3. Diffed the two sets, treating the generic `entities/${name}` client as
   covering the standard list/all/get/create/update/delete/batch CRUD for every
   entity router.
4. **Manually verified each candidate gap** case-insensitively and against named
   API wrapper functions in `lib/api.ts` / `lib/auth.ts`, because a literal
   URL-string grep misses dynamically-built paths and wrapper functions.

> ⚠️ Verification mattered: a first pass wrongly flagged "POS loyalty" as a gap
> because of a case-sensitive grep. It is in fact wired (see false-positives).
> Every finding below was re-checked.

## Headline

**The large majority of the backend is reflected and sensibly placed.** Of 433
routes, 378 are consumed. Of the 55 with no literal frontend reference, ~24 are
_correctly_ absent (inbound webhooks, dynamically-built auth paths, redundant
endpoints). That leaves **15 genuine gap areas** — all of them **missing UI**,
not wrong-path bugs. **Every frontend call targets a real backend endpoint.**

The big subsystems are all wired and correctly located: entity CRUD, POS
sale/refund/void/hold/loyalty, restaurant tickets/KDS/tables/settle/split,
reports, ZATCA onboarding, gift cards, promotions, printers, store settings,
and the tenant/agent/master billing dashboards.

---

## Confirmed gaps (backend capability with no functional frontend surface)

### A. Security / account — highest value

| # | Backend endpoint(s) | Status | Notes |
|---|---|---|---|
| 1 | `POST /auth/mfa/enroll`, `/auth/mfa/activate`, `GET /auth/mfa/status`, `POST /auth/login/mfa` | **Gap** | No MFA setup or challenge UI. An `input-otp.tsx` shadcn primitive exists but is **never imported** by any page. |
| 2 | `GET /auth/sessions`, `DELETE /auth/sessions/{id}`, `DELETE /auth/sessions/others` | **Gap** | No active-session management UI (view / revoke devices). |
| 3 | `POST /auth/password/forgot`, `POST /auth/password/reset` | **Gap** | No self-service "forgot password" flow. Only forced-reset (`/force-reset` → change-password) and agent-initiated client reset exist. |
| 4 | `GET/PUT /users/profile` | **Gap** | `UserProfile.tsx` only calls `users/preferences` + `users/change-password`. Profile name/email/phone editing is not wired. |

### B. Operational features

| # | Backend endpoint(s) | Status | Notes |
|---|---|---|---|
| 5 | `GET/PUT /pos/branches/{id}/variant-stock` | **Gap** | Per-branch **variant** stock cannot be viewed/edited. Parent-product branch stock (`/stock`) is wired; variants are not. |
| 6 | `POST /pos/transactions/{id}/sms` | **Gap** | Only `emailReceipt` (`/email`) is wired. Notable: `sms_receipts` is a **sellable feature flag** (PackageManagement), so the flag exists but the action does not. |
| 7 | `PUT/DELETE /restaurant/zones/{id}` | **Gap** | `FloorMap.tsx` only imports `getFloorZones` + `createFloorZone`. Zones can be created/listed but not renamed/deleted. (Tables, by contrast, have full CRUD.) |
| 8 | `POST /production/notifications/send` | **Gap** | `Notifications.tsx` lists + marks-read only; no compose/send UI. |

### C. Admin / observability — likely intentional, but unsurfaced

| # | Backend endpoint(s) | Status | Notes |
|---|---|---|---|
| 9 | `/storage/*` (list-buckets, list/get/upload/download/rename/delete-object, create-bucket) | **Unused** | No file-manager UI at all. Product images go through `/products/{id}/image` instead. |
| 10 | `GET /production/metrics`, `/production/health/detailed`, `/production/search`, `/production/api-usage/stats` | **Unused** | Observability/global-search endpoints not surfaced. |
| 11 | `/production/permissions/grant`, `/revoke`, `/check`, `/list` | **Unused** | RBAC admin endpoints unused; the FE uses `/production/staff-permissions/{id}` instead (partial overlap). |
| 12 | `POST /production/bulk/import`, `/bulk/export`, `/production/invoice/pdf` | **Unused** | Generic bulk endpoints unused; specific `products/import` + `products/export` are wired. |
| 13 | `POST /zatca/invoices/{id}/sign`, `/zatca/invoices/{id}/report`, `GET /zatca/integrity` | **Backend-only** | Per-invoice manual sign/report and the hash-chain integrity check have no UI. Auto-signing at sale + bulk `report-pending` (which **is** wired in `ZatcaStatus.tsx`) cover the normal flow; the integrity audit is the real omission. |
| 14 | `GET /payments/tender-types`, `POST /payments/charge` | **Unused** | POS uses a static tender list + `/payments/terminal/charge` / Moyasar. |
| 15 | `GET /printers/resolve` | **Unused** | Internal print-routing helper; FE resolves routing via `/restaurant/order-tickets/{id}/print-routing`. |

---

## False positives (looked missing, verified present or correctly absent)

| Item | Resolution |
|---|---|
| **POS loyalty earn/redeem** (`/production/loyalty/earn`,`/redeem`) | ✅ Wired. `POSTerminal.tsx` selects a customer and sends `redeem_points` in the `/pos/transaction` payload (line ~859); earn/redeem happen server-side in the sale. |
| **Registration** (`/auth/register`) | ✅ Wired. `Index.tsx` calls `auth.register()`. |
| **Login / refresh / logout** (`/auth/refresh`, `/auth/logout`) | ✅ Wired in `lib/auth.ts` / `lib/apiClient.ts` (built dynamically). |
| **Z-report** (`/reports/zreport`, `/zreport/document`) | ✅ Wired via query-string variants in `lib/api.ts`. |
| **CSV download** (`/reports/export-csv/download`) | ✅ Wired (query variant). |
| **Restaurant tables edit/delete** (`/restaurant/tables/{id}`) | ✅ Wired (full CRUD). |
| **KDS all-day count** (`/restaurant/all-day-count`) | ✅ Feature present — `KDS.tsx` shows the count, computed **client-side** from the board. Backend endpoint is redundant, not a user-facing gap. |
| **Inbound webhooks** (`aggregator/{provider}/webhook`, `salla/webhook`, `billing/webhook/agent/{id}`, `quota/webhook`) | ✅ Correctly **not** called from the UI (server-to-server, Moyasar/Salla → backend). |
| **Session validate/refresh** (`/production/session/refresh`, `/validate`) | ✅ Redundant — `apiClient` uses `/auth/refresh`. |

---

## Recommendations (suggested priority)

1. **Wire SMS receipts (#6)** — a feature flag is already sold to clients but the
   action is missing; this is the most user-visible inconsistency.
2. **Self-service forgot-password (#3)** and **MFA UI (#1)** — security expectations
   for a SaaS POS; backend is ready.
3. **Active session management (#2)** and **profile editing (#4)** — small, backend
   is ready.
4. **Variant branch stock (#5)** and **zone edit/delete (#7)** — complete the
   existing screens.
5. **Notifications send (#8)** — finish the Notifications page.
6. Items #9–#15 are admin/observability/internal — confirm whether they are
   intentionally backend-only before building UI.

## Caveats

This is a **path-coverage** audit (does the FE reach each endpoint, in a plausible
page). It does **not** exhaustively verify request/response **payload shapes** or
**role-gating** for all 378 wired routes. Spot checks were clean, but a deeper
per-subsystem audit would be needed to certify those dimensions.
