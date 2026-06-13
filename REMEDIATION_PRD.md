# Remediation PRD — Ralph file-mode checklist

> Generated from `docs/prd/PRD-AUDIT-platform-remediation.md` and the 104 issues in `docs/issues/`.
> This is the **ralph `--from-file` task list**. Source of truth for detail is each issue file (path on every line).
>
> Run: `python ralph.py <N> --from-file --prd REMEDIATION_PRD.md --allow "Bash(git:*)" "Bash(python -m pytest:*)" "Bash(npx tsc:*)" "Bash(npm:*)"`
> (or `--yolo` / `--sandbox` for fully unattended). One task per iteration.

## Loop rules (read every iteration)
1. Work tasks under **## Tasks** ONLY, strictly **top-to-bottom** — they are dependency-ordered, so the first unchecked task is the next eligible one.
2. SKIP any task whose line is marked `⚠ HOLD` (it depends on a human decision under "Human-in-the-loop"); leave it unchecked and move to the next task that is NOT on hold.
3. NEVER implement anything under **## Human-in-the-loop** — those need a human (architectural decision / design review).
4. Open the task's linked `docs/issues/ISSUE-*.md` file and treat its **Acceptance criteria** as the definition of done. Implement with `/tdd` (red→green→refactor), one criterion at a time.
5. Run the project's tests + type checks and make them pass before committing. Commit referencing the issue id (e.g. `... (ISSUE-021)`).
6. When done, check the box `[x]` here and note completion in `progress.txt`. ONLY ONE TASK PER ITERATION.
7. If every task under ## Tasks is `[x]` or `⚠ HOLD`, output `<promise>COMPLETE</promise>`.

## Tasks

### Sprint 1 — Security & compliance
- [ ] ISSUE-001 — Delete `packages` scaffold · docs/issues/ISSUE-001-delete-packages-scaffold.md
- [ ] ISSUE-002 — Delete `agents`/`agent_features` scaffolds · docs/issues/ISSUE-002-delete-agents-scaffolds.md
- [ ] ISSUE-003 — Delete `permissions` scaffold · docs/issues/ISSUE-003-delete-permissions-scaffold.md
- [ ] ISSUE-004 — Delete `clients`/`client_features` scaffolds (incl `/all`) · docs/issues/ISSUE-004-delete-clients-scaffolds.md
- [ ] ISSUE-005 — Delete `entities/shifts` scaffold · docs/issues/ISSUE-005-delete-shifts-scaffold.md
- [ ] ISSUE-006 — `audit_logs` read-only · docs/issues/ISSUE-006-audit-logs-read-only.md
- [ ] ISSUE-007 — `api_usage` read-only · docs/issues/ISSUE-007-api-usage-read-only.md
- [ ] ISSUE-008 — Remove dead generator artifacts · docs/issues/ISSUE-008-remove-generator-artifacts.md
- [ ] ISSUE-009 — Explicit router allowlist · docs/issues/ISSUE-009-explicit-router-allowlist.md
- [ ] ISSUE-010 — Tenancy: PO-receive owner scope · docs/issues/ISSUE-010-tenancy-po-receive.md
- [ ] ISSUE-011 — Tenancy: payments-gateway owner scope · docs/issues/ISSUE-011-tenancy-payments-gateway.md
- [ ] ISSUE-012 — Tenancy: audit/api-usage owner scope + tag rows · docs/issues/ISSUE-012-tenancy-audit-owner-scope.md
- [ ] ISSUE-013 — Tenancy: `require_feature` owner scope · docs/issues/ISSUE-013-tenancy-require-feature.md
- [ ] ISSUE-014 — ZATCA: per-client PIH (kill singleton) · docs/issues/ISSUE-014-zatca-per-client-pih.md
- [ ] ISSUE-015 — ZATCA: valid signed UBL (XAdES+C14N+UUID) · docs/issues/ISSUE-015-zatca-signed-ubl.md
- [ ] ISSUE-016 — ZATCA: gate submission until valid · docs/issues/ISSUE-016-zatca-gate-submission.md
- [ ] ISSUE-018 — ZATCA: onboarding wizard · docs/issues/ISSUE-018-zatca-onboarding-wizard.md
- [ ] ISSUE-019 — Append-only / tamper-evident audit log · docs/issues/ISSUE-019-append-only-audit-log.md

