# F-057 — KDS / KOT + real-time kitchen channel

## Parent

`docs/prd/PRD-RST-restaurant-vertical.md` — Restaurant Vertical (RST core). Source finding F-057.

## What to build

Give the kitchen eyes. A menu manager defines **prep-stations** (e.g. Grill, Bar, Cold). When a server fires a course (F-055), the fired items **route to the station that prepares them** and materialize on a **Kitchen Display (KDS)** — one column per prep-station — updating in **near-real-time (≤1s target, SRS §5.1)**. A cook can **bump** (complete) a ticket to clear it from the active board and **recall** a mistaken bump. The board shows **ticket timers and all-day counts**. Fired/bumped state stays consistent between the server's screen and the KDS so front and back of house agree.

For stations without a screen, an **80mm Arabic KOT** prints per station — modifiers grouped by course, **no prices**.

**Real-time transport is the implementer's call** (this slice is AFK): choose **WebSocket or SSE deliberately** to meet the ≤1s update target. This is the one seam in the vertical with no existing prior art in the repo — pick the simpler option that hits the target and document the choice in the PR.

Backend: new `prep_stations` triad (`name`, `name_ar`) and `kds_tickets` (materialized fired items routed to a station, status `active`/`bumped`, timestamps for timers), owner-scoped, behind the restaurant double-gate. Routes: `GET /kds/tickets` (real-time stream — WS or SSE), `POST /kds/{id}/bump`, `POST /kds/{id}/recall`. Wire the F-055 `fire` action to create KDS tickets per station.

Frontend: `KDS.tsx` — a column-per-station board with timers and all-day counts; new client-role-gated route in `App.tsx`. Typed `api.ts` wrappers; i18n ×4 (fire/bump/recall, station names) with RTL.

## Acceptance criteria

- [ ] A manager can define prep-stations with bilingual names.
- [ ] Firing a course creates a KDS ticket per relevant prep-station and routes items to the correct station column.
- [ ] Fired items appear on the KDS within ~1s via the chosen real-time transport (WS or SSE; choice documented).
- [ ] Bump moves a ticket off the active board; recall restores a bumped ticket.
- [ ] The board shows per-ticket timers and all-day counts; server screen and KDS stay consistent on fired/bumped state.
- [ ] An 80mm always-Arabic KOT prints per station with modifiers grouped by course and no prices.
- [ ] KDS entities/routes are owner-scoped (SEC-02) and behind the restaurant double-gate.
- [ ] Tests added and green: `test_fire_creates_kds_ticket_per_station`, `test_bump_then_recall`, and a KOT-render snapshot test.
- [ ] `KDS.tsx` renders loading / empty / error / permission / offline states; brand tokens; RTL verified.
- [ ] Full existing `backend/tests` suite stays green.

## Blocked by

- `01-F055-order-ticket-line-items.md` (KDS materializes the fired items / fire action from F-055).
