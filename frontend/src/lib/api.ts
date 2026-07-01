import { createClient, uploadMultipart, getBlob, getText, getToken } from './apiClient';
import { getAPIBaseURL } from './config';

export const client = createClient();

// Role detection
export async function getRole() {
  const response = await client.apiCall.invoke({
    url: '/api/v1/tenant/role',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Master endpoints
export async function getMasterAgents(skip = 0, limit = 50) {
  const response = await client.apiCall.invoke({
    url: '/api/v1/tenant/master/agents',
    method: 'GET',
    data: { skip, limit },
  });
  return response.data;
}

export async function toggleAgent(agentId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/tenant/master/agents/${agentId}/toggle`,
    method: 'POST',
    data: {},
  });
  return response.data;
}

// #236 (A4): blast-radius preview for suspending an agent — the merchants and
// staff the suspension cascade (SEC-02) would block at auth, shown before confirm.
export interface AgentSuspendImpact {
  agent_id: number;
  company_name: string;
  merchant_count: number;
  staff_count: number;
}
export async function getAgentSuspendImpact(agentId: number): Promise<AgentSuspendImpact> {
  const response = await client.apiCall.invoke<AgentSuspendImpact>({
    url: `/api/v1/tenant/master/agents/${agentId}/suspend-impact`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// M10 Ops (#211): the "last backup" health indicator. Collapses the backup-run
// ledger into one operable state — ok / stale / failing / missing — against the
// documented RPO/RTO targets, so the master sees DR posture at a glance.
export interface BackupHealth {
  status: 'ok' | 'stale' | 'failing' | 'missing';
  last_success_at?: string | null;
  last_run_at?: string | null;
  last_run_status?: string | null;
  age_seconds?: number | null;
  total_runs: number;
  rpo_target_seconds: number;
  rto_target_seconds: number;
}
export async function getBackupHealth(): Promise<BackupHealth> {
  const response = await client.apiCall.invoke<BackupHealth>({
    url: '/api/v1/tenant/master/ops/backups/health',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// MA-08 / RSL-08 / RPT-09 (F-023): platform-wide economics for the master operator
// console — MRR (yearly plans normalized to fee/12), churn (suspended share),
// active merchants, and a revenue-by-agent leaderboard. `collected` is the agent's
// GMV from his own merchants (his money); `quota_paid` is what he paid the platform
// for his quota (Rail 1 — the platform's revenue from this agent).
export interface AgentEconomics {
  agent_id: number;
  company_name: string;
  is_active: boolean;
  total_clients: number;
  active_clients: number;
  mrr: number;
  collected: number;
  quota_paid: number;
  payments: number;
}

export interface MasterEconomics {
  total_agents: number;
  active_agents: number;
  total_clients: number;
  active_clients: number;
  churned_clients: number;
  mrr: number;
  arr: number;
  churn_rate: number;
  // ISSUE-245: LTV is a real aggregate (ARPA / churn); null when churn is zero.
  // CAC is null until an acquisition-spend feed exists (honest, never fabricated).
  ltv?: number | null;
  cac?: number | null;
  collected: number;
  platform_revenue: number;
  by_agent: AgentEconomics[];
}

export async function getMasterEconomics(): Promise<MasterEconomics> {
  const response = await client.apiCall.invoke<MasterEconomics>({
    url: '/api/v1/tenant/master/economics',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Agent endpoints
// ISSUE-023/026 (H9): GET /agent/clients returns AgentClientsResponse
// `{ items, total, remaining_slots }` (routers/tenant.py). The Remaining-Slots
// tile reads `remaining_slots`/`total` from here — the explicit signature stops
// the UI from silently sourcing slot counts off the branding payload again.
export interface AgentClientListItem {
  id: number;
  business_name: string;
  email: string;
  phone?: string | null;
  subscription_fee?: number | null;
  is_active: boolean;
  zatca_enabled: boolean;
  language_preference: string;
  created_at?: string | null;
  // M8 (issue-215): ISO timestamp the merchant was archived, or null when live.
  archived_at?: string | null;
}

export interface AgentClientsResponse {
  items: AgentClientListItem[];
  total: number;
  remaining_slots: number;
}

export async function getAgentClients(
  skip = 0,
  limit = 50,
  archived = false,
): Promise<AgentClientsResponse> {
  const response = await client.apiCall.invoke<AgentClientsResponse>({
    url: '/api/v1/tenant/agent/clients',
    method: 'GET',
    // M8: `archived` selects the archived book (for restore/delete) over the live one.
    data: { skip, limit, archived },
  });
  return response.data;
}

export async function getAgentBranding() {
  const response = await client.apiCall.invoke({
    url: '/api/v1/tenant/agent/branding',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// The agent's settled-subscription revenue, summed from his merchants' payments.
// This is entirely the agent's money — the platform takes no cut here (the
// platform's revenue is the wholesale quota the agent buys, Rail 1).
export interface RevenueByClient {
  client_id: number;
  business_name: string;
  collected: number;
  payments: number;
}

export interface AgentRevenue {
  collected: number;
  payments: number;
  by_client: RevenueByClient[];
}

export async function getAgentRevenue(): Promise<AgentRevenue> {
  const response = await client.apiCall.invoke<AgentRevenue>({
    url: '/api/v1/tenant/agent/revenue',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// ISSUE-245: agent dashboard KPIs — active merchants, merchant growth (this 30-day
// window vs the prior), trial expiry, and a short revenue trend. All scoped to the
// caller's own merchants and SQL/window-aggregated (no load-everything).
export interface MerchantGrowth {
  new_current: number;
  new_previous: number;
  delta: number;
}

export interface TrialExpiry {
  expiring_soon: number;
  next_trial_end?: string | null;
}

export interface RevenueTrendPoint {
  month: string;
  amount: number;
}

export interface AgentDashboardKpis {
  active_merchants: number;
  total_merchants: number;
  merchant_growth: MerchantGrowth;
  trial_expiry: TrialExpiry;
  revenue_trend: RevenueTrendPoint[];
}

export async function getAgentDashboardKpis(): Promise<AgentDashboardKpis> {
  const response = await client.apiCall.invoke<AgentDashboardKpis>({
    url: '/api/v1/tenant/agent/dashboard-kpis',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Per-period subscription-collection statements for the agent, each with line
// items by client. The period total is the sum of the period's payments (the
// agent's own revenue — no platform cut).
export interface CommissionStatementLine {
  client_id: number;
  business_name: string;
  collected: number;
  payments: number;
}

export interface CommissionStatement {
  period_start: string;
  period_end: string;
  billing_cycle: string;
  collected: number;
  payments: number;
  by_client: CommissionStatementLine[];
}

export interface CommissionStatements {
  statements: CommissionStatement[];
}

export async function getAgentCommissionStatements(): Promise<CommissionStatements> {
  const response = await client.apiCall.invoke<CommissionStatements>({
    url: '/api/v1/tenant/agent/commission/statements',
    method: 'GET',
    data: {},
  });
  return response.data;
}

export interface CreatedClient {
  id: number;
  business_name: string;
  email: string;
  phone?: string;
  subscription_fee?: number;
  language_preference: string;
  // One-time provisioning credentials (shown once / emailed).
  temp_password: string;
  must_change_password: boolean;
  email_delivered: boolean;
}

export async function createNewClient(data: {
  business_name: string;
  email: string;
  phone?: string;
  subscription_fee?: number;
  language_preference?: string;
  features?: string[];
}): Promise<CreatedClient> {
  const response = await client.apiCall.invoke<CreatedClient>({
    url: '/api/v1/tenant/agent/clients',
    method: 'POST',
    data,
  });
  return response.data;
}

// Client endpoints
export async function getClientDashboard() {
  const response = await client.apiCall.invoke({
    url: '/api/v1/tenant/client/dashboard',
    method: 'GET',
    data: {},
  });
  return response.data;
}

export async function getClientBranding() {
  const response = await client.apiCall.invoke({
    url: '/api/v1/tenant/client/branding',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// POS endpoints
// PAY-01: a captured tender on the sale — the network/approval proof for a
// card-like payment. Carries only PCI-safe fields (never a PAN).
export interface TenderInfo {
  tender_type: string;
  amount: number;
  network?: string;
  approval_code?: string;
  rrn?: string;
  last4?: string;
  gateway?: string;
  status: string;
}

export interface TransactionResult {
  id: number;
  invoice_number: string;
  subtotal: number;
  vat_amount: number;
  discount_amount: number;
  total_amount: number;
  // POS-13 (F-012): gratuity collected on top of total_amount; null when no tip.
  // The customer paid total_amount + tip_amount across the tenders.
  tip_amount?: number | null;
  // ISSUE-074: cash-drawer change helper — cash handed over + change owed back.
  // Drawer-facing only; null on a non-cash / unentered sale.
  cash_tendered?: number | null;
  change_due?: number | null;
  payment_method: string;
  status: string;
  // Stamped ZATCA TLV (base64) + the ready-to-render fiscal QR PNG (base64).
  zatca_qr?: string;
  zatca_qr_base64?: string;
  zatca_hash?: string;
  zatca_document_id?: number;
  zatca_status?: string;
  // Captured tenders (PAY-01) — how the sale was really paid.
  tenders?: TenderInfo[];
}

export interface PaymentEntry {
  // 'cash' | 'card' | 'mada' | 'applepay' | 'stcpay' | 'tabby' | 'tamara' | 'transfer' | 'loyalty' | 'giftcard'
  method: string;
  amount: number;
  // Card-like tenders capture a real gateway approval (PAY-01/05). token is the
  // gateway card token from client tokenization (no PAN); simulate is a
  // sandbox-only hint ('approve'/'decline') ignored by real gateways.
  tender_type?: string;
  token?: string;
  simulate?: string;
  // HW-03/PAY-05: push this card-like leg to a paired in-store SoftPOS terminal
  // for a real approval instead of the online gateway. A decline blocks the sale.
  terminal_id?: number;
  // CRM-03/PRC-05 (F-038): when this leg is a gift card, the bearer code whose
  // balance is validated + atomically decremented on the sale path.
  gift_card_code?: string;
}

export async function createTransaction(data: {
  // variant_id (INV-04): when the line is a product variant SKU, the sale
  // decrements that variant's own stock instead of the parent product's.
  items: { product_id: number; variant_id?: number; name: string; name_ar?: string; quantity: number; price: number; vat_rate: number }[];
  payment_method: string;
  customer_name?: string;
  customer_phone?: string;
  // F-018/ZA-06: buyer VAT for a B2B sale. When set (or resolvable from the
  // selected customer's saved record) the invoice carries the buyer tax block and
  // routes to clearance once it clears the threshold.
  customer_vat_number?: string;
  // POS-01: persist the applied order discount so totals match what the cashier saw.
  discount_amount?: number;
  // POS-13 (F-012): gratuity collected on top of the invoice total. Outside the VAT
  // base; the split/single tenders must cover total_amount + tip_amount.
  tip_amount?: number;
  // ISSUE-074: cash the customer handed over on a cash payment; the server records
  // it and the change owed back. Drawer-facing only — never changes the tender.
  cash_tendered?: number;
  // PRC-01: a discount code the server validates and prices authoritatively. When
  // set, the server recomputes the discount from the rule and consumes one use —
  // the client-sent discount_amount is not trusted for the coded portion.
  discount_code?: string;
  // POS-02: split tenders (cash + card + …). Per-method amounts must sum to the total.
  payments?: PaymentEntry[];
  // Loyalty: identify the customer to accrue points; redeem_points spends balance.
  customer_id?: number;
  redeem_points?: number;
  // Multi-branch: tag the sale to a branch so its stock ledger is deducted.
  branch_id?: number;
  // Single-tender capture hints (PAY-01) when not using split payments.
  payment_token?: string;
  payment_simulate?: string;
  // HW-03/PAY-05: capture a single card-like tender on a paired SoftPOS terminal.
  payment_terminal_id?: number;
  // CRM-03/PRC-05 (F-038): single-tender gift-card sale — the bearer code redeemed.
  payment_gift_card_code?: string;
}): Promise<TransactionResult> {
  const response = await client.apiCall.invoke<TransactionResult>({
    url: '/api/v1/pos/transaction',
    method: 'POST',
    data,
  });
  return response.data;
}

// ---------------------------------------------------------------------------
// Gift cards / store credit (CRM-03 / PRC-05, F-038)
// ---------------------------------------------------------------------------
export interface GiftCard {
  id: number;
  code: string;
  currency: string;
  initial_balance: number;
  balance: number;
  status: string;
  expiry_date?: string | null;
  customer_id?: number | null;
  created_at?: string;
}

export interface GiftCardBalance {
  code: string;
  balance: number;
  status: string;
  expiry_date?: string | null;
  is_redeemable: boolean;
}

export async function issueGiftCard(data: {
  amount: number;
  currency?: string;
  expiry_date?: string;
  customer_id?: number;
}): Promise<GiftCard> {
  const response = await client.apiCall.invoke<GiftCard>({
    url: '/api/v1/gift-cards',
    method: 'POST',
    data,
  });
  return response.data;
}

// Server-side paginated (OPS-05): `total` is the full count so the caller can page.
export async function listGiftCards(
  skip = 0,
  limit = 50,
): Promise<{ items: GiftCard[]; total: number }> {
  const response = await client.apiCall.invoke<{ items: GiftCard[]; total: number }>({
    url: '/api/v1/gift-cards',
    method: 'GET',
    data: { skip, limit },
  });
  return response.data;
}

export async function getGiftCardBalance(code: string): Promise<GiftCardBalance> {
  const response = await client.apiCall.invoke<GiftCardBalance>({
    url: `/api/v1/gift-cards/${encodeURIComponent(code)}/balance`,
    method: 'GET',
  });
  return response.data;
}

export interface GiftCardLedgerEntry {
  id: number;
  entry_type: string;
  amount: number;
  balance_after: number;
  transaction_id?: number | null;
  note?: string | null;
  created_at?: string;
}

// ISSUE-057: cancel a card — freezes its balance and makes it unredeemable.
export async function voidGiftCard(cardId: number): Promise<GiftCard> {
  const response = await client.apiCall.invoke<GiftCard>({
    url: `/api/v1/gift-cards/${cardId}/void`,
    method: 'POST',
  });
  return response.data;
}

// ISSUE-057: top up a card's balance (reactivates a previously exhausted card).
export async function reloadGiftCard(cardId: number, amount: number): Promise<GiftCard> {
  const response = await client.apiCall.invoke<GiftCard>({
    url: `/api/v1/gift-cards/${cardId}/reload`,
    method: 'POST',
    data: { amount },
  });
  return response.data;
}

// ISSUE-057: refund a sale's value back onto a card, increasing its balance.
export async function refundToGiftCard(
  cardId: number,
  amount: number,
  transactionId?: number,
): Promise<GiftCard> {
  const response = await client.apiCall.invoke<GiftCard>({
    url: `/api/v1/gift-cards/${cardId}/refund`,
    method: 'POST',
    data: { amount, transaction_id: transactionId },
  });
  return response.data;
}

export async function getGiftCardLedger(cardId: number): Promise<GiftCardLedgerEntry[]> {
  const response = await client.apiCall.invoke<GiftCardLedgerEntry[]>({
    url: `/api/v1/gift-cards/${cardId}/ledger`,
    method: 'GET',
  });
  return response.data;
}

export interface RefundResult {
  credit_note_id: number;
  original_transaction_id: number;
  credit_note_number: string;
  total_amount: number;
  zatca_qr?: string;
  zatca_qr_base64?: string;
  zatca_document_id: number;
  zatca_status: string;
  // POS-07: "refunded" when fully returned, "partial_refunded" when a balance remains.
  original_status: string;
}

// POS-07: one returned line for a partial/line-level refund.
export interface RefundLine {
  product_id: number;
  quantity: number;
  // INV-04: the variant being returned, when the line was a variant SKU.
  variant_id?: number;
}

// POS-07: refund a sale by issuing a ZATCA credit note (type 381). Restores
// inventory and signs the credit note server-side; returns its number + QR.
// Pass `lines` to return only selected units (partial/line-level refund); omit
// it to refund the whole remaining balance.
export async function refundTransaction(
  transactionId: number,
  lines?: RefundLine[],
): Promise<RefundResult> {
  const response = await client.apiCall.invoke<RefundResult>({
    url: `/api/v1/pos/transactions/${transactionId}/refund`,
    method: 'POST',
    data: lines && lines.length > 0 ? { lines } : {},
  });
  return response.data;
}

// POS-08: void (audited cancellation) of a whole sale, gated by `pos.void`.
export interface VoidResult {
  transaction_id: number;
  invoice_number: string;
  status: string;
}

// POS-08: void a sale rung in error. Marks it `voided`, restores stock, and
// writes an audit row server-side (gated by the `pos.void` permission). Unlike
// a refund this issues no credit note; the server returns 409 if the invoice
// has already been reported to ZATCA (refund it instead).
export async function voidTransaction(
  transactionId: number,
  reason?: string,
): Promise<VoidResult> {
  const response = await client.apiCall.invoke<VoidResult>({
    url: `/api/v1/pos/transactions/${transactionId}/void`,
    method: 'POST',
    data: reason ? { reason } : {},
  });
  return response.data;
}

// HW-03/PAY-05: integrated in-store SoftPOS terminals (F-005).
export interface Terminal {
  id: number;
  provider: string;
  label?: string;
  serial?: string;
  branch_id?: number;
  status: string;
}

export interface TerminalChargeResult {
  approved: boolean;
  tender_id?: number;
  tender_type: string;
  amount: number;
  network?: string;
  approval_code?: string;
  rrn?: string;
  gateway_ref?: string;
  last4?: string;
  gateway: string;
  status: string;
}

// Register an in-store SoftPOS terminal the merchant has paired (provider 'geidea').
export async function registerTerminal(data: {
  provider?: string;
  label?: string;
  serial?: string;
  branch_id?: number;
}): Promise<Terminal> {
  const response = await client.apiCall.invoke<Terminal>({
    url: '/api/v1/payments/terminals',
    method: 'POST',
    data,
  });
  return response.data;
}

// List the caller's registered terminals (owner-scoped).
export async function listTerminals(): Promise<Terminal[]> {
  const response = await client.apiCall.invoke<Terminal[]>({
    url: '/api/v1/payments/terminals',
    method: 'GET',
  });
  return response.data;
}

// Push an amount to a paired SoftPOS terminal and capture the approval (HW-03).
// A decline throws (the SDK surfaces the 402) so checkout can block the sale.
export async function chargeTerminal(data: {
  terminal_id: number;
  amount: number;
  tender_type?: string;
  currency?: string;
  simulate?: string;
}): Promise<TerminalChargeResult> {
  const response = await client.apiCall.invoke<TerminalChargeResult>({
    url: '/api/v1/payments/terminal/charge',
    method: 'POST',
    data,
  });
  return response.data;
}

// ---- Advanced discounts: auto-applied promotions (ISSUE-058) ----
export interface Promotion {
  id: number;
  name: string;
  kind: 'line' | 'category' | 'bogo';
  disc_type?: string | null;
  value?: number | null;
  product_id?: number | null;
  category?: string | null;
  min_subtotal?: number | null;
  bogo_buy_qty?: number | null;
  bogo_get_qty?: number | null;
  bogo_get_percent?: number | null;
  is_active?: boolean | null;
}

export interface AppliedPromotion {
  promotion_id?: number | null;
  name: string;
  kind: string;
  amount: number;
}

// Define a line/category/BOGO promotion the merchant's carts auto-apply (ISSUE-058).
export async function createPromotion(data: {
  name: string;
  kind: 'line' | 'category' | 'bogo';
  disc_type?: string;
  value?: number;
  product_id?: number;
  category?: string;
  min_subtotal?: number;
  bogo_buy_qty?: number;
  bogo_get_qty?: number;
  bogo_get_percent?: number;
  is_active?: boolean;
}): Promise<Promotion> {
  const response = await client.apiCall.invoke<Promotion>({
    url: '/api/v1/entities/promotions',
    method: 'POST',
    data,
  });
  return response.data;
}

// List the merchant's configured promotions (owner-scoped).
export async function listPromotions(): Promise<{ items: Promotion[]; total: number }> {
  const response = await client.apiCall.invoke<{ items: Promotion[]; total: number }>({
    url: '/api/v1/entities/promotions',
    method: 'GET',
  });
  return response.data;
}

// Preview which promotions a cart would earn, before tendering — so the cashier
// sees the auto-applied discount up front (AC2). Does not ring a sale.
export async function previewPromotions(
  items: Array<{ product_id?: number; price: number; quantity: number }>,
): Promise<{ total_discount: number; applied: AppliedPromotion[] }> {
  const response = await client.apiCall.invoke<{ total_discount: number; applied: AppliedPromotion[] }>({
    url: '/api/v1/pos/promotions/preview',
    method: 'POST',
    data: { items },
  });
  return response.data;
}

export async function getTransactions(page = 1, pageSize = 20) {
  const response = await client.apiCall.invoke({
    url: '/api/v1/pos/transactions',
    method: 'GET',
    data: { page, page_size: pageSize },
  });
  return response.data;
}

// POS-10: park/hold & recall. A held ticket is a saved cart with no fiscal side
// effect (no invoice, no ZATCA, no stock deduction) — it is rung up as a real
// sale only when recalled and sent through createTransaction.
export interface HeldItem {
  product_id: number;
  name: string;
  name_ar?: string;
  price: number;
  quantity: number;
  discount?: number;
  // INV-04 (F-033): when the held line is a product *variant* SKU, this carries the
  // variant id so recall restores the variant (not the parent) — without it the
  // recalled sale deducts the parent product's stock (ISSUE-031 / H28).
  variant_id?: number;
}

export interface HeldTicket {
  id: number;
  label?: string;
  item_count: number;
  subtotal: number;
  total_amount: number;
  customer_name?: string;
  customer_phone?: string;
  branch_id?: number;
  items_json?: string;
  created_at?: string;
}

export interface RecalledTicket {
  id: number;
  label?: string;
  items: HeldItem[];
  customer_name?: string;
  customer_phone?: string;
  branch_id?: number;
}

export async function holdSale(data: {
  items: {
    product_id: number;
    name: string;
    name_ar?: string;
    price: number;
    quantity: number;
    variant_id?: number;
  }[];
  label?: string;
  customer_name?: string;
  customer_phone?: string;
  branch_id?: number;
}): Promise<HeldTicket> {
  const response = await client.apiCall.invoke<HeldTicket>({
    url: '/api/v1/pos/hold',
    method: 'POST',
    data,
  });
  return response.data;
}

export async function getHeldSales(
  skip = 0,
  limit = 50,
): Promise<{ items: HeldTicket[]; total: number }> {
  const response = await client.apiCall.invoke<{ items: HeldTicket[]; total: number }>({
    url: '/api/v1/pos/held',
    method: 'GET',
    data: { skip, limit },
  });
  return response.data;
}

export async function recallSale(heldId: number): Promise<RecalledTicket> {
  const response = await client.apiCall.invoke<RecalledTicket>({
    url: `/api/v1/pos/recall/${heldId}`,
    method: 'POST',
  });
  return response.data;
}

// INV-06 (F-036): stock counts & adjustments with reasons → variance record.
export type StockAdjustmentReason =
  | 'count'
  | 'wastage'
  | 'damage'
  | 'correction'
  | 'restock'
  | 'other';

export interface StockAdjustment {
  id: number;
  product_id: number;
  product_name?: string;
  branch_id?: number | null;
  reason: StockAdjustmentReason;
  system_quantity: number;
  counted_quantity: number;
  variance: number;
  note?: string | null;
  created_at?: string | null;
}

export async function createStockAdjustment(data: {
  product_id?: number;
  product_name?: string;
  branch_id?: number;
  reason: StockAdjustmentReason;
  counted_quantity: number;
  note?: string;
}): Promise<StockAdjustment> {
  const response = await client.apiCall.invoke<StockAdjustment>({
    url: '/api/v1/production/stock-adjustments',
    method: 'POST',
    data,
  });
  return response.data;
}

export async function getStockAdjustments(params?: {
  branch_id?: number;
  product_id?: number;
}): Promise<{ items: StockAdjustment[]; total: number }> {
  const response = await client.apiCall.invoke<{ items: StockAdjustment[]; total: number }>({
    url: '/api/v1/production/stock-adjustments',
    method: 'GET',
    data: params || {},
  });
  return response.data;
}

// ISSUE-060: inter-branch stock-transfer history (the audit rows F-032 writes).
export interface BranchTransfer {
  id: number;
  from_branch_id: number;
  to_branch_id: number;
  product_id: number;
  product_name?: string | null;
  quantity: number;
  status: string;
  created_at?: string | null;
}

export async function getBranchTransfers(params?: {
  branch_id?: number;
  product_id?: number;
  status?: string;
}): Promise<{ items: BranchTransfer[]; total: number }> {
  const response = await client.apiCall.invoke<{ items: BranchTransfer[]; total: number }>({
    url: '/api/v1/production/branches/transfers',
    method: 'GET',
    data: params || {},
  });
  return response.data;
}

// ISSUE-061: two-phase transfer (dispatch → receive). Stock leaves the source on
// dispatch (in_transit) and lands at the destination only on receive; a short
// receive records the dispatched−received discrepancy.
export interface DispatchedTransfer {
  id: number;
  from_branch_id: number;
  to_branch_id: number;
  product_id: number;
  product_name?: string | null;
  quantity: number;
  status: string;
  from_branch_quantity: number;
}

export interface ReceivedTransfer {
  id: number;
  from_branch_id: number;
  to_branch_id: number;
  product_id: number;
  product_name?: string | null;
  quantity: number;
  received_quantity: number;
  discrepancy: number;
  status: string;
  to_branch_quantity: number;
}

export async function dispatchBranchTransfer(data: {
  from_branch_id: number;
  to_branch_id: number;
  product_id?: number;
  product_name?: string;
  quantity: number;
}): Promise<DispatchedTransfer> {
  const response = await client.apiCall.invoke<DispatchedTransfer>({
    url: '/api/v1/production/branches/transfer/dispatch',
    method: 'POST',
    data,
  });
  return response.data;
}

export async function receiveBranchTransfer(
  transferId: number,
  receivedQuantity?: number,
): Promise<ReceivedTransfer> {
  const response = await client.apiCall.invoke<ReceivedTransfer>({
    url: `/api/v1/production/branches/transfer/${transferId}/receive`,
    method: 'POST',
    data: receivedQuantity == null ? {} : { received_quantity: receivedQuantity },
  });
  return response.data;
}

// M4 / #207 — guided stocktake (sessioned count → freeze → count → approve).
// A resumable physical count layered on the stock-adjustments variance primitive:
// freeze snapshots the on-hand baseline, counts fill it in, approve posts one
// adjustment per counted line atomically.
export type StocktakeStatus = 'draft' | 'frozen' | 'approved' | 'cancelled';

export interface StocktakeLine {
  id: number;
  product_id: number;
  product_name?: string | null;
  system_quantity: number;
  counted_quantity: number | null;
  variance: number | null;
  counted: boolean;
  note?: string | null;
  counted_at?: string | null;
}

export interface StocktakeSession {
  id: number;
  branch_id?: number | null;
  name?: string | null;
  status: StocktakeStatus;
  note?: string | null;
  frozen_at?: string | null;
  approved_at?: string | null;
  created_at?: string | null;
  // Present on the detail/freeze/approve responses (the session + its lines).
  lines?: StocktakeLine[];
  line_count?: number;
  counted_count?: number;
  variance_count?: number;
  total_variance?: number;
  // Present on the approve response.
  adjustments_posted?: number;
}

export interface StocktakeCountResult {
  id: number;
  session_id: number;
  product_id: number;
  product_name?: string | null;
  system_quantity: number;
  counted_quantity: number;
  variance: number;
  counted_at?: string | null;
}

export async function listStocktakes(params?: {
  status?: StocktakeStatus;
  branch_id?: number;
}): Promise<{ items: StocktakeSession[]; total: number }> {
  const response = await client.apiCall.invoke<{ items: StocktakeSession[]; total: number }>({
    url: '/api/v1/production/stock-counts',
    method: 'GET',
    data: params || {},
  });
  return response.data;
}

export async function getStocktake(sessionId: number): Promise<StocktakeSession> {
  const response = await client.apiCall.invoke<StocktakeSession>({
    url: `/api/v1/production/stock-counts/${sessionId}`,
    method: 'GET',
  });
  return response.data;
}

export async function startStocktake(data: {
  branch_id?: number;
  name?: string;
  note?: string;
}): Promise<StocktakeSession> {
  const response = await client.apiCall.invoke<StocktakeSession>({
    url: '/api/v1/production/stock-counts',
    method: 'POST',
    data,
  });
  return response.data;
}

export async function freezeStocktake(sessionId: number): Promise<StocktakeSession> {
  const response = await client.apiCall.invoke<StocktakeSession>({
    url: `/api/v1/production/stock-counts/${sessionId}/freeze`,
    method: 'POST',
  });
  return response.data;
}

export async function countStocktakeLine(
  sessionId: number,
  data: { product_id?: number; barcode?: string; counted_quantity: number; note?: string },
): Promise<StocktakeCountResult> {
  const response = await client.apiCall.invoke<StocktakeCountResult>({
    url: `/api/v1/production/stock-counts/${sessionId}/count`,
    method: 'POST',
    data,
  });
  return response.data;
}

export async function approveStocktake(sessionId: number): Promise<StocktakeSession> {
  const response = await client.apiCall.invoke<StocktakeSession>({
    url: `/api/v1/production/stock-counts/${sessionId}/approve`,
    method: 'POST',
  });
  return response.data;
}

export async function cancelStocktake(sessionId: number): Promise<StocktakeSession> {
  const response = await client.apiCall.invoke<StocktakeSession>({
    url: `/api/v1/production/stock-counts/${sessionId}/cancel`,
    method: 'POST',
  });
  return response.data;
}

// Phase 3: the caller's effective permission grants/denies, so the UI can
// hide/disable actions (e.g. refund) the staff member lacks. Master accounts
// come back with is_master=true and gate nothing.
export interface MyPermissions {
  is_master: boolean;
  denied: string[];
  granted: string[];
}

export async function getMyPermissions(): Promise<MyPermissions> {
  const response = await client.apiCall.invoke<MyPermissions>({
    url: '/api/v1/auth/me/permissions',
    method: 'GET',
  });
  return response.data;
}

/** Whether the current user may use a permission key (grant-by-default). */
export function canUse(perms: MyPermissions | null | undefined, key: string): boolean {
  if (!perms) return true; // not yet loaded — optimistic, server still enforces
  if (perms.is_master) return true;
  return !perms.denied.includes(key);
}

// Entity endpoints
export async function getProducts() {
  const response = await client.entities.products.query({
    query: {},
    limit: 100,
  });
  return response.data;
}

// ISSUE-024/026 (U1.1): GET /api/v1/packages/list returns PackageListResponse
// `{ items, total }`, each package carrying `suggested_retail_price` (the field
// MasterDashboard's retail-price line reads). Mirrors backend PackageResponse.
export interface Package {
  id: number;
  name: string;
  client_slots: number;
  wholesale_price: number;
  suggested_retail_price?: number | null;
  is_active: boolean;
  features?: string[] | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PackageListResponse {
  items: Package[];
  total: number;
}

export async function getPackages(): Promise<PackageListResponse> {
  // H1: the generic /api/v1/entities/packages scaffold was removed; the only
  // package surface is the master-gated listing in routers/features.py.
  const response = await client.apiCall.invoke<PackageListResponse>({
    url: '/api/v1/packages/list',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Public agent landing page data (no auth required)
export async function getAgentPublicProfile(agentId: string) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/tenant/agent/${agentId}/public`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Product Management
// ISSUE-021/026 (H6): GET /api/v1/products/list returns ProductListResponse
// `{ items, total }`. The explicit signature is the durable guard — reading the
// old drifted `products` key (which left the catalog table permanently empty) is
// now a tsc compile error. Mirrors backend ProductResponse in routers/features.py.
export interface ProductListItem {
  id: number;
  client_id: number;
  name: string;
  name_ar?: string | null;
  barcode?: string | null;
  price: number;
  cost_price?: number | null;
  quantity: number;
  reorder_point: number;
  reorder_quantity: number;
  category?: string | null;
  category_id?: number | null;
  vat_rate?: number | null;
  is_active: boolean;
  is_weighted: boolean;
  is_open_price: boolean;
  unit_label?: string | null;
  // ISSUE-065 (P2 catalog): served URL of the product image (catalog + POS tile
  // grid). May be a relative ``/uploads/...`` path — resolve via productImageSrc().
  image_url?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProductListResponse {
  items: ProductListItem[];
  total: number;
}

export async function getProductsList(
  categoryId?: number | string,
  search?: string,
  includeArchived?: boolean,
): Promise<ProductListResponse> {
  const params: Record<string, string> = {};
  // H7 (ISSUE-038): filter by the linked category id, not the legacy free-text name.
  if (categoryId !== undefined && categoryId !== '' && categoryId !== 'all') {
    params.category_id = String(categoryId);
  }
  if (search) params.search = search;
  // ISSUE-068: opt in to see archived (soft-deleted) products for restore.
  if (includeArchived) params.include_archived = 'true';
  const queryString = new URLSearchParams(params).toString();
  const url = queryString ? `/api/v1/products/list?${queryString}` : '/api/v1/products/list';
  const response = await client.apiCall.invoke<ProductListResponse>({
    url,
    method: 'GET',
    data: {},
  });
  return response.data;
}

export async function createProduct(data: {
  name: string;
  name_ar?: string;
  barcode?: string;
  price: number;
  cost_price?: number;
  quantity: number;
  reorder_point?: number;
  reorder_quantity?: number;
  category?: string;
  // H7 (ISSUE-038): link to a real category from the merchant's tree.
  category_id?: number;
  vat_rate?: number;
  // POS-11 (F-011): weighted / open-price configuration.
  is_weighted?: boolean;
  is_open_price?: boolean;
  unit_label?: string;
}) {
  const response = await client.apiCall.invoke({
    url: '/api/v1/products/create',
    method: 'POST',
    data,
  });
  return response.data;
}

export async function updateProduct(productId: number, data: Record<string, unknown>) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/products/${productId}`,
    method: 'PUT',
    data,
  });
  return response.data;
}

export async function deleteProduct(productId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/products/${productId}`,
    method: 'DELETE',
    data: {},
  });
  return response.data;
}

// ISSUE-068: un-archive a soft-deleted product so it reappears in the active
// catalog / POS.
export async function restoreProduct(productId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/products/${productId}/restore`,
    method: 'POST',
    data: {},
  });
  return response.data;
}

// ISSUE-065 (P2 catalog): upload a product image. Returns the updated product
// (its ``image_url`` is the served URL). Mirrors the agent-logo upload (AG-01).
export async function uploadProductImage(productId: number, file: File): Promise<ProductListItem> {
  return uploadMultipart<ProductListItem>(`/api/v1/products/${productId}/image`, file);
}

// ISSUE-065: resolve a product ``image_url`` for an <img> src. The backend serves
// images from a relative ``/uploads/...`` path; prefix the API origin so the POS
// (which may run on another origin) can load it. Absolute URLs pass through.
export function productImageSrc(imageUrl?: string | null): string | undefined {
  if (!imageUrl) return undefined;
  return imageUrl.startsWith('http') ? imageUrl : `${getAPIBaseURL()}${imageUrl}`;
}

// ISSUE-064: catalog CSV export/import. Export streams the merchant's catalog as
// a CSV blob; import uploads a CSV and returns a per-run report (created/updated
// counts + the rejected rows, so bad rows are surfaced, not silently dropped).
export interface CsvImportError {
  row: number;
  errors: string[];
}

export interface CsvImportResult {
  created: number;
  updated: number;
  total_rows: number;
  errors: CsvImportError[];
}

export async function exportProductsCsv(): Promise<Blob> {
  return getBlob('/api/v1/entities/products/export');
}

export async function importProductsCsv(file: File): Promise<CsvImportResult> {
  return uploadMultipart<CsvImportResult>('/api/v1/entities/products/import', file);
}

export async function getLowStockProducts() {
  const response = await client.apiCall.invoke({
    url: '/api/v1/products/low-stock',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// ---- Reorder points / auto-PO suggestions (INV-08, F-035) ----
export interface ReorderSuggestion {
  product_id: number;
  name: string;
  name_ar?: string;
  category?: string;
  on_hand: number;
  reorder_point: number;
  reorder_quantity: number;
  suggested_order_quantity: number;
}

export async function getReorderSuggestions(): Promise<{
  items: ReorderSuggestion[];
  total: number;
}> {
  const response = await client.apiCall.invoke({
    url: '/api/v1/products/reorder-suggestions',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// ---- AI forecasting / smart-reorder / dynamic pricing (#228, M9·AI) ----
// Read-only, tenant-scoped surfaces over the /reports/* forecast endpoints in
// backend/routers/features.py. Types mirror the Pydantic response models there.
export interface SalesForecastPoint {
  date: string; // projected day, YYYY-MM-DD
  forecast_sales: number;
}
// The sales-forecast endpoint exposes two self-describing models on one route:
// the flat 'moving_average' (default) and the direction-aware 'linear_trend',
// selected with ?method= (#228).
export type SalesForecastMethod = 'moving_average' | 'linear_trend';
export interface SalesForecastResponse {
  method: string;
  lookback_days: number;
  horizon_days: number;
  history_total: number;
  avg_daily_sales: number;
  trend_per_day: number; // projected day-over-day change (0 for moving_average)
  points: SalesForecastPoint[];
}
export async function getSalesForecast(
  lookback = 30,
  horizon = 7,
  method: SalesForecastMethod = 'moving_average'
): Promise<SalesForecastResponse> {
  const response = await client.apiCall.invoke<SalesForecastResponse>({
    url: `/api/v1/reports/sales-forecast?lookback=${lookback}&horizon=${horizon}&method=${method}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

export interface InventoryForecastItem {
  product_id: number;
  name: string;
  name_ar?: string | null;
  on_hand: number;
  avg_daily_units: number;
  projected_demand: number;
  days_of_cover: number | null;
  will_stock_out: boolean;
  suggested_reorder_quantity: number;
}
export interface InventoryForecastResponse {
  method: string;
  lookback_days: number;
  horizon_days: number;
  items: InventoryForecastItem[];
  total: number;
}
export async function getInventoryForecast(
  lookback = 30,
  horizon = 14
): Promise<InventoryForecastResponse> {
  const response = await client.apiCall.invoke<InventoryForecastResponse>({
    url: `/api/v1/reports/inventory-forecast?lookback=${lookback}&horizon=${horizon}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

export interface DynamicPriceItem {
  product_id: number;
  name: string;
  name_ar?: string | null;
  on_hand: number;
  avg_daily_units: number;
  days_of_cover: number | null;
  signal: 'markup' | 'markdown';
  current_price: number;
  suggested_price: number;
  adjustment_pct: number;
}
export interface DynamicPricingResponse {
  method: string;
  lookback_days: number;
  low_cover_days: number;
  high_cover_days: number;
  items: DynamicPriceItem[];
  total: number;
}
export async function getDynamicPricing(lookback = 30): Promise<DynamicPricingResponse> {
  const response = await client.apiCall.invoke<DynamicPricingResponse>({
    url: `/api/v1/reports/dynamic-pricing?lookback=${lookback}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// ---- Peak-hours heatmap (#229 M9·Analytics) ----
// Completed sales bucketed into a day-of-week × hour-of-day grid — the raw
// material for a peak-hours heatmap. Only non-empty cells are returned (the grid
// is sparse); ``busiest`` names the hottest cell, or is null when there are no
// sales. day_of_week is 0=Sunday..6=Saturday. Mirrors the Pydantic models in
// backend/routers/features.py.
export interface PeakHoursCell {
  day_of_week: number; // 0=Sunday..6=Saturday
  hour: number; // 0..23
  order_count: number;
  revenue: number;
}
export interface PeakHoursResponse {
  method: string;
  lookback_days: number;
  total_orders: number;
  total_revenue: number;
  busiest: PeakHoursCell | null;
  cells: PeakHoursCell[];
}
export async function getPeakHours(lookback = 365): Promise<PeakHoursResponse> {
  const response = await client.apiCall.invoke<PeakHoursResponse>({
    url: `/api/v1/reports/peak-hours?lookback=${lookback}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// ---- Cohort retention (#229 M9·Analytics) ----
// Attributable customers grouped by the calendar month of their first purchase
// (their cohort), each tracked forward month by month for what fraction return —
// the retention triangle behind a cohort heatmap. cohorts are oldest-first; each
// cell's month_offset is months since the cohort month (0 = that month, always
// 100% retained). Mirrors the Pydantic models in backend/routers/features.py.
export interface CohortCell {
  month_offset: number; // 0 = the cohort's own month
  active_customers: number;
  retention_rate: number; // active_customers / cohort_size
}
export interface CohortRow {
  cohort_month: string; // YYYY-MM
  cohort_size: number;
  cells: CohortCell[];
}
export interface CohortRetentionResponse {
  method: string;
  lookback_days: number;
  total_customers: number;
  cohorts: CohortRow[];
}
export async function getCohortRetention(lookback = 365): Promise<CohortRetentionResponse> {
  const response = await client.apiCall.invoke<CohortRetentionResponse>({
    url: `/api/v1/reports/cohorts?lookback=${lookback}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// ---- Checkout conversion funnel (#229 M9·Analytics) ----
// "Of every ticket we open, how many convert to a kept sale, and where do we
// lose them?". A ticket walks three ordered stages, each read off the status
// composition of the window: started (opened) → completed (finalised sale) →
// retained (revenue kept). biggest_dropoff names the leakiest transition (null
// when there are no tickets).
export interface FunnelStage {
  stage: string; // started | completed | retained
  label: string;
  count: number;
  conversion_rate: number; // count / started (top of funnel)
  step_rate: number; // count / previous stage
}
export interface FunnelDropoff {
  from_stage: string;
  to_stage: string;
  lost: number;
  rate: number; // lost / from-stage count
}
export interface SalesFunnelResponse {
  method: string;
  lookback_days: number;
  total_tickets: number; // = the started stage count
  stages: FunnelStage[];
  biggest_dropoff: FunnelDropoff | null;
}
export async function getSalesFunnel(lookback = 30): Promise<SalesFunnelResponse> {
  const response = await client.apiCall.invoke<SalesFunnelResponse>({
    url: `/api/v1/reports/sales-funnel?lookback=${lookback}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// ---- Accounting/ERP sales-journal export (#230 Integrations) ----
// The window's selling activity as a balanced set of double-entry GL postings an
// accountant — or an ERP import — can book directly, keyed on stable
// account_code. Money received debits a tender account (cash → 1000, card/bank →
// 1010); VAT (2100), gratuities (2200) and net revenue (4000) are credited.
// Credit notes reverse the postings; the journal always balances.
export interface AccountingJournalLine {
  account_code: string; // stable GL code an ERP maps to its chart of accounts
  account_name: string;
  debit: number; // 0 when the account nets to the credit side
  credit: number; // 0 when the account nets to the debit side
}
export interface AccountingExportResponse {
  method: string; // "sales_journal"
  lookback_days: number;
  total_debit: number;
  total_credit: number;
  balanced: boolean; // total_debit == total_credit (within a cent)
  lines: AccountingJournalLine[];
}
export async function getAccountingExport(
  lookback = 30,
): Promise<AccountingExportResponse> {
  const response = await client.apiCall.invoke<AccountingExportResponse>({
    url: `/api/v1/reports/accounting-export?lookback=${lookback}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// ---- In-app assistant (#228 M9·AI) ----
// The conversational surface over the tenant's own data. This first slice is a
// rule-based intent router server-side; the client just passes the question and
// renders the grounded, self-describing answer. ``method`` names the engine
// ('rule_based' now; LLM-backed later) and ``intent`` how the question routed.
export interface AssistantAnswer {
  method: string;
  query: string;
  intent: string; // top_product | sales_today | average_order | sales_forecast | sales_trend | peak_hours | smart_reorder | dynamic_pricing | low_stock | unknown
  answer: string;
  data: Record<string, unknown>;
  suggestions: string[];
}
export async function askAssistant(question: string): Promise<AssistantAnswer> {
  const qs = new URLSearchParams({ q: question }).toString();
  const response = await client.apiCall.invoke<AssistantAnswer>({
    url: `/api/v1/assistant/query?${qs}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// ---- Product variants / matrix (INV-04, F-033) ----
// Each variant is a sellable SKU of a parent product with its own barcode, price
// and stock. Managed via the generic entity triad at /api/v1/entities/product_variants.
export interface ProductVariant {
  id: number;
  product_id: number;
  client_id?: number;
  name: string;
  attributes?: string;
  sku?: string;
  barcode?: string;
  price?: number;
  cost_price?: number;
  quantity?: number;
  is_active?: boolean;
}

export async function getProductVariants(productId: number): Promise<ProductVariant[]> {
  const response = await client.entities.product_variants.query<{ items: ProductVariant[] }>({
    query: { product_id: productId },
    limit: 200,
    sort: 'id',
  });
  return response.data?.items || [];
}

export async function createProductVariant(data: {
  product_id: number;
  client_id: number;
  name: string;
  attributes?: string;
  sku?: string;
  barcode?: string;
  price?: number;
  cost_price?: number;
  quantity?: number;
  is_active?: boolean;
}): Promise<ProductVariant> {
  const response = await client.entities.product_variants.create<ProductVariant>({ data });
  return response.data;
}

export async function updateProductVariant(
  variantId: number,
  data: Record<string, unknown>,
): Promise<ProductVariant> {
  const response = await client.entities.product_variants.update<ProductVariant>({
    id: variantId,
    data,
  });
  return response.data;
}

export async function deleteProductVariant(variantId: number) {
  const response = await client.entities.product_variants.delete({ id: variantId });
  return response.data;
}

// POS-06 / INV-04: resolve a scanned barcode to a product or a variant SKU.
export interface BarcodeResolution {
  kind: 'variant' | 'product' | 'none';
  product_id?: number;
  variant_id?: number;
  name: string;
  name_ar?: string;
  price: number;
  barcode?: string;
  quantity?: number;
  sku?: string;
  // ISSUE-230 (Integrations): a variable-measure *scale* barcode carries a value
  // the scan itself supplies. `scale_kind` is 'weight' (weighted product →
  // `scale_weight` kg is the line quantity) or 'price' (any other product →
  // `scale_price` is the line's total price, the scale having priced it).
  scale?: boolean;
  scale_kind?: 'weight' | 'price';
  scale_weight?: number;
  scale_price?: number;
}

export async function resolveBarcode(barcode: string): Promise<BarcodeResolution> {
  const response = await client.apiCall.invoke<BarcodeResolution>({
    url: `/api/v1/pos/resolve-barcode?barcode=${encodeURIComponent(barcode)}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Inventory Management
export async function deductInventory(items: { product_id: number; quantity: number }[]) {
  const response = await client.apiCall.invoke({
    url: '/api/v1/inventory/deduct',
    method: 'POST',
    data: { items },
  });
  return response.data;
}

export async function getInventoryAlerts() {
  const response = await client.apiCall.invoke({
    url: '/api/v1/inventory/alerts',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Account / security
export async function changePassword(currentPassword: string, newPassword: string) {
  const response = await client.apiCall.invoke({
    url: '/api/v1/users/change-password',
    method: 'POST',
    data: { current_password: currentPassword, new_password: newPassword },
  });
  return response.data;
}

// Self-service password reset (ISSUE-082 backend / #199 UI).
export interface PasswordResetRequestResult {
  success: boolean;
  message: string;
  // Populated only in dev / no-SMTP mode so the flow is usable without a real
  // mailbox; null in production. Never assume it is present.
  reset_token?: string | null;
}

/**
 * Request a password-reset link for `email`. Always resolves 200 regardless of
 * whether the address maps to an account — the backend is anti-enumeration, so
 * the caller must show the same neutral confirmation either way.
 */
export async function requestPasswordReset(email: string): Promise<PasswordResetRequestResult> {
  const response = await client.apiCall.invoke<PasswordResetRequestResult>({
    url: '/api/v1/auth/password/forgot',
    method: 'POST',
    data: { email },
  });
  return response.data;
}

/**
 * Complete a password reset with a single-use token from the emailed link.
 * Throws on an invalid/expired token or a password that fails complexity — the
 * caller surfaces `response.data.detail`.
 */
export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<{ success: boolean; message: string }> {
  const response = await client.apiCall.invoke<{ success: boolean; message: string }>({
    url: '/api/v1/auth/password/reset',
    method: 'POST',
    data: { token, new_password: newPassword },
  });
  return response.data;
}

// Active login sessions for the current user (auth/sessions). Used to show the
// real current-session details on the profile instead of a hardcoded row.
export interface SessionInfo {
  id: string;
  current: boolean;
  user_agent?: string | null;
  ip_address?: string | null;
  created_at?: string | null;
  last_used_at?: string | null;
}

export async function getActiveSessions() {
  const response = await client.apiCall.invoke({
    url: '/api/v1/auth/sessions',
    method: 'GET',
    data: {},
  });
  return response.data as { sessions: SessionInfo[] };
}

/** Revoke one of the caller's sessions by id (#202, parity #2). */
export async function revokeSession(sessionId: string) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/auth/sessions/${sessionId}`,
    method: 'DELETE',
    data: {},
  });
  return response.data as { success: boolean; revoked: number };
}

// ---- MFA (TOTP) — #202 (parity #1). Backend ISSUE-081. ----
export interface MfaStatus {
  enabled: boolean;
  recovery_codes_remaining: number;
}

export interface MfaEnrollResult {
  secret: string; // base32 shared secret
  otpauth_uri: string; // otpauth://totp/... for QR provisioning
  enabled: boolean;
}

export interface MfaActivateResult {
  enabled: boolean;
  recovery_codes: string[]; // shown once — the user must save these
}

/** Whether MFA is active for the caller (+ remaining recovery codes). */
export async function getMfaStatus(): Promise<MfaStatus> {
  const response = await client.apiCall.invoke<MfaStatus>({
    url: '/api/v1/auth/mfa/status',
    method: 'GET',
    data: {},
  });
  return response.data;
}

/** Begin TOTP enrollment: mint a pending secret + provisioning URI. */
export async function enrollMfa(): Promise<MfaEnrollResult> {
  const response = await client.apiCall.invoke<MfaEnrollResult>({
    url: '/api/v1/auth/mfa/enroll',
    method: 'POST',
    data: {},
  });
  return response.data;
}

/** Confirm enrollment with a code; enables MFA and returns recovery codes. */
export async function activateMfa(code: string): Promise<MfaActivateResult> {
  const response = await client.apiCall.invoke<MfaActivateResult>({
    url: '/api/v1/auth/mfa/activate',
    method: 'POST',
    data: { code },
  });
  return response.data;
}

// Per-user profile + notification preferences (ISSUE-078, persisted server-side)
export interface NotificationPrefs {
  email_alerts: boolean;
  whatsapp_alerts: boolean;
  push_alerts: boolean;
  low_stock_alerts: boolean;
  daily_summary: boolean;
  transaction_alerts: boolean;
}

export interface UserPreferences {
  display_name: string | null;
  notification_prefs: NotificationPrefs;
}

export async function getUserPreferences(): Promise<UserPreferences> {
  const response = await client.apiCall.invoke<UserPreferences>({
    url: '/api/v1/users/preferences',
    method: 'GET',
    data: {},
  });
  return response.data;
}

export async function saveUserPreferences(prefs: {
  display_name?: string | null;
  notification_prefs?: NotificationPrefs;
}): Promise<UserPreferences> {
  const response = await client.apiCall.invoke<UserPreferences>({
    url: '/api/v1/users/preferences',
    method: 'PUT',
    data: prefs,
  });
  return response.data;
}

// Account profile (#203, parity #4) — the user's own identity fields, editable on
// the profile screen. Distinct from UserPreferences (display_name + notification
// channels): this is the account record (name/email/phone) behind /users/profile.
export interface UserAccountProfile {
  id: string;
  email: string;
  name: string | null;
  phone: string | null;
  role: string;
}

export async function getUserProfile(): Promise<UserAccountProfile> {
  const response = await client.apiCall.invoke<UserAccountProfile>({
    url: '/api/v1/users/profile',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// PATCH-like: only the fields passed are sent, so the backend leaves omitted
// fields untouched. Throws on a 409 (email already in use); the caller surfaces
// `response.data.detail`.
export async function updateUserProfile(fields: {
  name?: string;
  email?: string;
  phone?: string;
}): Promise<UserAccountProfile> {
  const response = await client.apiCall.invoke<UserAccountProfile>({
    url: '/api/v1/users/profile',
    method: 'PUT',
    data: fields,
  });
  return response.data;
}

// Merchant store settings (ISSUE-079) — the store-level identity + operational
// defaults that feed every receipt/invoice: VAT/CR numbers, receipt footer, the
// branch profile and business hours. Persisted server-side at
// /api/v1/store-settings (seller name + VAT written through to the client row).
export interface BusinessHours {
  day: string;
  open: string;
  close: string;
  closed: boolean;
}

export interface StoreSettings {
  store_name: string | null;
  vat_number: string | null;
  cr_number: string | null;
  receipt_footer: string | null;
  address: string | null;
  city: string | null;
  phone: string | null;
  business_hours: BusinessHours[] | null;
}

export async function getStoreSettings(): Promise<StoreSettings> {
  const response = await client.apiCall.invoke<StoreSettings>({
    url: '/api/v1/store-settings',
    method: 'GET',
    data: {},
  });
  return response.data;
}

export async function saveStoreSettings(
  settings: Partial<StoreSettings>
): Promise<StoreSettings> {
  const response = await client.apiCall.invoke<StoreSettings>({
    url: '/api/v1/store-settings',
    method: 'PUT',
    data: settings,
  });
  return response.data;
}

// Client self-service profile (CL-02 first-login business type)
export type BusinessType = 'retail' | 'restaurant' | 'both';

export interface ClientProfile {
  client_id: number;
  business_name: string;
  business_type: BusinessType;
  language_preference: string;
}

// Read the caller's own client profile (used to pre-select business type on the
// first-login setup screen). 403s for non-clients.
export async function getClientProfile(): Promise<ClientProfile> {
  const response = await client.apiCall.invoke<ClientProfile>({
    url: '/api/v1/tenant/client/profile',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// CL-02: the client confirms/sets their own business type during first-login.
// Drives retail vs restaurant POS mode; scoped server-side to the caller's own row.
export async function setBusinessType(businessType: BusinessType): Promise<ClientProfile> {
  const response = await client.apiCall.invoke<ClientProfile>({
    url: '/api/v1/tenant/client/business-type',
    method: 'POST',
    data: { business_type: businessType },
  });
  return response.data;
}

// Agent Branding
export async function updateBranding(data: {
  logo_url?: string;
  primary_color?: string;
  secondary_color?: string;
  font_family?: string;
  button_radius?: string;
  default_language?: string;
  // AG-05 / AG-06 deep white-label.
  custom_domain?: string;
  email_template_subject?: string;
  email_template_body?: string;
}) {
  const response = await client.apiCall.invoke({
    url: '/api/v1/branding/update',
    method: 'PUT',
    data,
  });
  return response.data;
}

// AG-05: resolve an agent's branding from a custom domain (public, pre-login) so
// the merchant login/funnel is served under the agent's brand. Returns null when
// the host isn't claimed (the caller falls back to the platform default theme).
export async function getBrandingByDomain(domain: string) {
  try {
    const response = await client.apiCall.invoke({
      url: `/api/v1/tenant/branding/by-domain?domain=${encodeURIComponent(domain)}`,
      method: 'GET',
      data: {},
    });
    return response.data;
  } catch {
    return null;
  }
}

// Reports & Analytics
export async function getSalesSummary(period: string) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/reports/sales-summary?period=${period}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

export async function getTopProducts(limit = 10) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/reports/top-products?limit=${limit}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

export async function exportCSV() {
  const response = await client.apiCall.invoke({
    url: '/api/v1/reports/export-csv',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// RPT-03: payment-method breakdown for the period (cash/Mada/card/wallet/BNPL/
// loyalty) from the real captured tenders, with refunds-to-origin netted out.
export async function getPaymentBreakdown(days = 30) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/reports/payment-breakdown?days=${days}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// FIN-02: accounting journal / general-ledger export for the period. A balanced
// double-entry journal (sales / VAT / COGS / inventory / payments-by-tender) the
// bookkeeper imports into Zoho/QuickBooks/Odoo. Returns structured lines + a CSV.
export interface JournalLine {
  account_code: string;
  account: string;
  description: string;
  debit: number;
  credit: number;
}

export interface JournalExport {
  days: number;
  from_date: string;
  to_date: string;
  lines: JournalLine[];
  total_debit: number;
  total_credit: number;
  balanced: boolean;
  csv_content: string;
}

export async function getJournalExport(days = 30): Promise<JournalExport> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/reports/journal-export?days=${days}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// RPT-04 / INV-09 (F-068): profit / COGS / margin report + dead-stock list.
// Each row carries revenue, COGS, gross profit and margin %; COGS uses the cost
// snapshotted onto the sale line at sale time so historical margin is stable.
export interface MarginRow {
  key: string;
  name: string;
  category: string | null;
  qty_sold: number;
  revenue: number;
  cogs: number;
  gross_profit: number;
  margin_pct: number;
}

export interface DeadStockItem {
  product_id: number;
  name: string;
  category: string | null;
  quantity: number;
  cost_price: number;
  stock_value: number;
}

export interface ProfitMarginReport {
  days: number;
  dead_stock_days: number;
  from_date: string;
  to_date: string;
  by_item: MarginRow[];
  by_category: MarginRow[];
  dead_stock: DeadStockItem[];
  totals: MarginRow;
  csv_content: string;
}

export async function getProfitMarginReport(days = 30, deadStockDays = 30): Promise<ProfitMarginReport> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/reports/profit-margin?days=${days}&dead_stock_days=${deadStockDays}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// RPT-05 (F-069): VAT / tax summary by rate — the ZATCA VAT-return boxes.
// Each bucket carries its taxable base + VAT; credit notes net the VAT down so
// net_vat = vat_collected − vat_reversed.
export interface VatBucket {
  key: string;
  label: string;
  rate: number;
  taxable_base: number;
  vat_amount: number;
}

export interface VatSummaryReport {
  days: number;
  from_date: string;
  to_date: string;
  buckets: VatBucket[];
  total_taxable_base: number;
  vat_collected: number;
  vat_reversed: number;
  net_vat: number;
  csv_content: string;
}

export async function getVatSummaryReport(days = 30): Promise<VatSummaryReport> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/reports/vat-summary?days=${days}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// RPT-07 / INV-09 (F-070): inventory report — on-hand valued at COST (not sale
// price) per product and per branch, plus a movement ledger (PO receipts, branch
// transfers, counts/adjustments) over a trailing window.
export interface InventoryValuationRow {
  product_id: number;
  name: string;
  category: string | null;
  quantity: number;
  cost_price: number;
  stock_value: number;
}

export interface BranchValuationRow {
  branch_id: number;
  branch_name: string | null;
  quantity: number;
  stock_value: number;
}

export interface InventoryMovementRow {
  date: string;
  type: string; // "receipt" | "transfer" | "adjustment"
  product_id: number | null;
  product_name: string | null;
  quantity: number;
  reference: string | null;
  note: string | null;
}

export interface InventoryReport {
  days: number;
  from_date: string;
  to_date: string;
  by_product: InventoryValuationRow[];
  by_branch: BranchValuationRow[];
  total_quantity: number;
  total_valuation: number;
  movements: InventoryMovementRow[];
  csv_content: string;
}

export async function getInventoryReport(days = 30): Promise<InventoryReport> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/reports/inventory?days=${days}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// RPT-08 (F-071): refund/void report — each refund (credit note) and void over a
// window with actor, reason, amount, timestamp. A void's actor/reason/when come
// from its audit event; a refund's from the credit-note transaction.
export interface RefundVoidRow {
  type: string; // "refund" | "void"
  transaction_id: number;
  invoice_number: string | null;
  actor_id: string | null;
  actor: string | null;
  reason: string | null;
  amount: number;
  timestamp: string | null;
  original_invoice: string | null;
}

export interface RefundVoidReport {
  days: number;
  from_date: string;
  to_date: string;
  rows: RefundVoidRow[];
  refund_count: number;
  refund_total: number;
  void_count: number;
  void_total: number;
  csv_content: string;
}

export async function getRefundVoidReport(days = 30): Promise<RefundVoidReport> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/reports/refunds-voids?days=${days}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// RPT-08 (F-071): discount report — each discounted sale over a window with actor,
// the applied promo code (is_manual for a codeless override), amount, timestamp.
export interface DiscountRow {
  transaction_id: number;
  invoice_number: string | null;
  actor_id: string | null;
  actor: string | null;
  code: string | null;
  is_manual: boolean;
  discount_amount: number;
  subtotal: number;
  timestamp: string | null;
}

export interface DiscountReport {
  days: number;
  from_date: string;
  to_date: string;
  rows: DiscountRow[];
  discount_count: number;
  discount_total: number;
  csv_content: string;
}

export async function getDiscountReport(days = 30): Promise<DiscountReport> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/reports/discounts?days=${days}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// M9 (F-068): Profit & Loss statement — net revenue (ex-VAT) − COGS (rolled up
// from the bill of materials) − operating expenses = net profit, for the window.
export interface PnlExpenseRow {
  category: string;
  amount: number;
}

export interface PnlReport {
  days: number;
  from_date: string;
  to_date: string;
  gross_sales: number;
  discounts: number;
  net_revenue: number;
  vat: number;
  cogs: number;
  gross_profit: number;
  gross_margin_pct: number;
  expenses: PnlExpenseRow[];
  total_expenses: number;
  net_profit: number;
  net_margin_pct: number;
  csv_content: string;
}

export async function getPnlReport(days = 30): Promise<PnlReport> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/reports/pnl?days=${days}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// M9 (F-068): Cash Flow statement — cash-basis receipts (net of refunds) − cash
// operating expenses = net operating cash flow, with a receipts-by-tender split
// and the drawer movement totals (pay-in/pay-out/cash-drop) for traceability.
export interface CashFlowLine {
  label: string;
  amount: number;
}

export interface CashFlowTender {
  tender_type: string;
  collected: number;
  refunds: number;
  net: number;
}

export interface CashFlowDrawer {
  pay_in: number;
  pay_out: number;
  cash_drop: number;
  net_drawer: number;
}

export interface CashFlowReport {
  days: number;
  from_date: string;
  to_date: string;
  receipts_collected: number;
  receipts_refunds: number;
  receipts_net: number;
  by_tender: CashFlowTender[];
  expenses: PnlExpenseRow[];
  total_expenses: number;
  inflows: CashFlowLine[];
  outflows: CashFlowLine[];
  net_cash_flow: number;
  drawer_movements: CashFlowDrawer;
  csv_content: string;
}

export async function getCashFlowReport(days = 30): Promise<CashFlowReport> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/reports/cash-flow?days=${days}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// RPT-06 / PRN-05: fetch a shift's Z-report (closed shift) / X-report (open) —
// sales by tender, VAT, discounts, voids, refunds + cash variance. Omit shiftId
// for the current open shift.
export async function getZReport(shiftId?: number) {
  const query = shiftId != null ? `?shift_id=${shiftId}` : '';
  const response = await client.apiCall.invoke({
    url: `/api/v1/reports/zreport${query}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Open the always-Arabic Z/X-report printable (PRN-05) in a print window. The
// document is fetched with the auth token attached, then written into a new
// window for print-to-PDF (window.open alone can't send the Bearer header).
export async function printZReport(shiftId?: number) {
  const query = shiftId != null ? `?shift_id=${shiftId}` : '';
  const blob = await getBlob(`/api/v1/reports/zreport/document${query}`);
  const html = await blob.text();
  const win = window.open('', '_blank');
  if (!win) return;
  win.document.open();
  win.document.write(html);
  win.document.close();
  win.focus();
  win.print();
}

// Cash drawer movements (FIN-04 / POS-09): pay-in / pay-out / cash-drop recorded
// against the open shift, folded into the drawer reconciliation and the Z/X-report.
export type CashMovementType = 'pay_in' | 'pay_out' | 'cash_drop';

export interface CashMovement {
  id: number;
  shift_id: number;
  movement_type: CashMovementType;
  amount: number;
  reason?: string | null;
  created_at?: string | null;
}

export interface CashMovementResult {
  id: number;
  shift_id: number;
  movement_type: CashMovementType;
  amount: number;
  reason?: string | null;
  expected_cash: number;
  pay_in: number;
  pay_out: number;
  cash_drops: number;
}

export interface CashMovementsList {
  movements: CashMovement[];
  total: number;
  pay_in: number;
  pay_out: number;
  cash_drops: number;
}

export async function recordCashMovement(data: {
  movement_type: CashMovementType;
  amount: number;
  reason?: string;
}): Promise<CashMovementResult> {
  const response = await client.apiCall.invoke({
    url: '/api/v1/production/shifts/movements',
    method: 'POST',
    data,
  });
  return response.data;
}

export async function getCashMovements(shiftId?: number): Promise<CashMovementsList> {
  const query = shiftId != null ? `?shift_id=${shiftId}` : '';
  const response = await client.apiCall.invoke({
    url: `/api/v1/production/shifts/movements${query}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Notifications
export async function getNotifications() {
  const response = await client.apiCall.invoke({
    url: '/api/v1/notifications/list',
    method: 'GET',
    data: {},
  });
  // The backend returns { items, unread_count }; the page reads `notifications`.
  // Map it here so the feed actually renders (F-052 — the field mismatch meant
  // the page always showed empty regardless of the alerts returned).
  const data = response.data || {};
  return { ...data, notifications: data.items || [] };
}

export async function markNotificationRead(notificationId: string) {
  const response = await client.apiCall.invoke({
    url: '/api/v1/notifications/mark-read',
    method: 'POST',
    data: { notification_id: notificationId },
  });
  return response.data;
}

// Operator-composed notification (M10 / parity #8, ISSUE-214). Sends over the
// chosen channel; a future `scheduled_at` (ISO string) defers delivery and the
// server acknowledges it as `scheduled` rather than `sent`.
export type NotificationChannel = 'email' | 'whatsapp' | 'push';

export interface ComposeNotificationInput {
  channel: NotificationChannel;
  to: string;
  subject?: string;
  body: string;
  scheduled_at?: string | null;
}

export interface ComposeNotificationResult {
  channel: NotificationChannel;
  to: string;
  subject: string;
  status: string; // sent | logged | scheduled
  scheduled_at?: string;
  delivered?: boolean;
  message_id?: string;
}

export async function sendNotification(
  input: ComposeNotificationInput,
): Promise<ComposeNotificationResult> {
  const response = await client.apiCall.invoke<ComposeNotificationResult>({
    url: '/api/v1/production/notifications/send',
    method: 'POST',
    data: input,
  });
  return response.data;
}

// Create Agent (Master Admin)
export interface CreatedAgent {
  id: number;
  company_name: string;
  email: string;
  phone?: string;
  package_type: number;
  used_slots: number;
  is_active: boolean;
  temp_password: string;
}

export async function createAgent(data: {
  company_name: string;
  email: string;
  phone?: string;
  package_id?: number;
  package_type?: string;
}): Promise<CreatedAgent> {
  const response = await client.apiCall.invoke<CreatedAgent>({
    url: '/api/v1/tenant/master/agents',
    method: 'POST',
    data,
  });
  return response.data;
}

// Toggle Client Status (Agent)
export async function toggleClient(clientId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/tenant/agent/clients/${clientId}/toggle`,
    method: 'POST',
    data: {},
  });
  return response.data;
}

// ZA-09 (F-022): agent toggles ZATCA e-invoicing on/off for one of their own
// clients. The sale path honors clients.zatca_enabled — off means simplified
// non-tax receipts (no stamp/QR, no fiscal document).
export async function setClientZatca(clientId: number): Promise<{ success: boolean; zatca_enabled: boolean }> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/tenant/agent/clients/${clientId}/zatca`,
    method: 'POST',
    data: {},
  });
  return response.data;
}

export interface ResetPasswordResult {
  success: boolean;
  client_id: number;
  email: string;
  temp_password: string;
  must_change_password: boolean;
  email_delivered: boolean;
}

// Agent: reset the password of one of their own client merchants (RSL-06). Returns
// a one-time temp password (force-reset on next login) for the agent to relay.
export async function resetClientPassword(clientId: number): Promise<ResetPasswordResult> {
  const response = await client.apiCall.invoke<ResetPasswordResult>({
    url: `/api/v1/tenant/agent/clients/${clientId}/reset-password`,
    method: 'POST',
    data: {},
  });
  return response.data;
}

// ---- Merchant lifecycle (M8 / issue-215): archive/restore/transfer/export/delete ----

export interface MerchantLifecycleResult {
  success: boolean;
  client_id: number;
  archived_at?: string | null;
}

// Agent: archive a merchant — retires it without data loss, frees its slot and
// blocks its login. Reversed by restoreClient.
export async function archiveClient(clientId: number): Promise<MerchantLifecycleResult> {
  const response = await client.apiCall.invoke<MerchantLifecycleResult>({
    url: `/api/v1/tenant/agent/clients/${clientId}/archive`,
    method: 'POST',
    data: {},
  });
  return response.data;
}

// Agent: restore an archived merchant back into the active book (re-takes a slot).
export async function restoreClient(clientId: number): Promise<MerchantLifecycleResult> {
  const response = await client.apiCall.invoke<MerchantLifecycleResult>({
    url: `/api/v1/tenant/agent/clients/${clientId}/restore`,
    method: 'POST',
    data: {},
  });
  return response.data;
}

export interface TransferClientResult {
  success: boolean;
  client_id: number;
  from_agent_id: number;
  to_agent_id: number;
}

// Agent: transfer a merchant to another agent (by the destination agent's email).
// Changes the owning agent_id; the merchant's catalog/customers/sales follow.
export async function transferClient(
  clientId: number,
  targetAgentEmail: string,
): Promise<TransferClientResult> {
  const response = await client.apiCall.invoke<TransferClientResult>({
    url: `/api/v1/tenant/agent/clients/${clientId}/transfer`,
    method: 'POST',
    data: { target_agent_email: targetAgentEmail },
  });
  return response.data;
}

// Agent: download a portable JSON snapshot of a merchant (PDPL data-portability).
export async function exportClientData(clientId: number): Promise<unknown> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/tenant/agent/clients/${clientId}/export`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Agent: permanently delete an archived merchant once its retention window lapses.
export async function deleteClient(
  clientId: number,
): Promise<{ success: boolean; client_id: number; deleted: boolean }> {
  const response = await client.apiCall.invoke<{ success: boolean; client_id: number; deleted: boolean }>({
    url: `/api/v1/tenant/agent/clients/${clientId}`,
    method: 'DELETE',
    data: {},
  });
  return response.data;
}

// Package Management (Master Admin)
export async function getPackagesList() {
  const response = await client.apiCall.invoke({
    url: '/api/v1/packages/list',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// #236 (A3): how many agents are still on a package, so deactivating an in-use
// one can warn with the affected-agents count/consequence before it runs.
export interface PackageImpact {
  package_id: number;
  agent_count: number;
  active_agent_count: number;
}
export async function getPackageImpact(packageId: number): Promise<PackageImpact> {
  const response = await client.apiCall.invoke<PackageImpact>({
    url: `/api/v1/packages/${packageId}/impact`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

export async function createPackage(data: {
  name: string;
  client_slots: number;
  wholesale_price: number;
  suggested_retail_price: number;
  // MA-07: the feature-entitlement tier (enabled feature keys). Omit/empty for
  // no restriction.
  features?: string[];
}) {
  const response = await client.apiCall.invoke({
    url: '/api/v1/packages/create',
    method: 'POST',
    data,
  });
  return response.data;
}

export async function updatePackage(packageId: number, data: Record<string, unknown>) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/packages/${packageId}`,
    method: 'PUT',
    data,
  });
  return response.data;
}

export async function deletePackage(packageId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/packages/${packageId}`,
    method: 'DELETE',
    data: {},
  });
  return response.data;
}

// Customer Management
export async function getCustomers() {
  const response = await client.entities.customers.query({
    query: {},
    limit: 200,
  });
  return response.data;
}

export async function createCustomer(data: {
  name: string;
  phone?: string;
  email?: string;
  vat_number?: string;
  address?: string;
  notes?: string;
  marketing_consent?: boolean;
  tags?: string[]; // segmentation labels (CRM-04 / F-039)
}) {
  const response = await client.entities.customers.create({ data });
  return response.data;
}

// CRM-04 (F-039): computed lifetime value + RFM-lite for one customer.
export interface CustomerInsights {
  customer_id: number;
  gross_sales: number;
  refunds: number;
  lifetime_value: number;
  visit_count: number;
  average_basket: number;
  first_purchase_at?: string | null;
  last_purchase_at?: string | null;
  recency_days?: number | null;
  segment: string; // new | regular | vip | at_risk
}

export async function getCustomerInsights(id: string): Promise<CustomerInsights> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/entities/customers/${id}/insights`,
    method: 'GET',
  });
  return response.data as CustomerInsights;
}

export async function updateCustomer(id: string, data: Record<string, unknown>) {
  const response = await client.entities.customers.update({ id, data });
  return response.data;
}

export async function deleteCustomer(id: string) {
  await client.entities.customers.delete({ id });
}

// PDPL data-subject rights (SEC-05 / F-050).
export interface CustomerDataExport {
  customer: Record<string, unknown>;
  transactions: {
    id: number;
    invoice_number: string;
    total_amount?: number;
    status?: string;
    created_at?: string;
  }[];
  transaction_count: number;
  retention_notice: string;
}

// PDPL right-to-access/portability: everything held about one customer.
export async function exportCustomerData(id: string): Promise<CustomerDataExport> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/entities/customers/${id}/data-export`,
    method: 'GET',
  });
  return response.data as CustomerDataExport;
}

// PDPL right-to-erasure: tombstone the customer's PII (row retained so fiscal
// records stay intact). Returns the tombstoned customer.
export async function eraseCustomerData(id: string) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/entities/customers/${id}/erase`,
    method: 'POST',
  });
  return response.data;
}

// Procurement (Phase 6 / F-034): receive a purchase order. The backend lands
// stock in the per-branch ledger when `branch_id` is given (else the client-level
// aggregate), supports partial receipts via `lines` (the PO becomes
// 'partially_received' while a balance remains), re-weights cost as a moving
// average, and is idempotent once fully received. Omit options to receive the
// full remaining balance into client-level stock (legacy behavior).
export async function receivePurchaseOrder(
  poId: number,
  options?: { branch_id?: number; lines?: { product_id: number; quantity: number; cost?: number }[] },
) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/entities/purchase_orders/${poId}/receive`,
    method: 'POST',
    data: options || {},
  });
  return response.data;
}

// Branches (multi-branch). Used to tag POS sales to a branch and for reports.
export async function getBranches() {
  const response = await client.entities.branches.query({ query: {}, limit: 200 });
  return response.data;
}

// ----- ISSUE-047: saved-printer registry + per-station routing (H26/U5.2) -----
export type PrinterRole = 'receipt' | 'kot';

export interface Printer {
  id: number;
  name: string;
  role: PrinterRole;
  station_id?: number | null;
  device_id?: string | null;
  paper_size?: string | null;
  is_default?: boolean | null;
  status?: string | null;
}

export async function listPrinters(): Promise<Printer[]> {
  const response = await client.apiCall.invoke<Printer[]>({
    url: '/api/v1/printers',
    method: 'GET',
  });
  return response.data;
}

export async function createPrinter(data: {
  name: string;
  role: PrinterRole;
  station_id?: number | null;
  device_id?: string | null;
  paper_size?: string | null;
  is_default?: boolean;
}): Promise<Printer> {
  const response = await client.apiCall.invoke<Printer>({
    url: '/api/v1/printers',
    method: 'POST',
    data,
  });
  return response.data;
}

export async function updatePrinter(
  id: number,
  data: Partial<{
    name: string;
    role: PrinterRole;
    station_id: number | null;
    device_id: string | null;
    paper_size: string | null;
    is_default: boolean;
    status: string;
  }>,
): Promise<Printer> {
  const response = await client.apiCall.invoke<Printer>({
    url: `/api/v1/printers/${id}`,
    method: 'PUT',
    data,
  });
  return response.data;
}

export async function deletePrinter(id: number): Promise<void> {
  await client.apiCall.invoke({
    url: `/api/v1/printers/${id}`,
    method: 'DELETE',
    data: {},
  });
}

// ISSUE-048 (H26): the merchant's receipt-template knobs the ESC/POS renderer
// honors at print time (#45 wired `load_default_template` into build_receipt /
// build_kot). The designer UI edits these; the default template (`is_default`)
// is the one the renderer loads.
export type FontSize = 'small' | 'medium' | 'large';

export interface ReceiptTemplate {
  id: number;
  name: string;
  header_text?: string | null;
  footer_text?: string | null;
  show_logo?: boolean | null;
  show_vat_details?: boolean | null;
  show_qr_code?: boolean | null;
  paper_size?: string | null;
  font_size?: string | null;
  is_default?: boolean | null;
}

export interface ReceiptTemplateInput {
  name: string;
  header_text?: string | null;
  footer_text?: string | null;
  show_logo?: boolean;
  show_vat_details?: boolean;
  show_qr_code?: boolean;
  paper_size?: string;
  font_size?: string;
  is_default?: boolean;
}

// List the merchant's receipt templates (owner-scoped). Unwraps the paginated
// entity envelope to the plain array the designer works with.
export async function listReceiptTemplates(): Promise<ReceiptTemplate[]> {
  const response = await client.apiCall.invoke<{ items: ReceiptTemplate[] }>({
    url: '/api/v1/entities/receipt_templates',
    method: 'GET',
  });
  return response.data?.items ?? [];
}

export async function createReceiptTemplate(
  data: ReceiptTemplateInput,
): Promise<ReceiptTemplate> {
  const response = await client.apiCall.invoke<ReceiptTemplate>({
    url: '/api/v1/entities/receipt_templates',
    method: 'POST',
    data,
  });
  return response.data;
}

export async function updateReceiptTemplate(
  id: number,
  data: Partial<ReceiptTemplateInput>,
): Promise<ReceiptTemplate> {
  const response = await client.apiCall.invoke<ReceiptTemplate>({
    url: `/api/v1/entities/receipt_templates/${id}`,
    method: 'PUT',
    data,
  });
  return response.data;
}

// Designate THE main branch (exactly one). The backend unsets the previous
// main atomically, so callers just reload after this resolves (ISSUE-062).
export async function setMainBranch(branchId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/entities/branches/${branchId}/set-main`,
    method: 'POST',
    data: {},
  });
  return response.data;
}

// Per-branch stock ledger (Phase 6). Set/list a branch's stock allocation.
export async function getBranchStock(branchId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/branches/${branchId}/stock`,
    method: 'GET',
  });
  return response.data;
}

export async function setBranchStock(branchId: number, productId: number, quantity: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/branches/${branchId}/stock`,
    method: 'PUT',
    data: { product_id: productId, quantity },
  });
  return response.data;
}

// Per-branch price overrides (#220 multi-branch: branch-level pricing). A branch
// may carry its own price for a product; absent an override the chain-wide base
// price applies. `resolveBranchPrice` returns the effective price for the POS.
export interface BranchPriceItem {
  product_id: number;
  price: number;
}

export interface BranchPriceResolution {
  product_id: number;
  branch_id: number;
  price: number;
  is_override: boolean;
}

export async function getBranchPrices(branchId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/branches/${branchId}/prices`,
    method: 'GET',
  });
  return response.data as { branch_id: number; items: BranchPriceItem[]; total: number };
}

export async function setBranchPrice(branchId: number, productId: number, price: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/branches/${branchId}/prices`,
    method: 'PUT',
    data: { product_id: productId, price },
  });
  return response.data;
}

export async function deleteBranchPrice(branchId: number, productId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/branches/${branchId}/prices/${productId}`,
    method: 'DELETE',
  });
  return response.data;
}

export async function resolveBranchPrice(branchId: number, productId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/branches/${branchId}/prices/resolve?product_id=${productId}`,
    method: 'GET',
  });
  return response.data as BranchPriceResolution;
}

// Per-branch VAT rate overrides (#220 multi-branch: branch-level tax). A branch
// may carry its own VAT rate; absent an override the chain-wide effective rate
// applies (master global rate, else the statutory default). `resolveBranchTaxRate`
// returns the effective rate and whether it is a branch override.
export interface BranchTaxRateResolution {
  branch_id: number;
  vat_rate: number;
  is_override: boolean;
}

export async function resolveBranchTaxRate(branchId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/branches/${branchId}/tax-rate`,
    method: 'GET',
  });
  return response.data as BranchTaxRateResolution;
}

export async function setBranchTaxRate(branchId: number, vatRate: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/branches/${branchId}/tax-rate`,
    method: 'PUT',
    data: { vat_rate: vatRate },
  });
  return response.data as BranchTaxRateResolution;
}

export async function deleteBranchTaxRate(branchId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/branches/${branchId}/tax-rate`,
    method: 'DELETE',
  });
  return response.data;
}

// Per-branch promotion opt-outs (#220 multi-branch: branch-level promotions). A
// chain's auto-applied promotions run at every branch by default; a branch may
// opt out of a specific promotion. `resolveBranchPromotions` returns the active
// promotions effective at the branch and the ids it has disabled.
export interface BranchPromotionSummary {
  promotion_id: number;
  name: string;
  kind: string;
}

export interface BranchPromotionResolution {
  branch_id: number;
  promotions: BranchPromotionSummary[];
  disabled_promotion_ids: number[];
}

export async function resolveBranchPromotions(branchId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/branches/${branchId}/promotions/resolve`,
    method: 'GET',
  });
  return response.data as BranchPromotionResolution;
}

export async function setBranchPromotion(
  branchId: number,
  promotionId: number,
  isEnabled: boolean,
) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/branches/${branchId}/promotions/${promotionId}`,
    method: 'PUT',
    data: { is_enabled: isEnabled },
  });
  return response.data as {
    branch_id: number;
    promotion_id: number;
    is_enabled: boolean;
  };
}

export async function deleteBranchPromotion(branchId: number, promotionId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/branches/${branchId}/promotions/${promotionId}`,
    method: 'DELETE',
  });
  return response.data;
}

// Cross-branch sales reporting (#220 multi-branch). Rolls each branch's net sales
// and sale count up side by side for the chain; refunds (credit notes) net out and
// held/voided rows are excluded. Optional ISO start/end bound the window.
export interface CrossBranchSalesRow {
  branch_id: number | null;
  branch_name: string;
  net_sales: number;
  sales_count: number;
}

export interface CrossBranchSalesSummary {
  branches: CrossBranchSalesRow[];
  total_net_sales: number;
  total_sales_count: number;
}

export async function getCrossBranchSales(start?: string, end?: string) {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  const qs = params.toString();
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/reports/cross-branch-sales${qs ? `?${qs}` : ''}`,
    method: 'GET',
  });
  return response.data as CrossBranchSalesSummary;
}

// Per-branch *variant* stock ledger (parity #5, INV-03 × INV-04). Each variant SKU
// carries its own per-branch allocation, separate from the parent product's stock.
export interface BranchVariantStockItem {
  variant_id: number;
  quantity: number;
}

export interface BranchVariantStock {
  branch_id: number;
  items: BranchVariantStockItem[];
  total: number;
}

export async function getBranchVariantStock(branchId: number): Promise<BranchVariantStock> {
  const response = await client.apiCall.invoke<BranchVariantStock>({
    url: `/api/v1/pos/branches/${branchId}/variant-stock`,
    method: 'GET',
  });
  return response.data;
}

export async function setBranchVariantStock(branchId: number, variantId: number, quantity: number) {
  const response = await client.apiCall.invoke<BranchVariantStockItem & { branch_id: number }>({
    url: `/api/v1/pos/branches/${branchId}/variant-stock`,
    method: 'PUT',
    data: { variant_id: variantId, quantity },
  });
  return response.data;
}

// Expense Management
// ISSUE-022/026: the generic entity list wraps rows as `{ items, total }`.
// Mirrors backend Expenses (models/expenses.py). Explicit signature so the page
// reads `items` (reading a wrong key is a tsc error).
export interface Expense {
  id: number;
  user_id?: string;
  category: string;
  amount: number;
  description?: string | null;
  expense_date?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ExpenseListResponse {
  items: Expense[];
  total: number;
}

export async function getExpenses(): Promise<ExpenseListResponse> {
  const response = await client.entities.expenses.query<ExpenseListResponse>({
    query: {},
    sort: '-created_at',
    limit: 200,
  });
  return response.data;
}

export async function createExpense(data: {
  category: string;
  amount: number;
  description?: string;
  expense_date?: string;
}) {
  const response = await client.entities.expenses.create({ data });
  return response.data;
}

export async function updateExpense(id: string, data: Record<string, unknown>) {
  const response = await client.entities.expenses.update({ id, data });
  return response.data;
}

export async function deleteExpense(id: string) {
  await client.entities.expenses.delete({ id });
}

// Staff Management
export async function getStaffMembers() {
  const response = await client.entities.staff_members.query({
    query: {},
    limit: 200,
  });
  return response.data;
}

export async function createStaffMember(data: {
  name: string;
  email?: string;
  phone?: string;
  role: string;
  is_active?: boolean;
}) {
  const response = await client.entities.staff_members.create({ data });
  return response.data;
}

export async function updateStaffMember(id: string, data: Record<string, unknown>) {
  const response = await client.entities.staff_members.update({ id, data });
  return response.data;
}

export async function deleteStaffMember(id: string) {
  await client.entities.staff_members.delete({ id });
}

// ---------------------------------------------------------------------------
// Staff lifecycle (#216): suspend/terminate, attendance, shifts, PIN.
// ---------------------------------------------------------------------------
const STAFF_BASE = '/api/v1/entities/staff_members';

export type StaffLifecycleAction = 'suspend' | 'terminate' | 'reactivate';

/** Move a staff member through the lifecycle (suspend/terminate revoke access). */
export async function setStaffLifecycle(id: string | number, action: StaffLifecycleAction) {
  const response = await client.apiCall.invoke({
    url: `${STAFF_BASE}/${id}/${action}`,
    method: 'POST',
  });
  return response.data;
}

/** Set a staff member's numeric login PIN (4–8 digits). */
export async function setStaffPin(id: string | number, pin: string) {
  const response = await client.apiCall.invoke({
    url: `${STAFF_BASE}/${id}/pin`,
    method: 'PUT',
    data: { pin },
  });
  return response.data;
}

/** Remove a staff member's PIN (disables their PIN login). */
export async function clearStaffPin(id: string | number) {
  const response = await client.apiCall.invoke({
    url: `${STAFF_BASE}/${id}/pin`,
    method: 'DELETE',
  });
  return response.data;
}

export interface StaffAttendance {
  id: number;
  staff_id: number;
  branch_id?: number | null;
  clock_in?: string | null;
  clock_out?: string | null;
  hours?: number | null;
  notes?: string | null;
}

export async function clockInStaff(id: string | number, notes?: string) {
  const response = await client.apiCall.invoke<StaffAttendance>({
    url: `${STAFF_BASE}/${id}/attendance/clock-in`,
    method: 'POST',
    data: { notes },
  });
  return response.data;
}

export async function clockOutStaff(id: string | number) {
  const response = await client.apiCall.invoke<StaffAttendance>({
    url: `${STAFF_BASE}/${id}/attendance/clock-out`,
    method: 'POST',
  });
  return response.data;
}

export async function getStaffAttendance(id: string | number): Promise<StaffAttendance[]> {
  const response = await client.apiCall.invoke<StaffAttendance[]>({
    url: `${STAFF_BASE}/${id}/attendance`,
    method: 'GET',
  });
  return response.data;
}

export interface StaffShift {
  id: number;
  staff_id: number;
  branch_id?: number | null;
  starts_at?: string | null;
  ends_at?: string | null;
  role?: string | null;
  notes?: string | null;
  status: string;
}

export async function assignStaffShift(
  id: string | number,
  shift: { starts_at: string; ends_at: string; role?: string; notes?: string },
): Promise<StaffShift> {
  const response = await client.apiCall.invoke<StaffShift>({
    url: `${STAFF_BASE}/${id}/shifts`,
    method: 'POST',
    data: shift,
  });
  return response.data;
}

export async function getStaffShifts(id: string | number): Promise<StaffShift[]> {
  const response = await client.apiCall.invoke<StaffShift[]>({
    url: `${STAFF_BASE}/${id}/shifts`,
    method: 'GET',
  });
  return response.data;
}

export async function cancelStaffShift(shiftId: string | number): Promise<StaffShift> {
  const response = await client.apiCall.invoke<StaffShift>({
    url: `${STAFF_BASE}/shifts/${shiftId}`,
    method: 'DELETE',
  });
  return response.data;
}

/** Fetch the merchant's attendance export as CSV text (payroll hand-off). */
export async function exportStaffAttendanceCsv(): Promise<string> {
  const response = await client.apiCall.invoke<string>({
    url: `${STAFF_BASE}/attendance/export`,
    method: 'GET',
  });
  return typeof response.data === 'string' ? response.data : String(response.data ?? '');
}

// ISSUE-035: owner-scoped staff-permission editor. `override` is the explicit
// grant/deny row (null = no override → the role default applies); `effective`
// is what `has_permission` resolves to.
export interface StaffPermission {
  permission_key: string;
  role_default: boolean;
  override: boolean | null;
  effective: boolean;
}

export interface StaffPermissions {
  staff_member_id: number;
  role: string;
  has_login: boolean;
  permissions: StaffPermission[];
}

export async function getStaffPermissions(staffMemberId: string | number): Promise<StaffPermissions> {
  const response = await client.apiCall.invoke<StaffPermissions>({
    url: `/api/v1/production/staff-permissions/${staffMemberId}`,
    method: 'GET',
  });
  return response.data;
}

/** Set a grant/deny override on a managed key, or pass `null` to reset to the role default. */
export async function setStaffPermission(
  staffMemberId: string | number,
  permissionKey: string,
  isGranted: boolean | null,
): Promise<{ staff_member_id: number; permission_key: string; override: boolean | null; effective: boolean }> {
  const response = await client.apiCall.invoke<{
    staff_member_id: number;
    permission_key: string;
    override: boolean | null;
    effective: boolean;
  }>({
    url: `/api/v1/production/staff-permissions/${staffMemberId}`,
    method: 'POST',
    data: { permission_key: permissionKey, is_granted: isGranted },
  });
  return response.data;
}

// Audit Logs (read-only)
export async function getAuditLogs() {
  const response = await client.entities.audit_logs.query({
    query: {},
    sort: '-created_at',
    limit: 200,
  });
  return response.data;
}

// Discount Management

// PRC-01: validate a discount code server-side and get the authoritative amount.
// The POS must not trust a client-computed discount; this is the source of truth
// for whether a code applies (active / min-purchase / usage cap) and its value.
export interface DiscountValidation {
  valid: boolean;
  code: string;
  type: string;
  value: number;
  discount_amount: number;
}

export async function validateDiscount(
  code: string,
  subtotal: number,
): Promise<DiscountValidation> {
  const response = await client.apiCall.invoke<DiscountValidation>({
    url: '/api/v1/entities/discounts/validate',
    method: 'POST',
    data: { code, subtotal },
  });
  return response.data;
}

// ISSUE-025/026 (U3.5): discount rows carry `usage_count` (the redemption tally),
// never `used_count`. Mirrors backend Discounts (models/discounts.py). The
// explicit signature makes the "Total Uses" rollup read the real field.
export interface Discount {
  id: number;
  user_id?: string;
  code: string;
  type: string;
  value: number;
  min_purchase?: number | null;
  is_active?: boolean | null;
  usage_count?: number | null;
  max_uses?: number | null;
  starts_at?: string | null;
  ends_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DiscountListResponse {
  items: Discount[];
  total: number;
}

export async function getDiscounts(): Promise<DiscountListResponse> {
  const response = await client.entities.discounts.query<DiscountListResponse>({
    query: {},
    limit: 200,
  });
  return response.data;
}

export async function createDiscount(data: {
  code: string;
  type: string;
  value: number;
  min_purchase?: number;
  max_uses?: number;
  is_active?: boolean;
  // PRC-02 validity window (ISO datetimes; either bound omitted ⇒ open-ended).
  starts_at?: string | null;
  ends_at?: string | null;
}) {
  const response = await client.entities.discounts.create({ data });
  return response.data;
}

export async function updateDiscount(id: string, data: Record<string, unknown>) {
  const response = await client.entities.discounts.update({ id, data });
  return response.data;
}

export async function deleteDiscount(id: string) {
  await client.entities.discounts.delete({ id });
}

// Category Management
export async function getCategories() {
  const response = await client.entities.categories.query({
    query: {},
    limit: 200,
  });
  return response.data;
}

export async function createCategory(data: {
  name: string;
  parent_id?: string;
  icon?: string;
  sort_order?: number;
}) {
  const response = await client.entities.categories.create({ data });
  return response.data;
}

export async function updateCategory(id: string, data: Record<string, unknown>) {
  const response = await client.entities.categories.update({ id, data });
  return response.data;
}

export async function deleteCategory(id: string) {
  await client.entities.categories.delete({ id });
}

// ---------------------------------------------------------------------------
// Phase C wiring
// ---------------------------------------------------------------------------

// Master: add client slots to an agent's package (MA-04)
export async function addAgentSlots(agentId: number, slots: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/tenant/master/agents/${agentId}/slots`,
    method: 'POST',
    data: { slots },
  });
  return response.data;
}

// Global tax rate (MA-05)
export async function getTaxRate() {
  const response = await client.apiCall.invoke({
    url: '/api/v1/tenant/tax-rate',
    method: 'GET',
    data: {},
  });
  return response.data as { tax_rate: number; is_global: boolean };
}

export async function setGlobalTaxRate(taxRate: number) {
  const response = await client.apiCall.invoke({
    url: '/api/v1/tenant/master/tax-rate',
    method: 'PUT',
    data: { tax_rate: taxRate },
  });
  return response.data;
}

// Agent: read the resolved per-client feature flags (AG-03). Every canonical key
// with its effective on/off state (default-on unless explicitly disabled), so the
// dashboard hydrates real toggle state per client instead of fabricating one.
export async function getClientFeatures(clientId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/tenant/agent/clients/${clientId}/features`,
    method: 'GET',
    data: {},
  });
  return response.data as { client_id: number; features: Record<string, boolean> };
}

// Agent: toggle a per-client feature flag at runtime (AG-03)
export async function setClientFeature(clientId: number, featureName: string, isEnabled: boolean) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/tenant/agent/clients/${clientId}/features`,
    method: 'POST',
    data: { feature_name: featureName, is_enabled: isEnabled },
  });
  return response.data;
}

// Agent: suspend a client whose subscription is past due (CL-05)
export async function suspendOverdueClient(clientId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/tenant/agent/clients/${clientId}/suspend-overdue`,
    method: 'POST',
    data: {},
  });
  return response.data;
}