### Sprint 2 — Make visible features work
- [ ] ISSUE-020 — Stop swallowing errors on façade pages · docs/issues/ISSUE-020-stop-swallowing-errors.md
- [ ] ISSUE-021 — ProductManagement reads `items` · docs/issues/ISSUE-021-productmanagement-reads-items.md
- [ ] ISSUE-022 — ExpenseTracking reads `items`/`total_amount` · docs/issues/ISSUE-022-expensetracking-reads-items.md
- [ ] ISSUE-023 — AgentDashboard `remaining_slots` · docs/issues/ISSUE-023-agentdashboard-remaining-slots.md
- [ ] ISSUE-024 — MasterDashboard price field · docs/issues/ISSUE-024-masterdashboard-price-field.md
- [ ] ISSUE-025 — DiscountManagement `usage_count` · docs/issues/ISSUE-025-discountmanagement-usage-count.md
- [ ] ISSUE-026 — Typed API return signatures · docs/issues/ISSUE-026-typed-api-returns.md
- [ ] ISSUE-027 — AuditLog reads real fields · docs/issues/ISSUE-027-auditlog-real-fields.md
- [ ] ISSUE-028 — Loyalty admin: 4 endpoints + UI · docs/issues/ISSUE-028-loyalty-admin-endpoints.md
- [ ] ISSUE-029 — Webhook delivery logs · docs/issues/ISSUE-029-webhook-delivery-logs.md
- [ ] ISSUE-031 — Hold/recall variant_id + open price · docs/issues/ISSUE-031-holdrecall-variant-id.md
- [ ] ISSUE-032 — Combo component deduction at settle · docs/issues/ISSUE-032-combo-component-deduction.md

### Sprint 3 — Close core merchant workflows
- [ ] ISSUE-033 — Staff login provisioning · docs/issues/ISSUE-033-staff-login-provisioning.md
- [ ] ISSUE-034 — Role→permission default map · docs/issues/ISSUE-034-role-permission-map.md
- [ ] ISSUE-035 — Permission-management UI · docs/issues/ISSUE-035-permission-management-ui.md
- [ ] ISSUE-036 — PO create real schema · docs/issues/ISSUE-036-po-create-real-schema.md
- [ ] ISSUE-037 — PO receive into branch + partial · docs/issues/ISSUE-037-po-receive-into-branch.md
- [ ] ISSUE-038 — Product↔category linkage · docs/issues/ISSUE-038-product-category-linkage.md
- [ ] ISSUE-039 — BOM recipe editor · docs/issues/ISSUE-039-bom-recipe-editor.md
- [ ] ISSUE-040 — Modifier-group attach UI · docs/issues/ISSUE-040-modifier-group-attach-ui.md
- [ ] ISSUE-041 — Auth: silent refresh · docs/issues/ISSUE-041-auth-silent-refresh.md
- [ ] ISSUE-042 — Auth: single logout · docs/issues/ISSUE-042-auth-single-logout.md
- [ ] ISSUE-043 — Login brute-force protection · docs/issues/ISSUE-043-login-brute-force.md
- [ ] ISSUE-044 — Loyalty ledger + expiry · docs/issues/ISSUE-044-loyalty-ledger-expiry.md

