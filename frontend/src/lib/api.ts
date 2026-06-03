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
}

export async function createTransaction(data: {
  items: { product_id: number; name: string; quantity: number; price: number; vat_rate: number }[];
  payment_method: string;
  customer_name?: string;
  customer_phone?: string;
  // F-018/ZA-06: buyer VAT for a B2B sale. When set (or resolvable from the
  // selected customer's saved record) the invoice carries the buyer tax block and
  // routes to clearance once it clears the threshold.
  customer_vat_number?: string;
  // POS-01: persist the applied order discount so totals match what the cashier saw.
  discount_amount?: number;
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

export async function getTransactions(page = 1, pageSize = 20) {
  const response = await client.apiCall.invoke({
    url: '/api/v1/pos/transactions',
    method: 'GET',
    data: { page, page_size: pageSize },
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

// Agent Branding
export async function updateBranding(data: {
  logo_url?: string;
  primary_color?: string;
  secondary_color?: string;
  font_family?: string;
  button_radius?: string;
  default_language?: string;
}) {
  const response = await client.apiCall.invoke({
    url: '/api/v1/branding/update',
    method: 'PUT',
    data,
  });
  return response.data;
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
  return response.data;
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

// Procurement (Phase 6): receive a purchase order — the backend increments
// product stock, records cost, and advances the PO to 'received' (idempotent).
export async function receivePurchaseOrder(poId: number) {
  const response = await client.apiCall.invoke({
    url: `/api/v1/entities/purchase_orders/${poId}/receive`,
    method: 'POST',
    data: {},
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