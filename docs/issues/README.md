# Issue Tracker — Platform Remediation

File-based issue store for [PRD — Platform Remediation](../prd/PRD-AUDIT-platform-remediation.md) (source: `docs/UNIT_AUDIT.md`).
104 tracer-bullet issues, all `ready-for-agent`, published in dependency order. `AFK` = agent can complete & merge unattended; `HITL` = needs a human decision/review.

> **Recommended grab order:** dependency-free Sprint-1 issues first (the subtractive security purge + tenancy fixes eliminate the most high/critical findings per unit of effort). Do not start with the solid units (ISSUE-102/103/104 are minor touches to them).

## Sprint 1 — Security & compliance
| # | Title | Type | Blocked by |
|---|---|---|---|
| 001 | Delete `packages` scaffold | AFK | — |
| 002 | Delete `agents`/`agent_features` scaffolds | AFK | — |
| 003 | Delete `permissions` scaffold | AFK | — |
| 004 | Delete `clients`/`client_features` scaffolds (incl `/all`) | AFK | — |
| 005 | Delete `entities/shifts` scaffold | AFK | — |
| 006 | `audit_logs` read-only | AFK | — |
| 007 | `api_usage` read-only | AFK | — |
| 008 | Remove dead generator artifacts | AFK | 001–004 |
| 009 | Explicit router allowlist | AFK | 001–008 |
| 010 | Tenancy: PO-receive owner scope | AFK | — |
| 011 | Tenancy: payments-gateway owner scope | AFK | — |
| 012 | Tenancy: audit/api-usage owner scope + tag rows | AFK | 006, 007 |
| 013 | Tenancy: `require_feature` owner scope | AFK | — |
| 014 | ZATCA: per-client PIH (kill singleton) | AFK | — |
| 015 | ZATCA: valid signed UBL (XAdES+C14N+UUID) | AFK | 014 |
| 016 | ZATCA: gate submission until valid | AFK | 015 |
| 017 | ZATCA: Fatoora sandbox verification | HITL | 015, 016 |
| 018 | ZATCA: onboarding wizard | AFK | — |
| 019 | Append-only / tamper-evident audit log | AFK | 006 |

## Sprint 2 — Make visible features work
| # | Title | Type | Blocked by |
|---|---|---|---|
| 020 | Stop swallowing errors on façade pages | AFK | — |
| 021 | ProductManagement reads `items` | AFK | — |
| 022 | ExpenseTracking reads `items`/`total_amount` | AFK | — |
| 023 | AgentDashboard `remaining_slots` | AFK | — |
| 024 | MasterDashboard price field | AFK | — |
| 025 | DiscountManagement `usage_count` | AFK | — |
| 026 | Typed API return signatures | AFK | 021–025 |
| 027 | AuditLog reads real fields | AFK | 012 |
| 028 | Loyalty admin: 4 endpoints + UI | AFK | 020 |
| 029 | Webhook delivery logs | AFK | 020 |
| 030 | Storage work-or-delete | HITL | 020 |
| 031 | Hold/recall variant_id + open price | AFK | — |
| 032 | Combo component deduction at settle | AFK | — |

## Sprint 3 — Close core merchant workflows
| # | Title | Type | Blocked by |
|---|---|---|---|
| 033 | Staff login provisioning | AFK | — |
| 034 | Role→permission default map | AFK | 033 |
| 035 | Permission-management UI | AFK | 034 |
| 036 | PO create real schema | AFK | — |
| 037 | PO receive into branch + partial | AFK | 036, 010 |
| 038 | Product↔category linkage | AFK | — |
| 039 | BOM recipe editor | AFK | — |
| 040 | Modifier-group attach UI | AFK | — |
| 041 | Auth: silent refresh | AFK | — |
| 042 | Auth: single logout | AFK | — |
| 043 | Login brute-force protection | AFK | — |
| 044 | Loyalty ledger + expiry | AFK | 028 |

## Sprint 4 — Parity & polish
| # | Title | Type | Blocked by |
|---|---|---|---|
| 045 | Receipt-template fields → renderer | AFK | — |
| 046 | 58mm paper support | AFK | 045 |
| 047 | Saved printer + per-station routing | AFK | — |
| 048 | Receipt-template designer UI | AFK | 045 |
| 049 | Devices settings (register/list terminals) | AFK | 011 |
| 050 | Checkout terminal picker | AFK | 049 |
| 051 | Webhook event emission completeness | AFK | 029 |
| 052 | Billing scheduler | AFK | — |
| 053 | Billing proration | AFK | — |
| 054 | Coupons / trials | AFK | — |
| 055 | Commission statements | AFK | — |
| 056 | Quote→sale conversion | AFK | — |
| 057 | Gift-card void/reload + refund-to-card | AFK | — |
| 058 | Advanced discounts | AFK | — |
| 059 | Unique discount codes | AFK | — |
| 060 | Stock-transfer history | AFK | — |
| 061 | Two-phase transfer | AFK | 060 |
| 062 | Branch `is_main` UI | AFK | — |
| 063 | Supplier VAT number | AFK | — |
| 064 | Catalog CSV import/export | AFK | — |
| 065 | Product images | AFK | 030 |
| 066 | Retail modifiers/combos | AFK | 032, 040 |
| 067 | Per-branch variant stock | AFK | — |
| 068 | Soft-delete products | AFK | — |
| 069 | Reservations / waitlist | AFK | — |
| 070 | Per-seat / partial settlement | AFK | — |
| 071 | In-app thermal print | AFK | 045 |
| 072 | Tip entry on settle | AFK | — |
| 073 | KDS bumped-card / undo | AFK | — |
| 074 | Cash-drawer change-due helper | AFK | — |
| 075 | Reprint past receipts | AFK | 045 |
| 076 | Price / stock check | AFK | — |
| 077 | Notification delivery honoring prefs | AFK | 078 |
| 078 | Persisted per-user profile | AFK | — |
| 079 | Merchant store-settings screen | AFK | — |
| 080 | Object storage / exports | AFK | 030 |
| 081 | MFA | AFK | — |
| 082 | Password reset / forgot | AFK | — |
| 083 | Active-session management | AFK | 042 |
| 084 | Password complexity policy | AFK | — |
| 085 | Re-skin: PackageManagement | HITL | — |
| 086 | Re-skin: BrandingEditor | HITL | — |
| 087 | Re-skin: SupplierManagement | HITL | — |
| 088 | Re-skin: DiscountManagement | HITL | — |
| 089 | Re-skin: AuditLog | HITL | 027 |
| 090 | Re-skin: WebhookManagement | HITL | — |
| 091 | Re-skin: CustomerDisplay | HITL | — |
| 092 | Re-skin: Shift/StaffManagement | HITL | — |
| 093 | Re-skin: auth gate screens | HITL | — |
| 094 | Remove LogoutCallbackPage | AFK | — |
| 095 | Rename atomsClient→apiClient + drop shims | AFK | 041, 042 |
| 096 | Remove dead refreshAccessToken residue | AFK | 041 |
| 097 | UserProfile change-password block | AFK | — |
| 098 | Remove storage residue + settingsApi orphan | AFK | 030 |
| 099 | Register PerformanceMiddleware | AFK | — |
| 100 | Remove duplicate CORS placeholder | AFK | — |
| 101 | Fix sw.js manifest reference | AFK | — |
| 102 | Refund UI shows SAR | AFK | — |
| 103 | Assign `bill_printed` table state | AFK | — |
| 104 | Fix deplete-stock double-deduct | AFK | 032 |