### Sprint 4 — Parity & polish
- [ ] ISSUE-045 — Receipt-template fields → renderer · docs/issues/ISSUE-045-receipt-template-fields-renderer.md
- [ ] ISSUE-046 — 58mm paper support · docs/issues/ISSUE-046-receipt-58mm-support.md
- [ ] ISSUE-047 — Saved printer + per-station routing · docs/issues/ISSUE-047-printer-station-routing.md
- [ ] ISSUE-048 — Receipt-template designer UI · docs/issues/ISSUE-048-receipt-template-designer-ui.md
- [ ] ISSUE-049 — Devices settings (register/list terminals) · docs/issues/ISSUE-049-devices-settings-terminals.md
- [ ] ISSUE-050 — Checkout terminal picker · docs/issues/ISSUE-050-checkout-terminal-picker.md
- [ ] ISSUE-051 — Webhook event emission completeness · docs/issues/ISSUE-051-webhook-event-emission.md
- [ ] ISSUE-052 — Billing scheduler · docs/issues/ISSUE-052-billing-scheduler.md
- [ ] ISSUE-053 — Billing proration · docs/issues/ISSUE-053-billing-proration.md
- [ ] ISSUE-054 — Coupons / trials · docs/issues/ISSUE-054-billing-coupons-trials.md
- [ ] ISSUE-055 — Commission statements · docs/issues/ISSUE-055-commission-statements.md
- [ ] ISSUE-056 — Quote→sale conversion · docs/issues/ISSUE-056-quote-to-sale.md
- [ ] ISSUE-057 — Gift-card void/reload + refund-to-card · docs/issues/ISSUE-057-giftcard-void-reload.md
- [ ] ISSUE-058 — Advanced discounts · docs/issues/ISSUE-058-advanced-discounts.md
- [ ] ISSUE-059 — Unique discount codes · docs/issues/ISSUE-059-unique-discount-codes.md
- [ ] ISSUE-060 — Stock-transfer history · docs/issues/ISSUE-060-stock-transfer-history.md
- [ ] ISSUE-061 — Two-phase transfer · docs/issues/ISSUE-061-two-phase-transfer.md
- [ ] ISSUE-062 — Branch `is_main` UI · docs/issues/ISSUE-062-branch-is-main-ui.md
- [ ] ISSUE-063 — Supplier VAT number · docs/issues/ISSUE-063-supplier-vat-number.md
- [ ] ISSUE-064 — Catalog CSV import/export · docs/issues/ISSUE-064-catalog-csv-import-export.md
- [ ] ISSUE-065 — Product images · docs/issues/ISSUE-065-product-images.md · ⚠ HOLD: depends on ISSUE-030 (storage, human decision)
- [ ] ISSUE-066 — Retail modifiers/combos · docs/issues/ISSUE-066-retail-modifiers-combos.md
- [ ] ISSUE-067 — Per-branch variant stock · docs/issues/ISSUE-067-per-branch-variant-stock.md
- [ ] ISSUE-068 — Soft-delete products · docs/issues/ISSUE-068-soft-delete-products.md
- [ ] ISSUE-069 — Reservations / waitlist · docs/issues/ISSUE-069-reservations-waitlist.md
- [ ] ISSUE-070 — Per-seat / partial settlement · docs/issues/ISSUE-070-per-seat-partial-settlement.md
- [ ] ISSUE-071 — In-app thermal print · docs/issues/ISSUE-071-in-app-thermal-print.md
- [ ] ISSUE-072 — Tip entry on settle · docs/issues/ISSUE-072-tip-entry-settle.md
- [ ] ISSUE-073 — KDS bumped-card / undo · docs/issues/ISSUE-073-kds-bumped-undo.md
- [ ] ISSUE-074 — Cash-drawer change-due helper · docs/issues/ISSUE-074-change-due-helper.md
- [ ] ISSUE-075 — Reprint past receipts · docs/issues/ISSUE-075-reprint-receipts.md
- [ ] ISSUE-076 — Price / stock check · docs/issues/ISSUE-076-price-stock-check.md
- [ ] ISSUE-078 — Persisted per-user profile · docs/issues/ISSUE-078-persisted-user-profile.md
- [ ] ISSUE-077 — Notification delivery honoring prefs · docs/issues/ISSUE-077-notification-delivery.md
- [ ] ISSUE-079 — Merchant store-settings screen · docs/issues/ISSUE-079-store-settings-screen.md
- [ ] ISSUE-080 — Object storage / exports · docs/issues/ISSUE-080-object-storage-exports.md · ⚠ HOLD: depends on ISSUE-030 (storage, human decision)
- [ ] ISSUE-081 — MFA · docs/issues/ISSUE-081-mfa.md
- [ ] ISSUE-082 — Password reset / forgot · docs/issues/ISSUE-082-password-reset.md
- [ ] ISSUE-083 — Active-session management · docs/issues/ISSUE-083-active-session-management.md
- [ ] ISSUE-084 — Password complexity policy · docs/issues/ISSUE-084-password-complexity.md
- [ ] ISSUE-094 — Remove LogoutCallbackPage · docs/issues/ISSUE-094-remove-logoutcallbackpage.md
- [ ] ISSUE-095 — Rename atomsClient→apiClient + drop shims · docs/issues/ISSUE-095-rename-atomsclient.md
- [ ] ISSUE-096 — Remove dead refreshAccessToken residue · docs/issues/ISSUE-096-remove-dead-refreshtoken.md
- [ ] ISSUE-097 — UserProfile change-password block · docs/issues/ISSUE-097-userprofile-change-password.md
- [ ] ISSUE-098 — Remove storage residue + settingsApi orphan · docs/issues/ISSUE-098-remove-storage-residue.md · ⚠ HOLD: depends on ISSUE-030 (storage, human decision)
- [ ] ISSUE-099 — Register PerformanceMiddleware · docs/issues/ISSUE-099-register-performance-middleware.md
- [ ] ISSUE-100 — Remove duplicate CORS placeholder · docs/issues/ISSUE-100-remove-cors-dupe.md
- [ ] ISSUE-101 — Fix sw.js manifest reference · docs/issues/ISSUE-101-fix-sw-manifest.md
- [ ] ISSUE-102 — Refund UI shows SAR · docs/issues/ISSUE-102-refund-ui-sar.md
- [ ] ISSUE-103 — Assign `bill_printed` table state · docs/issues/ISSUE-103-bill-printed-state.md
- [ ] ISSUE-104 — Fix deplete-stock double-deduct · docs/issues/ISSUE-104-deplete-double-deduct.md