// Agent: run the dunning sweep over their own overdue clients (CL-06). Retries
// each overdue charge; a failed retry walks active->past_due->dunning->suspended,
// a successful retry recovers the account.
export interface DunningRunResult {
  processed: number;
  recovered: number;
  past_due: number;
  dunning: number;
  suspended: number;
}

export async function runDunning() {
  const response = await client.apiCall.invoke<DunningRunResult>({
    url: '/api/v1/tenant/agent/billing/run-dunning',
    method: 'POST',
    data: {},
  });
  return response.data;
}

// ---------------------------------------------------------------------------
// Phase 5: subscription (CL-03/CL-04) + white-label logo upload (AG-01)
// ---------------------------------------------------------------------------
export interface SubscriptionPayment {
  id: number;
  amount: number;
  billing_cycle?: string;
  period_start?: string;
  period_end?: string;
  method?: string;
  created_at?: string;
}

export interface SubscriptionStatus {
  client_id: number;
  business_name: string;
  subscription_fee: number;
  billing_cycle: string;
  subscription_status: string;
  next_billing_date?: string;
  is_active: boolean;
  // Self-serve lifecycle stamps (#206): when the merchant paused / cancelled.
  subscription_paused_at?: string | null;
  subscription_cancelled_at?: string | null;
  // Card-on-file summary (#206): the masked card for the "replace card" affordance.
  has_card?: boolean;
  card_last4?: string | null;
  card_brand?: string | null;
  // Dunning state (CL-06): drive the client-facing overdue notice.
  dunning_attempts?: number;
  grace_deadline?: string;
  // Rail 2: the owning agent's Moyasar publishable key for live card tokenization.
  moyasar_publishable_key?: string | null;
  payments: SubscriptionPayment[];
}

