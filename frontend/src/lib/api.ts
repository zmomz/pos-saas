import { createClient } from './atomsClient';

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
}

export interface PaymentEntry {
  method: string; // 'cash' | 'card' | 'transfer' | 'loyalty'
  amount: number;
}

export async function createTransaction(data: {
  items: { product_id: number; name: string; quantity: number; price: number; vat_rate: number }[];
  payment_method: string;
  customer_name?: string;
  customer_phone?: string;
  // POS-01: persist the applied order discount so totals match what the cashier saw.
  discount_amount?: number;
  // POS-02: split tenders (cash + card + …). Per-method amounts must sum to the total.
  payments?: PaymentEntry[];
  // Loyalty: identify the customer to accrue points; redeem_points spends balance.
  customer_id?: number;
  redeem_points?: number;
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
}

// POS-07: refund a sale by issuing a ZATCA credit note (type 381). Restores
// inventory and signs the credit note server-side; returns its number + QR.
export async function refundTransaction(transactionId: number): Promise<RefundResult> {
  const response = await client.apiCall.invoke<RefundResult>({
    url: `/api/v1/pos/transactions/${transactionId}/refund`,
    method: 'POST',
    data: {},
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