## Human-in-the-loop (DO NOT auto-implement — needs a human decision/review)
- ISSUE-017 — ZATCA: Fatoora sandbox verification (needs sandbox creds + response review) · docs/issues/ISSUE-017-zatca-sandbox-verify.md
- ISSUE-030 — Storage: work-or-delete decision (unblocks 065/080/098) · docs/issues/ISSUE-030-storage-work-or-delete.md
- ISSUE-085 — Re-skin: PackageManagement (design review) · docs/issues/ISSUE-085-reskin-packagemanagement.md
- ISSUE-086 — Re-skin: BrandingEditor (design review) · docs/issues/ISSUE-086-reskin-brandingeditor.md
- ISSUE-087 — Re-skin: SupplierManagement (design review) · docs/issues/ISSUE-087-reskin-suppliermanagement.md
- ISSUE-088 — Re-skin: DiscountManagement (design review) · docs/issues/ISSUE-088-reskin-discountmanagement.md
- ISSUE-089 — Re-skin: AuditLog (design review) · docs/issues/ISSUE-089-reskin-auditlog.md
- ISSUE-090 — Re-skin: WebhookManagement (design review) · docs/issues/ISSUE-090-reskin-webhookmanagement.md
- ISSUE-091 — Re-skin: CustomerDisplay (design review) · docs/issues/ISSUE-091-reskin-customerdisplay.md
- ISSUE-092 — Re-skin: Shift/StaffManagement (design review) · docs/issues/ISSUE-092-reskin-shift-staff.md
- ISSUE-093 — Re-skin: auth gate screens (design review) · docs/issues/ISSUE-093-reskin-auth-gates.md
