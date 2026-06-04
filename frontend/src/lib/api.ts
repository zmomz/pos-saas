import { createClient, uploadMultipart, getBlob } from './atomsClient';

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

// MA-08 / RSL-08 / RPT-09 (F-023): platform-wide economics for the master operator
// console — MRR (yearly plans normalized to fee/12), churn (suspended share),
// active merchants, and a revenue-by-agent leaderboard from the commission ledger.
export interface AgentEconomics {
  agent_id: number;
  company_name: string;
  is_active: boolean;
  total_clients: number;
  active_clients: number;
  mrr: number;
  collected: number;
  master_owed: number;
  net: number;
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
export async function getAgentClients(skip = 0, limit = 50) {
  const response = await client.apiCall.invoke({
    url: '/api/v1/tenant/agent/clients',
    method: 'GET',
    data: { skip, limit },
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

// RSL-01/02 (F-029): the agent's settled-subscription economics from the
// commission/revenue-split ledger. collected == master_owed + net.
export interface RevenueByClient {
  client_id: number;
  business_name: string;
  collected: number;
  master_owed: number;
  net: number;
  payments: number;
}

export interface AgentRevenue {
  collected: number;
  master_owed: number;
  net: number;
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
  // 'cash' | 'card' | 'mada' | 'applepay' | 'stcpay' | 'tabby' | 'tamara' | 'transfer' | 'loyalty'
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
}): Promise<TransactionResult> {
  const response = await client.apiCall.invoke<TransactionResult>({
    url: '/api/v1/pos/transaction',
    method: 'POST',
    data,
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
  items: { product_id: number; name: string; name_ar?: string; price: number; quantity: number }[];
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

export async function getHeldSales(): Promise<{ items: HeldTicket[]; total: number }> {
  const response = await client.apiCall.invoke<{ items: HeldTicket[]; total: number }>({
    url: '/api/v1/pos/held',
    method: 'GET',
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

export async function getPackages() {
  const response = await client.entities.packages.queryAll({
    query: {},
    limit: 20,
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
export async function getProductsList(category?: string, search?: string) {
  const params: Record<string, string> = {};
  if (category) params.category = category;
  if (search) params.search = search;
  const queryString = new URLSearchParams(params).toString();
  const url = queryString ? `/api/v1/products/list?${queryString}` : '/api/v1/products/list';
  const response = await client.apiCall.invoke({
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
  category?: string;
  vat_rate?: number;
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

export async function getLowStockProducts() {
  const response = await client.apiCall.invoke({
    url: '/api/v1/products/low-stock',
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

// Package Management (Master Admin)
export async function getPackagesList() {
  const response = await client.apiCall.invoke({
    url: '/api/v1/packages/list',
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
}) {
  const response = await client.entities.customers.create({ data });
  return response.data;
}

export async function updateCustomer(id: string, data: Record<string, unknown>) {
  const response = await client.entities.customers.update({ id, data });
  return response.data;
}

export async function deleteCustomer(id: string) {
  await client.entities.customers.delete({ id });
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

// Expense Management
export async function getExpenses() {
  const response = await client.entities.expenses.query({
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

export async function getDiscounts() {
  const response = await client.entities.discounts.query({
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
  // Dunning state (CL-06): drive the client-facing overdue notice.
  dunning_attempts?: number;
  grace_deadline?: string;
  payments: SubscriptionPayment[];
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

// Client: pay the current subscription period (CL-04)
export async function payClientSubscription() {
  const response = await client.apiCall.invoke<SubscriptionStatus>({
    url: '/api/v1/tenant/client/subscription/pay',
    method: 'POST',
    data: {},
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

// POS-04: email a receipt for a transaction
export async function emailReceipt(transactionId: number, toEmail: string) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/transactions/${transactionId}/email`,
    method: 'POST',
    data: { to_email: toEmail },
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

// ---- Phase E ----

// Fetch a base64 ESC/POS byte stream for thermal printing (see lib/thermalPrint).
export async function getEscposReceipt(transactionId: number): Promise<string> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/pos/transactions/${transactionId}/escpos`,
    method: 'GET',
    data: {},
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

// AI sales forecast (moving-average projection).
export async function getSalesForecast(days = 30) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/production/analytics/forecast?days=${days}`,
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
}

export interface OrderTicket {
  id: number;
  table_id?: number | null;
  order_type?: string | null; // dine_in | takeaway | delivery
  status?: string | null; // open | held | fired | settled | void
  customer_name?: string | null;
  party_size?: number | null;
  notes?: string | null;
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

export async function getZatcaDocuments(): Promise<ZatcaDocument[]> {
  const res = await client.apiCall.invoke<ZatcaDocument[]>({
    url: '/api/v1/zatca/documents',
    method: 'GET',
    data: {},
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