// Upcoming renewal / upgrade-downgrade preview (#206).
export interface ProrationPreview {
  new_fee: number;
  billing_cycle: string;
  days_remaining: number;
  cycle_days: number;
  amount: number; // pro-rated charge (positive) or credit (negative)
  is_credit: boolean;
}

export interface RenewalPreview {
  subscription_status: string;
  billing_cycle: string;
  renewal_date?: string | null;
  currency: string;
  gross_fee: number;
  coupon_active: boolean;
  coupon_type?: string | null;
  coupon_value?: number | null;
  discount_amount: number;
  net_amount: number; // what will actually be charged on the next renewal
  will_charge: boolean; // false when paused / cancelled
  in_trial: boolean;
  proration?: ProrationPreview | null;
}

// Client: read own subscription status + payment history (CL-04)
export async function getClientSubscription() {
  const response = await client.apiCall.invoke<SubscriptionStatus>({
    url: '/api/v1/tenant/client/subscription',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Client: pay the current subscription period (CL-04). Charges the merchant's
// card-on-file through the owning agent's Moyasar account (Rail 2).
export async function payClientSubscription() {
  const response = await client.apiCall.invoke<SubscriptionStatus>({
    url: '/api/v1/tenant/client/subscription/pay',
    method: 'POST',
    data: {},
  });
  return response.data;
}

// A reusable card token from moyasar.js (PAN never reaches the server — PAY-09).
export interface SaveCardResult {
  saved: boolean;
  card_last4?: string | null;
  card_brand?: string | null;
}

// Client: store the card used to pay the subscription (Rail 2). Used both for the
// first card and to replace the card on file (#206) — the new token overwrites it.
export async function saveSubscriptionCard(data: {
  token: string;
  last4?: string;
  brand?: string;
}): Promise<SaveCardResult> {
  const response = await client.apiCall.invoke<SaveCardResult>({
    url: '/api/v1/tenant/client/subscription/card',
    method: 'POST',
    data,
  });
  return response.data;
}

// Client: pause their own subscription — billing stops, access kept (#206).
export async function pauseSubscription(): Promise<SubscriptionStatus> {
  const response = await client.apiCall.invoke<SubscriptionStatus>({
    url: '/api/v1/tenant/client/subscription/pause',
    method: 'POST',
    data: {},
  });
  return response.data;
}

// Client: resume a paused (or reactivate a cancelled) subscription (#206).
export async function resumeSubscription(): Promise<SubscriptionStatus> {
  const response = await client.apiCall.invoke<SubscriptionStatus>({
    url: '/api/v1/tenant/client/subscription/resume',
    method: 'POST',
    data: {},
  });
  return response.data;
}

// Client: cancel their own subscription at period end (#206).
export async function cancelSubscription(): Promise<SubscriptionStatus> {
  const response = await client.apiCall.invoke<SubscriptionStatus>({
    url: '/api/v1/tenant/client/subscription/cancel',
    method: 'POST',
    data: {},
  });
  return response.data;
}

// Client: preview the upcoming renewal — and optionally an upgrade/downgrade's
// proration when newFee is supplied (#206).
export async function getRenewalPreview(opts?: {
  newFee?: number;
  newCycle?: string;
}): Promise<RenewalPreview> {
  const params = new URLSearchParams();
  if (opts?.newFee !== undefined) params.set('new_fee', String(opts.newFee));
  if (opts?.newCycle) params.set('new_cycle', opts.newCycle);
  const qs = params.toString();
  const response = await client.apiCall.invoke<RenewalPreview>({
    url: `/api/v1/tenant/client/subscription/renewal-preview${qs ? `?${qs}` : ''}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Client: refund one of their settled subscription payments (#206). Omit amount
// for a full refund of the remaining amount.
export async function refundSubscriptionPayment(
  paymentId: number,
  amount?: number
): Promise<SubscriptionStatus> {
  const response = await client.apiCall.invoke<SubscriptionStatus>({
    url: `/api/v1/tenant/client/subscription/payments/${paymentId}/refund`,
    method: 'POST',
    data: amount !== undefined ? { amount } : {},
  });
  return response.data;
}

// ---- Rail 1: the agent's quota (what the agent pays the platform) ----
export interface QuotaPaymentLine {
  amount: number;
  billing_cycle?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  method?: string | null;
  reference?: string | null;
}

export interface QuotaStatus {
  quota_price?: number | null;
  quota_cycle?: string | null;
  quota_status?: string | null;
  next_quota_billing_date?: string | null;
  has_card: boolean;
  card_last4?: string | null;
  card_brand?: string | null;
  has_moyasar_account: boolean;
  moyasar_publishable_key?: string | null;
  payments: QuotaPaymentLine[];
}

// Agent: read quota status (price, cycle, next bill, card-on-file) + history.
export async function getQuotaStatus(): Promise<QuotaStatus> {
  const response = await client.apiCall.invoke<QuotaStatus>({
    url: '/api/v1/tenant/agent/quota',
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Agent: store the card used to pay the platform for the quota (Rail 1).
export async function saveQuotaCard(data: {
  token: string;
  last4?: string;
  brand?: string;
}): Promise<SaveCardResult> {
  const response = await client.apiCall.invoke<SaveCardResult>({
    url: '/api/v1/tenant/agent/quota/card',
    method: 'POST',
    data,
  });
  return response.data;
}

// Agent: pay / renew the current quota period (Rail 1).
export async function payQuota(): Promise<QuotaStatus> {
  const response = await client.apiCall.invoke<QuotaStatus>({
    url: '/api/v1/tenant/agent/quota/pay',
    method: 'POST',
    data: {},
  });
  return response.data;
}

// ---- Rail 2: the agent's OWN Moyasar account (collects from his merchants) ----
export interface SaveAgentMoyasarResult {
  saved: boolean;
  valid: boolean;
  detail: string;
  publishable_key?: string | null;
}

// Agent: connect / update his own Moyasar account credentials.
export async function saveAgentMoyasarKeys(data: {
  secret_key: string;
  publishable_key?: string;
  webhook_secret?: string;
}): Promise<SaveAgentMoyasarResult> {
  const response = await client.apiCall.invoke<SaveAgentMoyasarResult>({
    url: '/api/v1/tenant/agent/moyasar',
    method: 'PUT',
    data,
  });
  return response.data;
}

// Client: download the PRN-08 subscription invoice for one paid period (CL-09)
export async function downloadSubscriptionInvoice(paymentId: number) {
  const blob = await getBlob(
    `/api/v1/tenant/client/subscription/payments/${paymentId}/invoice`
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `subscription-invoice-${paymentId}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Agent: set a client's subscription fee / billing cycle (CL-03)
export async function updateClientSubscription(
  clientId: number,
  data: { subscription_fee?: number; billing_cycle?: string }
) {
  const response = await client.apiCall.invoke<SubscriptionStatus>({
    url: `/api/v1/tenant/agent/clients/${clientId}/subscription`,
    method: 'PUT',
    data,
  });
  return response.data;
}

// Agent: upload a white-label logo; returns the served URL (AG-01)
export async function uploadAgentLogo(file: File): Promise<{ logo_url: string }> {
  return uploadMultipart<{ logo_url: string }>('/api/v1/tenant/agent/logo', file);
}

// Phase 6 (PDF): download a transaction's invoice as a real PDF and save it.
export async function downloadInvoicePdf(transactionId: number, invoiceNumber: string) {
  const blob = await getBlob(`/api/v1/pos/transactions/${transactionId}/pdf`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${invoiceNumber}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// F-072 / RPT-10: download any /reports/* report as a real PDF. The shared,
// always-Arabic RTL renderer lives server-side; the client just asks for
// ?format=pdf and saves the bytes. ``path`` is the report path (no leading
// slash), ``params`` the report's query args (days, period, …).
export async function downloadReportPdf(
  path: string,
  filename: string,
  params: Record<string, string | number> = {},
) {
  const qs = new URLSearchParams({ ...Object.fromEntries(
    Object.entries(params).map(([k, v]) => [k, String(v)]),
  ), format: 'pdf' }).toString();
  const blob = await getBlob(`/api/v1/reports/${path}?${qs}`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Result shared by the email/SMS receipt actions. `delivered` is false when the
// backend only *logged* the message (no SMTP/Twilio configured) — the UI must
// not claim "sent" in that case (parity #6).
export interface ReceiptDeliveryResult {
  status: 'sent' | 'logged' | string;
  to: string;
  delivered: boolean;
  message_id?: string;
  subject?: string;
  invoice_number?: string;
}

// POS-04: email a receipt for a transaction
export async function emailReceipt(
  transactionId: number,
  toEmail: string,
): Promise<ReceiptDeliveryResult> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/transactions/${transactionId}/email`,
    method: 'POST',
    data: { to_email: toEmail },
  });
  return response.data;
}

// Parity #6: SMS a receipt for a transaction. Sibling of `emailReceipt`; the
// backend gates it behind the `sms_receipts` feature flag and expects `to_number`.
export async function smsReceipt(
  transactionId: number,
  toNumber: string,
): Promise<ReceiptDeliveryResult> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/transactions/${transactionId}/sms`,
    method: 'POST',
    data: { to_number: toNumber },
  });
  return response.data;
}

// Build the URL of the always-Arabic ZATCA invoice document (print-to-PDF ready).
export function invoiceDocumentPath(transactionId: number): string {
  return `/api/v1/pos/transactions/${transactionId}/invoice`;
}

// ---- Quotations (Phase D) ----
// A quotation (عرض سعر) is a non-fiscal pre-sale document. Its printable form is
// always Arabic (see quotationDocumentPath), enforced server-side.
export async function getQuotations() {
  const response = await client.entities.quotations.query({ query: {}, limit: 200 });
  return response.data;
}

export async function createQuotation(data: {
  customer_name?: string;
  customer_phone?: string;
  items_json?: string;
  subtotal?: number;
  vat_amount?: number;
  discount_amount?: number;
  total_amount?: number;
  valid_until?: string;
  notes?: string;
  status?: string;
}) {
  const response = await client.entities.quotations.create({ data });
  return response.data;
}

export async function updateQuotation(id: string, data: Record<string, unknown>) {
  const response = await client.entities.quotations.update({ id, data });
  return response.data;
}

export async function deleteQuotation(id: string) {
  await client.entities.quotations.delete({ id });
}

// Always-Arabic quotation document (print-to-PDF ready).
export function quotationDocumentPath(quotationId: number): string {
  return `/api/v1/entities/quotations/${quotationId}/document`;
}

// FE-11: fetch the always-Arabic quotation document through the shared client
// (getBlob → the auth-refresh interceptor) and return its HTML. getBlob rejects
// on a non-2xx status, so the caller surfaces the error instead of writing the
// backend's error page into a new tab (the old bare-fetch path did neither).
export async function getQuotationDocument(quotationId: number): Promise<string> {
  return getText(quotationDocumentPath(quotationId));
}

// ISSUE-056: move a quotation along its lifecycle (draft → sent → accepted →
// expired). `converted` is reached only via convertQuotation, not here.
export async function updateQuotationStatus(id: number, status: string) {
  const res = await client.apiCall.invoke<Record<string, unknown>>({
    url: `/api/v1/entities/quotations/${id}/status`,
    method: 'PUT',
    data: { status },
  });
  return res.data;
}

export interface QuotationConvertResult {
  quotation_id: number;
  status: string;
  transaction_id: number;
  invoice_number: string;
  total_amount: number;
  zatca_document_id?: number | null;
  zatca_status: string;
}

// ISSUE-056: convert a quotation into a real sale through the canonical ZATCA
// sale path. Marks the quote `converted` and links the resulting invoice.
export async function convertQuotation(
  id: number,
  data: { payment_method?: string } = {}
): Promise<QuotationConvertResult> {
  const res = await client.apiCall.invoke<QuotationConvertResult>({
    url: `/api/v1/entities/quotations/${id}/convert`,
    method: 'POST',
    data,
  });
  return res.data;
}

// ---- Phase E ----

// Fetch a base64 ESC/POS byte stream for thermal printing (see lib/thermalPrint).
// ISSUE-075: pass `{ reprint: true }` to reprint a PAST sale — the backend stamps
// the receipt as a duplicate copy and audits the reprint.
export async function getEscposReceipt(
  transactionId: number,
  opts?: { reprint?: boolean }
): Promise<string> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/transactions/${transactionId}/escpos`,
    method: 'GET',
    data: opts?.reprint ? { reprint: true } : {},
  });
  return response.data?.data as string;
}

// Customer loyalty balance.
export async function getLoyaltyBalance(customerId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/production/loyalty/balance?customer_id=${customerId}`,
    method: 'GET',
    data: {},
  });
  return response.data;
}

// Flush an offline-queued batch of transactions (idempotent by offline_id).
export async function syncOfflineTransactions(
  transactions: Array<Record<string, unknown>>
) {
  const response = await client.apiCall.invoke({
    url: '/api/v1/production/offline/sync',
    method: 'POST',
    data: { transactions },
  });
  return response.data;
}

// ---------- Restaurant (RST-01..03, F-045) ----------
// All endpoints are gated server-side by require_feature('restaurant') AND the
// client's business_type ∈ {restaurant, both}; a retail client gets 403.
export interface FloorZone {
  id: number;
  name: string;
  branch_id?: number | null;
}

export interface RestaurantTable {
  id: number;
  name: string;
  seats?: number | null;
  zone_id?: number | null;
  branch_id?: number | null;
  state?: string | null; // free | occupied | bill_printed
  current_ticket_id?: number | null;
  next_reservation?: Reservation | null; // soonest upcoming booking (ISSUE-069)
}

export interface OrderTicket {
  id: number;
  table_id?: number | null;
  order_type?: string | null; // dine_in | takeaway | delivery
  status?: string | null; // open | held | fired | settled | void
  customer_name?: string | null;
  party_size?: number | null;
  notes?: string | null;
  service_charge_pct?: number | null; // optional service charge %, outside VAT (F-061)
}

export async function getFloorZones(): Promise<FloorZone[]> {
  const res = await client.apiCall.invoke<FloorZone[]>({
    url: '/api/v1/restaurant/zones',
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function createFloorZone(data: { name: string; branch_id?: number }) {
  const res = await client.apiCall.invoke({
    url: '/api/v1/restaurant/zones',
    method: 'POST',
    data,
  });
  return res.data;
}

// Rename a floor zone (parity #7). Only non-null fields are applied server-side.
export async function updateFloorZone(
  zoneId: number,
  data: { name?: string; branch_id?: number },
): Promise<FloorZone> {
  const res = await client.apiCall.invoke<FloorZone>({
    url: `/api/v1/restaurant/zones/${zoneId}`,
    method: 'PUT',
    data,
  });
  return res.data;
}

// Delete a floor zone (parity #7). Tables keep their seats but lose the zone tab.
export async function deleteFloorZone(zoneId: number) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/restaurant/zones/${zoneId}`,
    method: 'DELETE',
  });
  return res.data;
}

export async function getRestaurantTables(params?: {
  zone_id?: number;
  branch_id?: number;
  state?: string;
}): Promise<{ items: RestaurantTable[]; total: number }> {
  const res = await client.apiCall.invoke<{ items: RestaurantTable[]; total: number }>({
    url: '/api/v1/restaurant/tables',
    method: 'GET',
    data: params || {},
  });
  return res.data;
}

export async function createRestaurantTable(data: {
  name: string;
  seats?: number;
  zone_id?: number;
  branch_id?: number;
}) {
  const res = await client.apiCall.invoke({
    url: '/api/v1/restaurant/tables',
    method: 'POST',
    data,
  });
  return res.data;
}

export async function updateRestaurantTable(
  tableId: number,
  data: { name?: string; seats?: number; zone_id?: number; state?: string }
) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/restaurant/tables/${tableId}`,
    method: 'PUT',
    data,
  });
  return res.data;
}

export async function openTableOrder(
  tableId: number,
  data: { order_type?: string; customer_name?: string; party_size?: number; notes?: string }
): Promise<OrderTicket> {
  const res = await client.apiCall.invoke<OrderTicket>({
    url: `/api/v1/restaurant/tables/${tableId}/open-order`,
    method: 'POST',
    data,
  });
  return res.data;
}

// ---------- Reservations + waitlist (ISSUE-069) ----------
export interface Reservation {
  id: number;
  table_id?: number | null;
  customer_name?: string | null;
  party_size?: number | null;
  reserved_at?: string | null; // ISO-8601
  status?: string | null; // booked | seated | cancelled | no_show
  notes?: string | null;
  branch_id?: number | null;
}

export interface WaitlistEntry {
  id: number;
  customer_name?: string | null;
  party_size?: number | null;
  status?: string | null; // waiting | seated | cancelled
  notes?: string | null;
  seated_table_id?: number | null;
  seated_ticket_id?: number | null;
}

export async function getReservations(params?: {
  status?: string;
  table_id?: number;
}): Promise<{ items: Reservation[]; total: number }> {
  const res = await client.apiCall.invoke<{ items: Reservation[]; total: number }>({
    url: '/api/v1/restaurant/reservations',
    method: 'GET',
    data: params || {},
  });
  return res.data;
}

export async function createReservation(data: {
  table_id?: number;
  reserved_at: string;
  customer_name?: string;
  party_size?: number;
  notes?: string;
}): Promise<Reservation> {
  const res = await client.apiCall.invoke<Reservation>({
    url: '/api/v1/restaurant/reservations',
    method: 'POST',
    data,
  });
  return res.data;
}

export async function cancelReservation(reservationId: number): Promise<Reservation> {
  const res = await client.apiCall.invoke<Reservation>({
    url: `/api/v1/restaurant/reservations/${reservationId}`,
    method: 'DELETE',
    data: {},
  });
  return res.data;
}

export async function getWaitlist(params?: {
  status?: string;
}): Promise<{ items: WaitlistEntry[]; total: number }> {
  const res = await client.apiCall.invoke<{ items: WaitlistEntry[]; total: number }>({
    url: '/api/v1/restaurant/waitlist',
    method: 'GET',
    data: params || {},
  });
  return res.data;
}

export async function addToWaitlist(data: {
  customer_name?: string;
  party_size?: number;
  notes?: string;
}): Promise<WaitlistEntry> {
  const res = await client.apiCall.invoke<WaitlistEntry>({
    url: '/api/v1/restaurant/waitlist',
    method: 'POST',
    data,
  });
  return res.data;
}

export async function cancelWaitlistEntry(entryId: number): Promise<WaitlistEntry> {
  const res = await client.apiCall.invoke<WaitlistEntry>({
    url: `/api/v1/restaurant/waitlist/${entryId}`,
    method: 'DELETE',
    data: {},
  });
  return res.data;
}

export async function seatWaitlistEntry(
  entryId: number,
  tableId: number
): Promise<{ entry: WaitlistEntry; ticket: OrderTicket }> {
  const res = await client.apiCall.invoke<{ entry: WaitlistEntry; ticket: OrderTicket }>({
    url: `/api/v1/restaurant/waitlist/${entryId}/seat`,
    method: 'POST',
    data: { table_id: tableId },
  });
  return res.data;
}

// ---------- Order ticket line items (F-055) ----------
export interface TicketItem {
  id: number;
  ticket_id: number;
  product_id?: number | null;
  variant_id?: number | null;
  name?: string | null;
  qty: number;
  unit_price: number;
  line_total: number;
  course?: string | null;
  seat_no?: number | null;
  fire_state?: string | null; // open | fired | bumped
  notes?: string | null;
  modifiers?: string | null; // serialized JSON of the selected modifiers (F-056)
}

export interface SplitShare {
  seat?: string;
  share?: number;
  item_id?: number;
  name?: string | null;
  item_ids?: number[];
  subtotal: number;
}

export interface SplitResult {
  ticket_id: number;
  strategy: string;
  total: number;
  shares: SplitShare[];
}

export interface AllDayCount {
  fired_item_count: number;
  fired_qty: number;
  by_product: { name: string; qty: number }[];
}

export async function getOrderTicket(ticketId: number): Promise<OrderTicket> {
  const res = await client.apiCall.invoke<OrderTicket>({
    url: `/api/v1/restaurant/order-tickets/${ticketId}`,
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function getTicketItems(
  ticketId: number
): Promise<{ items: TicketItem[]; total: number }> {
  const res = await client.apiCall.invoke<{ items: TicketItem[]; total: number }>({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/items`,
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function addTicketItem(
  ticketId: number,
  data: {
    product_id?: number;
    combo_id?: number;
    name?: string;
    qty?: number;
    unit_price?: number;
    course?: string;
    seat_no?: number;
    notes?: string;
    modifiers?: number[]; // selected modifier ids (F-056)
  }
): Promise<TicketItem> {
  const res = await client.apiCall.invoke<TicketItem>({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/items`,
    method: 'POST',
    data,
  });
  return res.data;
}

export async function updateTicketItem(
  ticketId: number,
  itemId: number,
  data: { qty?: number; course?: string; seat_no?: number; notes?: string; unit_price?: number }
): Promise<TicketItem> {
  const res = await client.apiCall.invoke<TicketItem>({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/items/${itemId}`,
    method: 'PUT',
    data,
  });
  return res.data;
}

export async function voidTicketItem(ticketId: number, itemId: number) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/items/${itemId}`,
    method: 'DELETE',
    data: {},
  });
  return res.data;
}

export async function fireCourse(ticketId: number, course: string) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/fire`,
    method: 'POST',
    data: { course },
  });
  return res.data;
}

export async function transferTicket(ticketId: number, targetTableId: number): Promise<OrderTicket> {
  const res = await client.apiCall.invoke<OrderTicket>({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/transfer`,
    method: 'POST',
    data: { target_table_id: targetTableId },
  });
  return res.data;
}

export async function mergeTickets(ticketId: number, sourceTicketId: number): Promise<OrderTicket> {
  const res = await client.apiCall.invoke<OrderTicket>({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/merge`,
    method: 'POST',
    data: { source_ticket_id: sourceTicketId },
  });
  return res.data;
}

export async function splitTicket(
  ticketId: number,
  strategy: 'seat' | 'amount' | 'item',
  nWays?: number
): Promise<SplitResult> {
  const res = await client.apiCall.invoke<SplitResult>({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/split`,
    method: 'POST',
    data: { strategy, n_ways: nWays },
  });
  return res.data;
}

// ---------- Service charge + check (F-061) ----------
// An optional service-charge % lives on the ticket; the check resolves it to a
// separate non-taxable line OUTSIDE the VAT base (mirrors tips). amount_due is
// what the tenders must cover: invoice total + service charge + tip.
export interface TicketCheck {
  ticket_id: number;
  lines: {
    item_id: number;
    name?: string | null;
    qty: number;
    unit_price: number;
    line_total: number;
    course?: string | null;
    taxable: boolean;
  }[];
  subtotal: number;
  vat_rate: number;
  vat_amount: number;
  total_amount: number;
  service_charge: { pct: number; amount: number; taxable: boolean };
  tip_amount: number;
  amount_due: number;
}

export async function setServiceCharge(
  ticketId: number,
  serviceChargePct: number
): Promise<OrderTicket> {
  const res = await client.apiCall.invoke<OrderTicket>({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/service-charge`,
    method: 'PUT',
    data: { service_charge_pct: serviceChargePct },
  });
  return res.data;
}

export async function getTicketCheck(
  ticketId: number,
  tipAmount = 0
): Promise<TicketCheck> {
  const res = await client.apiCall.invoke<TicketCheck>({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/check`,
    method: 'GET',
    data: { tip_amount: tipAmount },
  });
  return res.data;
}

// ---------- Check + settle (F-059) ----------
// A proforma check (فاتورة مبدئية) the customer reviews BEFORE paying: full
// breakdown but NO QR and NO stamp, so it can never be mistaken for a tax invoice.
export interface ProformaCheck extends TicketCheck {
  document_type: 'proforma';
  title_ar: string;
  is_fiscal: false;
  has_qr: false;
  has_stamp: false;
  proforma_base64: string;
}

export async function printTicketCheck(
  ticketId: number,
  tipAmount = 0
): Promise<ProformaCheck> {
  const res = await client.apiCall.invoke<ProformaCheck>({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/check`,
    method: 'POST',
    data: { tip_amount: tipAmount },
  });
  return res.data;
}

export interface SettleResult {
  ticket_id: number;
  transaction_id: number;
  invoice_number: string;
  subtotal: number;
  vat_amount: number;
  total_amount: number;
  service_charge: number;
  tip_amount: number;
  amount_due: number;
  zatca_document_id?: number | null;
  zatca_status: string;
  zatca_qr?: string | null;
  zatca_qr_base64?: string | null;
  receipt_base64?: string | null;
  ticket_status: string;
  table_freed: boolean;
  // ISSUE-070: false when a partial settlement left an unpaid remainder on a
  // still-open ticket; true (or absent) for a full settle.
  fully_settled?: boolean;
}

// Settle a ticket into a real ZATCA invoice via the shared atomic sale core. A
// declined card rolls the whole thing back (402) — ticket stays open, table stays
// occupied, no invoice minted.
export async function settleTicket(
  ticketId: number,
  data: {
    payment_method?: string;
    tip_amount?: number;
    customer_name?: string;
    customer_vat_number?: string;
    payment_simulate?: string;
    payment_token?: string;
    payment_terminal_id?: number;
    payment_gift_card_code?: string;
    payments?: {
      method: string;
      amount: number;
      tender_type?: string;
      token?: string;
      simulate?: string;
      terminal_id?: number;
      gift_card_code?: string;
    }[];
  }
): Promise<SettleResult> {
  const res = await client.apiCall.invoke<SettleResult>({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/settle`,
    method: 'POST',
    data,
  });
  return res.data;
}

// Settle PART of a ticket into its own ZATCA invoice (ISSUE-070), leaving the
// unpaid remainder on the still-open ticket. Bills exactly one subset: a single
// seat's lines (`seat_no`) or specific lines (`item_ids`). Mints a real invoice
// through the SAME atomic sale core as the full settle; billing the last unpaid
// line closes the ticket and frees the table (`fully_settled: true`).
export async function settleTicketPartial(
  ticketId: number,
  data: {
    item_ids?: number[];
    seat_no?: number;
    payment_method?: string;
    tip_amount?: number;
    customer_name?: string;
    customer_vat_number?: string;
    payment_simulate?: string;
    payment_token?: string;
    payment_terminal_id?: number;
    payment_gift_card_code?: string;
  }
): Promise<SettleResult> {
  const res = await client.apiCall.invoke<SettleResult>({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/settle-partial`,
    method: 'POST',
    data,
  });
  return res.data;
}

export async function getOrderTickets(params?: {
  status?: string;
  table_id?: number;
}): Promise<{ items: OrderTicket[]; total: number }> {
  const res = await client.apiCall.invoke<{ items: OrderTicket[]; total: number }>({
    url: '/api/v1/restaurant/order-tickets',
    method: 'GET',
    data: params || {},
  });
  return res.data;
}

// ---------- Order types drive behavior (F-058) ----------
// Open a ticket whose flow follows order_type: dine_in requires (and occupies)
// a table; takeaway/delivery are tableless. order_type also drives print routing.
export async function createOrderTicket(data: {
  order_type: string; // dine_in | takeaway | delivery
  table_id?: number;
  customer_name?: string;
  party_size?: number;
  notes?: string;
}): Promise<OrderTicket> {
  const res = await client.apiCall.invoke<OrderTicket>({
    url: '/api/v1/restaurant/order-tickets',
    method: 'POST',
    data,
  });
  return res.data;
}

export interface PrintRouting {
  ticket_id: number;
  order_type: string;
  targets: string[]; // e.g. ['kitchen', 'table_check']
}

export async function getPrintRouting(ticketId: number): Promise<PrintRouting> {
  const res = await client.apiCall.invoke<PrintRouting>({
    url: `/api/v1/restaurant/order-tickets/${ticketId}/print-routing`,
    method: 'GET',
    data: {},
  });
  return res.data;
}

// ---------- Modifiers, modifier groups & combos (F-056) ----------
// The menu-builder surface: a manager defines modifier groups (required + min/
// max), modifiers (bilingual name + price delta), attaches groups to products,
// and defines combos (components + a bundle price that overrides their sum).
export interface ModifierGroup {
  id: number;
  name: string;
  name_ar?: string | null;
  required?: boolean | null;
  min_select?: number | null;
  max_select?: number | null;
}

export interface Modifier {
  id: number;
  group_id: number;
  name: string;
  name_ar?: string | null;
  price_delta: number;
}

// A product's attached group, with its modifiers nested (the ticket picker reads this).
export interface ProductModifierGroup extends ModifierGroup {
  modifiers: Modifier[];
}

export interface ComboComponentRef {
  product_id: number;
  qty: number;
}

export interface Combo {
  id: number;
  name: string;
  name_ar?: string | null;
  bundle_price: number;
  components: ComboComponentRef[];
  component_sum?: number | null;
  is_active?: boolean | null;
}

export async function getModifierGroups(): Promise<ModifierGroup[]> {
  const res = await client.apiCall.invoke<ModifierGroup[]>({
    url: '/api/v1/restaurant/modifier-groups',
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function createModifierGroup(data: {
  name: string;
  name_ar?: string;
  required?: boolean;
  min_select?: number;
  max_select?: number;
}): Promise<ModifierGroup> {
  const res = await client.apiCall.invoke<ModifierGroup>({
    url: '/api/v1/restaurant/modifier-groups',
    method: 'POST',
    data,
  });
  return res.data;
}

export async function deleteModifierGroup(groupId: number) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/restaurant/modifier-groups/${groupId}`,
    method: 'DELETE',
    data: {},
  });
  return res.data;
}

export async function getModifiers(groupId: number): Promise<Modifier[]> {
  const res = await client.apiCall.invoke<Modifier[]>({
    url: `/api/v1/restaurant/modifier-groups/${groupId}/modifiers`,
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function createModifier(
  groupId: number,
  data: { name: string; name_ar?: string; price_delta?: number }
): Promise<Modifier> {
  const res = await client.apiCall.invoke<Modifier>({
    url: `/api/v1/restaurant/modifier-groups/${groupId}/modifiers`,
    method: 'POST',
    data,
  });
  return res.data;
}

export async function deleteModifier(modifierId: number) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/restaurant/modifiers/${modifierId}`,
    method: 'DELETE',
    data: {},
  });
  return res.data;
}

export async function getProductModifierGroups(
  productId: number
): Promise<{ items: ProductModifierGroup[]; total: number }> {
  const res = await client.apiCall.invoke<{ items: ProductModifierGroup[]; total: number }>({
    url: `/api/v1/restaurant/products/${productId}/modifier-groups`,
    method: 'GET',
    data: {},
  });
  return res.data;
}

// ---------- Bill-of-materials / recipe (F-062, ISSUE-039) ----------
// A parent product's recipe: each entry is a component product with a qty-per
// (units of the component consumed per unit of the parent sold). Selling a
// BOM-backed product depletes every component by qty_per × qty_sold inside the
// same atomic settle transaction (the sale-core depletion path).
export interface BomEntry {
  id: number;
  user_id: string;
  client_id?: number | null;
  parent_product_id: number;
  component_product_id: number;
  qty_per: number;
}

export interface BomList {
  items: BomEntry[];
  total: number;
  // Component costs rolled up to the parent's cost-of-goods value.
  cost_of_goods: number;
}

export async function getProductBom(productId: number): Promise<BomList> {
  const res = await client.apiCall.invoke<BomList>({
    url: `/api/v1/restaurant/products/${productId}/bom`,
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function addBomEntry(
  productId: number,
  data: { component_product_id: number; qty_per: number }
): Promise<BomEntry> {
  const res = await client.apiCall.invoke<BomEntry>({
    url: `/api/v1/restaurant/products/${productId}/bom`,
    method: 'POST',
    data,
  });
  return res.data;
}

export async function updateBomEntry(bomId: number, qtyPer: number): Promise<BomEntry> {
  const res = await client.apiCall.invoke<BomEntry>({
    url: `/api/v1/restaurant/bom/${bomId}`,
    method: 'PUT',
    data: { qty_per: qtyPer },
  });
  return res.data;
}

export async function deleteBomEntry(bomId: number) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/restaurant/bom/${bomId}`,
    method: 'DELETE',
    data: {},
  });
  return res.data;
}

export async function attachModifierGroup(productId: number, groupId: number) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/restaurant/products/${productId}/modifier-groups/${groupId}`,
    method: 'POST',
    data: {},
  });
  return res.data;
}

export async function detachModifierGroup(productId: number, groupId: number) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/restaurant/products/${productId}/modifier-groups/${groupId}`,
    method: 'DELETE',
    data: {},
  });
  return res.data;
}

export async function getCombos(): Promise<Combo[]> {
  const res = await client.apiCall.invoke<Combo[]>({
    url: '/api/v1/restaurant/combos',
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function createCombo(data: {
  name: string;
  name_ar?: string;
  bundle_price: number;
  components: ComboComponentRef[];
}): Promise<Combo> {
  const res = await client.apiCall.invoke<Combo>({
    url: '/api/v1/restaurant/combos',
    method: 'POST',
    data,
  });
  return res.data;
}

export async function deleteCombo(comboId: number) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/restaurant/combos/${comboId}`,
    method: 'DELETE',
    data: {},
  });
  return res.data;
}

// ---------- Catalog modifiers & combos for ANY merchant (ISSUE-066) ----------
// The same modifier-group / modifier / product-attach / combo primitives as the
// restaurant menu-builder above, but on the ``/api/v1/catalog`` surface that has
// NO restaurant business-type/feature gate — so a retail merchant can build
// gift-wrap modifiers and bundle combos. Defined here (separate functions, same
// types) so the page can target the catalog surface without the 403 gate, while
// the restaurant menu-builder keeps using ``/api/v1/restaurant``.
export async function getCatalogModifierGroups(): Promise<ModifierGroup[]> {
  const res = await client.apiCall.invoke<ModifierGroup[]>({
    url: '/api/v1/catalog/modifier-groups',
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function createCatalogModifierGroup(data: {
  name: string;
  name_ar?: string;
  required?: boolean;
  min_select?: number;
  max_select?: number;
}): Promise<ModifierGroup> {
  const res = await client.apiCall.invoke<ModifierGroup>({
    url: '/api/v1/catalog/modifier-groups',
    method: 'POST',
    data,
  });
  return res.data;
}

export async function deleteCatalogModifierGroup(groupId: number) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/catalog/modifier-groups/${groupId}`,
    method: 'DELETE',
    data: {},
  });
  return res.data;
}

export async function createCatalogModifier(
  groupId: number,
  data: { name: string; name_ar?: string; price_delta?: number }
): Promise<Modifier> {
  const res = await client.apiCall.invoke<Modifier>({
    url: `/api/v1/catalog/modifier-groups/${groupId}/modifiers`,
    method: 'POST',
    data,
  });
  return res.data;
}

export async function getCatalogProductModifierGroups(
  productId: number
): Promise<{ items: ProductModifierGroup[]; total: number }> {
  const res = await client.apiCall.invoke<{ items: ProductModifierGroup[]; total: number }>({
    url: `/api/v1/catalog/products/${productId}/modifier-groups`,
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function attachCatalogModifierGroup(productId: number, groupId: number) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/catalog/products/${productId}/modifier-groups/${groupId}`,
    method: 'POST',
    data: {},
  });
  return res.data;
}

export async function detachCatalogModifierGroup(productId: number, groupId: number) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/catalog/products/${productId}/modifier-groups/${groupId}`,
    method: 'DELETE',
    data: {},
  });
  return res.data;
}

export async function getCatalogCombos(): Promise<Combo[]> {
  const res = await client.apiCall.invoke<Combo[]>({
    url: '/api/v1/catalog/combos',
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function createCatalogCombo(data: {
  name: string;
  name_ar?: string;
  bundle_price: number;
  components: ComboComponentRef[];
}): Promise<Combo> {
  const res = await client.apiCall.invoke<Combo>({
    url: '/api/v1/catalog/combos',
    method: 'POST',
    data,
  });
  return res.data;
}

export async function deleteCatalogCombo(comboId: number) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/catalog/combos/${comboId}`,
    method: 'DELETE',
    data: {},
  });
  return res.data;
}

// ---------- KDS / KOT + real-time kitchen channel (F-057) ----------
// A manager defines prep-stations; firing a course (F-055) materializes one KDS
// card per relevant station and pushes it to the board over SSE (≤1s). A cook
// bumps a card off the board and recalls a mistaken bump; a per-station 80mm
// always-Arabic KOT (modifiers grouped by course, no prices) prints for stations
// without a screen.
export interface PrepStation {
  id: number;
  name: string;
  name_ar?: string | null;
  sort_order?: number | null;
}

export interface KdsCardItem {
  item_id: number;
  name?: string | null;
  qty: number;
  course?: string | null;
  notes?: string | null;
  modifiers: string[];
}

export interface KdsCard {
  id: number;
  order_ticket_id: number;
  table_id?: number | null;
  station_id?: number | null;
  course?: string | null;
  status: string; // active | bumped
  customer_name?: string | null;
  order_type?: string | null;
  items: KdsCardItem[];
  fired_at?: string | null;
  bumped_at?: string | null;
}

export interface KotCourse {
  course: string;
  items: { name?: string | null; qty: number; notes?: string | null; modifiers: string[] }[];
}

export interface KotPayload {
  kds_ticket_id: number;
  order_ticket_id: number;
  station_id?: number | null;
  station_name?: string | null;
  station_name_ar?: string | null;
  table_id?: number | null;
  fired_at?: string | null;
  courses: KotCourse[];
  kot_base64: string;
}

export async function getPrepStations(): Promise<PrepStation[]> {
  const res = await client.apiCall.invoke<PrepStation[]>({
    url: '/api/v1/restaurant/kds/stations',
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function createPrepStation(data: {
  name: string;
  name_ar?: string;
  sort_order?: number;
}): Promise<PrepStation> {
  const res = await client.apiCall.invoke<PrepStation>({
    url: '/api/v1/restaurant/kds/stations',
    method: 'POST',
    data,
  });
  return res.data;
}

export async function deletePrepStation(stationId: number) {
  const res = await client.apiCall.invoke({
    url: `/api/v1/restaurant/kds/stations/${stationId}`,
    method: 'DELETE',
    data: {},
  });
  return res.data;
}

export async function getKdsTickets(params?: {
  status?: string;
  station_id?: number;
}): Promise<{ items: KdsCard[]; total: number }> {
  const res = await client.apiCall.invoke<{ items: KdsCard[]; total: number }>({
    url: '/api/v1/restaurant/kds/tickets',
    method: 'GET',
    data: params || {},
  });
  return res.data;
}

export async function bumpKdsTicket(kdsId: number): Promise<KdsCard> {
  const res = await client.apiCall.invoke<KdsCard>({
    url: `/api/v1/restaurant/kds/${kdsId}/bump`,
    method: 'POST',
    data: {},
  });
  return res.data;
}

export async function recallKdsTicket(kdsId: number): Promise<KdsCard> {
  const res = await client.apiCall.invoke<KdsCard>({
    url: `/api/v1/restaurant/kds/${kdsId}/recall`,
    method: 'POST',
    data: {},
  });
  return res.data;
}

export async function getKdsKot(kdsId: number): Promise<KotPayload> {
  const res = await client.apiCall.invoke<KotPayload>({
    url: `/api/v1/restaurant/kds/${kdsId}/kot`,
    method: 'GET',
    data: {},
  });
  return res.data;
}

// The SSE stream URL for the live kitchen board. EventSource can't set an
// Authorization header, so rather than leaking the long-lived bearer JWT in the
// URL (where it lands in access logs / browser history), we mint a single-use,
// short-lived stream ticket via an authenticated POST and put *that* on the URL.
// The backend validates and burns the ticket on connect (FE-02). Returns null
// when not authenticated or if minting fails.
export async function kdsStreamUrl(): Promise<string | null> {
  if (!getToken()) return null;
  try {
    const res = await client.apiCall.invoke<{ ticket: string }>({
      url: '/api/v1/restaurant/kds/stream-ticket',
      method: 'POST',
      data: {},
    });
    const ticket = res.data?.ticket;
    if (!ticket) return null;
    return `${getAPIBaseURL()}/api/v1/restaurant/kds/stream?ticket=${encodeURIComponent(ticket)}`;
  } catch {
    return null;
  }
}

// ---------- ZATCA document status (ZA-08, F-019) ----------
// Client-scoped fiscal-document visibility: onboarding status, a status-count
// summary (with a stuck pending/failed alert), the retained document list, and
// the reconcile sweep that resubmits stuck documents once onboarded.

export interface ZatcaStatus {
  environment: string;
  has_csr: boolean;
  onboarded: boolean;
  gateway_configured: boolean;
  pih?: string | null;
  documents: number;
}

export interface ZatcaDocumentSummary {
  total: number;
  by_status: Record<string, number>;
  pending: number;
  failed: number;
  stuck: number;
  needs_attention: boolean;
  onboarded: boolean;
  gateway_configured: boolean;
}

export interface ZatcaDocument {
  id: number;
  invoice_number: string;
  icv?: number | null;
  invoice_hash?: string | null;
  status: string;
  submitted_at?: string | null;
  retention_until?: string | null;
  created_at?: string | null;
}

export interface ZatcaReportPendingResult {
  processed: number;
  cleared: number;
  reported: number;
  pending: number;
  failed: number;
}

export async function getZatcaStatus(): Promise<ZatcaStatus> {
  const res = await client.apiCall.invoke<ZatcaStatus>({
    url: '/api/v1/zatca/status',
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function getZatcaDocumentSummary(): Promise<ZatcaDocumentSummary> {
  const res = await client.apiCall.invoke<ZatcaDocumentSummary>({
    url: '/api/v1/zatca/documents/summary',
    method: 'GET',
    data: {},
  });
  return res.data;
}

// Server-side paginated (OPS-05): the fiscal archive grows one row per invoice.
export async function getZatcaDocuments(
  skip = 0,
  limit = 50,
): Promise<{ items: ZatcaDocument[]; total: number }> {
  const res = await client.apiCall.invoke<{ items: ZatcaDocument[]; total: number }>({
    url: '/api/v1/zatca/documents',
    method: 'GET',
    data: { skip, limit },
  });
  return res.data;
}

export async function reportPendingZatcaDocuments(): Promise<ZatcaReportPendingResult> {
  const res = await client.apiCall.invoke<ZatcaReportPendingResult>({
    url: '/api/v1/zatca/documents/report-pending',
    method: 'POST',
    data: {},
  });
  return res.data;
}

// ---------- ZATCA onboarding wizard (ISSUE-018) ----------
// The three Fatoora onboarding steps surfaced for the in-app wizard: generate
// the EGS keypair + CSR, exchange the CSR + portal OTP for a compliance CSID,
// then promote it to a production CSID. Each is client-scoped server-side.

export interface ZatcaCsrResult {
  csr_pem: string;
  csr_base64: string;
  public_key_pem: string;
}

export interface ZatcaOnboardResult {
  onboarded: boolean;
  message: string;
}

export async function onboardGenerateCsr(): Promise<ZatcaCsrResult> {
  const res = await client.apiCall.invoke<ZatcaCsrResult>({
    url: '/api/v1/zatca/onboard/csr',
    method: 'POST',
    data: {},
  });
  return res.data;
}

export async function onboardComplianceCsid(otp: string): Promise<ZatcaOnboardResult> {
  const res = await client.apiCall.invoke<ZatcaOnboardResult>({
    url: '/api/v1/zatca/onboard/compliance-csid',
    method: 'POST',
    data: { otp },
  });
  return res.data;
}

export async function onboardProductionCsid(): Promise<ZatcaOnboardResult> {
  const res = await client.apiCall.invoke<ZatcaOnboardResult>({
    url: '/api/v1/zatca/onboard/production-csid',
    method: 'POST',
    data: {},
  });
  return res.data;
}

// ---------- ZATCA hash-chain integrity (ZA-04, parity #13) ----------
// Walks the archived documents in counter (icv) order, asserting each one chains
// onto the prior invoice_hash and that every ECDSA stamp verifies. Reports the
// first icv that breaks the chain or fails its signature.

export interface ZatcaIntegrityResult {
  ok: boolean;
  total: number;
  chain_ok: boolean;
  signatures_ok: boolean;
  broken_at?: number | null;
  detail?: string | null;
}

export async function getZatcaIntegrity(): Promise<ZatcaIntegrityResult> {
  const res = await client.apiCall.invoke<ZatcaIntegrityResult>({
    url: '/api/v1/zatca/integrity',
    method: 'GET',
    data: {},
  });
  return res.data;
}

// ---------- Operations / observability (parity #10) ----------
// Surfaces the production telemetry endpoints into an ops console: detailed
// health, owner-scoped API-usage metering, the platform-admin performance
// monitor, and the cross-entity global search.

export interface OpsHealth {
  status: string; // "healthy" | "degraded"
  checks: {
    database: string;
    rate_limiter: string;
    performance_monitor: string;
    timestamp: string;
  } & Record<string, string>;
}

export interface ApiUsageEndpoint {
  endpoint: string;
  request_count: number;
  avg_response_time_ms: number;
}

export interface ApiUsageStats {
  user_id: string;
  total_requests: number;
  endpoints: ApiUsageEndpoint[];
  rate_limit: {
    remaining_tokens: number;
    max_tokens: number;
    refill_rate_per_second: number;
  };
}

export interface OpsMetricsSummary {
  total_requests: number;
  total_errors: number;
  error_rate: number;
  avg_response_ms: number;
  endpoints_tracked: number;
}

export interface OpsMetricsEndpoint {
  avg_ms: number;
  min_ms: number;
  max_ms: number;
  p95_ms: number;
  total_requests: number;
  error_count: number;
}

export interface OpsMetrics {
  summary: OpsMetricsSummary;
  endpoints: Record<string, OpsMetricsEndpoint>;
  rate_limiter: { remaining_tokens: number };
}

export interface GlobalSearchResults {
  query: string;
  total_results: number;
  results: {
    products: Array<{
      id: number;
      name: string;
      name_ar?: string | null;
      barcode?: string | null;
      price?: number | null;
      category?: string | null;
    }>;
    customers: Array<{
      id: number;
      name: string;
      phone?: string | null;
      email?: string | null;
    }>;
    transactions: Array<{
      id: number;
      invoice_number?: string | null;
      total_amount?: number | null;
      customer_name?: string | null;
      status?: string | null;
      created_at?: string | null;
    }>;
  };
}

export async function getOpsHealth(): Promise<OpsHealth> {
  const res = await client.apiCall.invoke<OpsHealth>({
    url: '/api/v1/production/health/detailed',
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function getApiUsageStats(): Promise<ApiUsageStats> {
  const res = await client.apiCall.invoke<ApiUsageStats>({
    url: '/api/v1/production/api-usage/stats',
    method: 'GET',
    data: {},
  });
  return res.data;
}

// Platform-admin scoped: 403s for a standard merchant (role "user"). Callers
// must treat a 403 as "not authorized", distinct from a real load failure.
export async function getOpsMetrics(): Promise<OpsMetrics> {
  const res = await client.apiCall.invoke<OpsMetrics>({
    url: '/api/v1/production/metrics',
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function globalSearch(q: string, limit = 20): Promise<GlobalSearchResults> {
  const res = await client.apiCall.invoke<GlobalSearchResults>({
    url: '/api/v1/production/search',
    method: 'GET',
    data: { q, limit },
  });
  return res.data;
}

// ---------- Omnichannel — Salla connector (OMN-01..03, F-046) ----------
// Connect the merchant's Salla store, read the connection status, and list the
// online orders that were imported as POS sales (decrementing the shared stock).

export interface SallaConnection {
  connected: boolean;
  store_id?: string | null;
  webhook_secret_set: boolean;
}

export interface ChannelOrder {
  id: number;
  provider: string;
  external_order_id: string;
  external_reference?: string | null;
  transaction_id?: number | null;
  status: string;
  customer_name?: string | null;
  customer_phone?: string | null;
  total_amount?: number | null;
  currency?: string | null;
  created_at?: string | null;
}

export interface ChannelOrderList {
  items: ChannelOrder[];
  total: number;
  page: number;
  page_size: number;
}

export async function getSallaConnection(): Promise<SallaConnection> {
  const res = await client.apiCall.invoke<SallaConnection>({
    url: '/api/v1/omnichannel/salla/connection',
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function connectSalla(
  storeId: string,
  webhookSecret?: string
): Promise<SallaConnection> {
  const res = await client.apiCall.invoke<SallaConnection>({
    url: '/api/v1/omnichannel/salla/connect',
    method: 'POST',
    data: { store_id: storeId, webhook_secret: webhookSecret || undefined },
  });
  return res.data;
}

export async function getChannelOrders(page = 1, pageSize = 20): Promise<ChannelOrderList> {
  const res = await client.apiCall.invoke<ChannelOrderList>({
    url: `/api/v1/omnichannel/channel-orders?page=${page}&page_size=${pageSize}`,
    method: 'GET',
    data: {},
  });
  return res.data;
}

// #237: health of the stuck-claim crash-recovery sweep (REV-05). A non-zero
// stuck_count means a settler crashed and the bounded sweep has not recovered the
// claim yet (un-healthy); last_run_at / last_reopened report the last unattended run.
export interface OmnichannelSweepStatus {
  last_run_at?: string | null;
  last_reopened?: number | null;
  stuck_count: number;
  oldest_stuck_age_seconds?: number | null;
  threshold_seconds: number;
  healthy: boolean;
}

export async function getOmnichannelSweepStatus(): Promise<OmnichannelSweepStatus> {
  const res = await client.apiCall.invoke<OmnichannelSweepStatus>({
    url: '/api/v1/omnichannel/sweep-status',
    method: 'GET',
    data: {},
  });
  return res.data;
}

// ---------- Aggregator — Deliverect-class delivery middleware (F-060) ----------
// Connect the restaurant's aggregator middleware location (Jahez / HungerStation
// arrive only through a Deliverect / Delivery-Hero POS-partner middleware). Ingested
// orders fire to the KDS and book a ZATCA sale that decrements the shared stock; they
// surface in the same back-office channel-orders list (getChannelOrders) by provider.

export interface AggregatorConnection {
  connected: boolean;
  location_id?: string | null;
  webhook_secret_set: boolean;
}

export async function getAggregatorConnection(): Promise<AggregatorConnection> {
  const res = await client.apiCall.invoke<AggregatorConnection>({
    url: '/api/v1/aggregator/connection',
    method: 'GET',
    data: {},
  });
  return res.data;
}

export async function connectAggregator(
  locationId: string,
  webhookSecret?: string
): Promise<AggregatorConnection> {
  const res = await client.apiCall.invoke<AggregatorConnection>({
    url: '/api/v1/aggregator/connect',
    method: 'POST',
    data: { location_id: locationId, webhook_secret: webhookSecret || undefined },
  });
  return res.data;
}

// ISSUE-059: single-use / unique discount codes. Distinct from the reusable
// discount definitions (one shared code with a usage cap) — these are minted in
// batches, each redeemable exactly once within an optional validity window. The
// server generates the codes and consumes the one-and-only use atomically.
export interface UniqueDiscountCode {
  id: number;
  user_id: string;
  batch_id: string;
  code: string;
  type: string;
  value: number;
  min_purchase?: number | null;
  redeemed: boolean;
  redeemed_at?: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  created_at?: string | null;
}

export async function generateDiscountCodes(data: {
  count: number;
  type: string;
  value: number;
  min_purchase?: number;
  starts_at?: string;
  ends_at?: string;
}): Promise<{ batch_id: string; count: number; codes: UniqueDiscountCode[] }> {
  const res = await client.apiCall.invoke<{
    batch_id: string;
    count: number;
    codes: UniqueDiscountCode[];
  }>({
    url: '/api/v1/entities/discount-codes/generate',
    method: 'POST',
    data,
  });
  return res.data;
}

export async function redeemDiscountCode(
  code: string,
  subtotal: number
): Promise<{ valid: boolean; code: string; type: string; value: number; discount_amount: number }> {
  const res = await client.apiCall.invoke<{
    valid: boolean;
    code: string;
    type: string;
    value: number;
    discount_amount: number;
  }>({
    url: '/api/v1/entities/discount-codes/redeem',
    method: 'POST',
    data: { code, subtotal },
  });
  return res.data;
}