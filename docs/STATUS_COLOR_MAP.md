# Status → Token Colour Map

**One source of truth for what each semantic colour *means* and which business
status maps to it.** Reach for this before inventing a new status pill or tinting
a badge by hand. Closes Phase 6 of [`plan.md`](../plan.md).

The tokens themselves live in two places (don't redefine them anywhere else):

- **Palette** — `frontend/tailwind.config.ts` (`success` / `warning` / `danger` /
  `violet` / `sky` + `brand` / `gold` scales). The three that back solid action
  buttons (`success` / `warning` / `danger`) carry an explicit `foreground` tuned
  for contrast — gold `warning` uses dark ink (`#3a2c10`), never white.
- **Pills / swatches** — `frontend/src/index.css` (`.pill-*`, `.dxr-sw-*`,
  `.dxr-delta-*`). A status badge is always a `.pill-*` class, never a raw
  `bg-*/10 text-*` triple.

---

## What each colour means

Map a domain status to a **meaning** first, then use the colour for that meaning.
Don't pick a colour because it "looks like" the word.

| Colour | Token | Meaning — when to use | Example statuses |
|---|---|---|---|
| **success** | `success` `#23a06b` (green) | A good / healthy / completed-positively steady or terminal state. "On, fine, done, paid." | active, healthy, operational, paid, reported, cleared, accepted, converted, balanced, earned, free (table), consent given, success log, positive variance |
| **warning** | `warning` `#d6a33a` (gold) | In-progress / transitional / needs-attention-soon. "Mid-flow, pending, watch this." | pending, fired (KDS), received (channel), occupied (table), refund, pay-out, required, low-but-present stock |
| **danger** | `danger` `#d14a3a` (red) | A bad / failed / blocked / offline state, **or** a destructive flag. "Wrong, stopped in error, gone." | failed, void, rejected, expired (quote), unmet, suspended, error log, out-of-stock, inactive (operational — see below) |
| **sky** | `sky` `#3d9ad1` (blue) | Neutral **informational** data — not a health signal. "Here's a fact." | payment method, document signed, sent (quote), type/category info labels |
| **muted** | `muted-foreground` (grey) | Neutral **idle / dormant / lifecycle** state with no health connotation. "Parked, not yet started, by choice." | draft, redeemed, cancelled, no-show, unknown, open (ticket), inactive (catalog — see below), role/tier labels, secondary rank |
| **violet** | `violet` `#7b57c9` | Categorical accent for *grouping*, not status. Use sparingly. | non-status segment tags |

`pill-gold` / `dxr-sw-gold` is **emphasis, not status** — premium / VIP / top
rank / highlight (white-label active, `#1`, "most popular"). Never use it to mean
"good"; that's `success`.

---

## The one ambiguous case: `active` / `inactive`

`active` is always **success**. `inactive` splits by stakes:

- **Operational on/off** — an agent, branch, webhook, loyalty config, or device.
  Off means *offline / needs attention* → **danger**.
  (AgentDashboard, MasterDashboard, BranchManagement, LoyaltyProgram,
  WebhookManagement, DevicesSettings.)
- **Catalogue / roster flag** — a product or staff member toggled out of rotation.
  Off is *parked, not broken* → **muted**.
  (ProductManagement, StaffManagement.)

So `WebhookManagement` rendering an inactive webhook as `pill-danger` is **correct**
under this rule (it's an operational integration), superseding the earlier
"should be muted" note in `plan.md`.

---

## Tiles have no `danger` tone — by design

`StatTile`'s `TileTone` is `brand | success | violet | sky | gold | warning`
(`components/dashboard/StatTile.tsx`). There is deliberately **no `danger` tile
tone**: KPI tiles summarise, they don't alarm. So an error status shows up as a
`warning`-toned tile **and** a `pill-danger` badge on the same page — e.g.
`ZatcaStatus` `failed` (`STATUS_TONE.failed = 'warning'`, `STATUS_BADGE.failed =
'pill-danger'`). That mismatch is intentional, not drift — don't "fix" it by
forcing a red tile.

---

## Canonical per-domain status maps (already in code)

These page-level maps already follow the table above; copy their shape for new
status sets rather than hand-rolling per-row ternaries:

| Domain | Map | File |
|---|---|---|
| Quotation lifecycle | draft→muted, sent→sky, accepted/converted→success, rejected/expired→danger | `QuotationManagement.tsx` |
| ZATCA document | signed→sky, reported/cleared→success, pending→warning, failed→danger, unknown→muted | `ZatcaStatus.tsx` |
| Gift card | active→success, redeemed→muted, expired→warning, void→danger | `GiftCardManagement.tsx` |
| Channel order | imported/fulfilled→success, received→warning | `ChannelOrders.tsx` |
| KDS ticket | open→muted, fired→warning, bumped→success | `OrderTicket.tsx` |
| Reservation | booked/confirmed→sky, seated→success, cancelled/no_show→muted | `Reservations.tsx` |
| Floor table | free→success, occupied→warning | `FloorMap.tsx` |
| Audit action | delete/auth-failure→danger, create/login→success, update→warning, else→muted | `AuditLog.tsx` |

> Note: `expired` is `warning` for a gift card (recoverable / reissue) but `danger`
> for a quotation (dead). The colour follows the *consequence*, not the word — see
> "What each colour means" above.

---

## Adding a new status

1. Decide the **meaning** (steady-good / transitional / bad / info / idle).
2. Pick the colour from the table — never a raw Tailwind colour
   (`emerald`/`amber`/`rose`/`slate` are banned; they don't theme).
3. Render it as a `STATUS_PILL` record + `pill-*` class, with `|| 'pill-muted'`
   as the fallback for unknown values.
4. If it's a solid action button instead of a badge, use the matching `Button`
   variant (`success` / `warning` / `danger` / `outline-danger`) — those already
   carry the contrast-safe foreground.
