import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getProducts, createTransaction, refundTransaction, voidTransaction, getTransactions, validateDiscount, getEscposReceipt, syncOfflineTransactions, getMyPermissions, canUse, downloadInvoicePdf, getCustomers, getBranches, holdSale, getHeldSales, recallSale, type MyPermissions, type TenderInfo, type HeldTicket } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatMoneyAr, toArabicDigits } from '@/lib/format';
import { enqueueTransaction, registerAutoFlush, isOnline } from '@/lib/offlineQueue';
import { printEscPos, isThermalPrintSupported } from '@/lib/thermalPrint';
import { useOnlineStatus } from '@/hooks/useOnlineStatus';
import ErrorState from '@/components/states/ErrorState';
import { ScanBarcode, RotateCcw, ShoppingCart, Tag, Check, X, Printer, FileDown, Camera, Pause, Play, WifiOff } from 'lucide-react';

interface Product {
  id: number;
  name: string;
  name_ar?: string;
  price: number;
  category?: string;
  sku?: string;
  barcode?: string;
}

interface CartItem {
  product: Product;
  quantity: number;
}

interface Receipt {
  id?: number;
  invoice_number: string;
  total_amount: number;
  vat_amount: number;
  subtotal: number;
  payment_method: string;
  zatca_qr_base64: string;
  zatca_status?: string;
  items: { name: string; quantity: number; price: number }[];
  discount_amount?: number;
  discount_code?: string;
  // Captured tenders (PAY-01) — show the network/approval proof on the receipt.
  tenders?: TenderInfo[];
}

interface Transaction {
  id?: number;
  invoice_number: string;
  total_amount: number;
  vat_amount: number;
  subtotal: number;
  payment_method: string;
  status?: string;
  items_json?: string;
  // POS-07: product_id is needed to drive partial/line-level refunds.
  items?: { product_id?: number; name: string; quantity: number; price: number; discount?: number }[];
  created_at?: string;
}

interface Discount {
  id: string;
  code: string;
  type: string; // 'percentage' | 'fixed'
  value: number;
  min_purchase?: number;
  max_uses?: number;
  is_active?: boolean;
}

type POSMode = 'sale' | 'refund';

export default function POSTerminal() {
  const [products, setProducts] = useState<Product[]>([]);
  // F-015 (UX-02): distinguish a products-fetch failure from an empty catalog —
  // a thrown load must render an error state, not the "no products" empty state.
  const [productsError, setProductsError] = useState(false);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [loading, setLoading] = useState(true);
  // F-015 (UX-02): a persistent connectivity indicator inside the full-screen POS
  // chrome (the global DashboardLayout banner can scroll out of the cashier's view).
  const online = useOnlineStatus();
  const [processing, setProcessing] = useState(false);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [mode, setMode] = useState<POSMode>('sale');
  const navigate = useNavigate();
  const { t } = useLanguage();

  // Barcode scanner state
  const [barcodeInput, setBarcodeInput] = useState('');
  const [barcodeMessage, setBarcodeMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  // POS-06: free-text product name search (complements barcode/SKU lookup).
  const [searchQuery, setSearchQuery] = useState('');

  // Loyalty checkout (Phase 4): pick the customer to accrue/redeem points and
  // optionally spend points as a discount at checkout.
  const [customers, setCustomers] = useState<{ id: number; name: string }[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('');
  const [redeemPoints, setRedeemPoints] = useState<string>('');

  // Multi-branch (Phase 6): tag the sale to a branch so its stock is deducted.
  const [branches, setBranches] = useState<{ id: number; name: string }[]>([]);
  const [selectedBranchId, setSelectedBranchId] = useState<string>('');

  // POS-06: live camera barcode scanning via the BarcodeDetector API.
  const [cameraScanning, setCameraScanning] = useState(false);

  // POS-02: split-tender payment. When enabled the cashier allocates the total
  // across multiple methods; the per-method amounts are sent as payments[].
  const [splitMode, setSplitMode] = useState(false);
  const [splitPayments, setSplitPayments] = useState<{ method: string; amount: number }[]>([
    { method: 'cash', amount: 0 },
    { method: 'card', amount: 0 },
  ]);

  // Discount state
  const [discountCode, setDiscountCode] = useState('');
  const [appliedDiscount, setAppliedDiscount] = useState<Discount | null>(null);
  const [discountError, setDiscountError] = useState('');
  const [applyingDiscount, setApplyingDiscount] = useState(false);

  // Refund state
  const [recentTransactions, setRecentTransactions] = useState<Transaction[]>([]);
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null);
  const [loadingTransactions, setLoadingTransactions] = useState(false);
  const [refundProcessing, setRefundProcessing] = useState(false);
  // POS-08: void (audited cancellation) of the selected sale.
  const [voidProcessing, setVoidProcessing] = useState(false);
  const [voidError, setVoidError] = useState('');
  // POS-07: per-line quantity to return, keyed by the line's index in the
  // selected transaction. Defaults to the full sold quantity (whole-invoice
  // refund); the cashier can dial any line down for a partial/line-level refund.
  const [refundQty, setRefundQty] = useState<Record<number, number>>({});

  // Offline POS (Phase E) state.
  const [queuedOffline, setQueuedOffline] = useState(false);

  // POS-10: park/hold & recall. Held tickets are saved carts the cashier can
  // resume; multiple may be open at once.
  const [heldTickets, setHeldTickets] = useState<HeldTicket[]>([]);
  const [showHeld, setShowHeld] = useState(false);
  const [holding, setHolding] = useState(false);
  const [heldError, setHeldError] = useState('');

  // Phase 3: permission-aware UI — gate the refund flow on `pos.refund` and the
  // audited void (POS-08) on `pos.void`.
  const [permissions, setPermissions] = useState<MyPermissions | null>(null);
  const canRefund = canUse(permissions, 'pos.refund');
  const canVoid = canUse(permissions, 'pos.void');

  useEffect(() => {
    loadProducts();
    getMyPermissions().then(setPermissions).catch(() => setPermissions(null));
    // Loyalty + multi-branch pickers (best-effort; absent data just hides them).
    getCustomers()
      .then((d) => setCustomers((d?.items || d || []) as { id: number; name: string }[]))
      .catch(() => setCustomers([]));
    getBranches()
      .then((d) => setBranches((d?.items || d || []) as { id: number; name: string }[]))
      .catch(() => setBranches([]));
    // POS-10: surface the count of parked tickets on the Held badge.
    loadHeld();
  }, []);

  // Offline POS (Phase E): replay any queued sales when connectivity returns.
  useEffect(() => {
    const unsubscribe = registerAutoFlush(syncOfflineTransactions);
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (mode === 'refund') {
      loadRecentTransactions();
    }
  }, [mode]);

  // Auto-clear barcode message after 3 seconds
  useEffect(() => {
    if (barcodeMessage) {
      const timer = setTimeout(() => setBarcodeMessage(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [barcodeMessage]);

  async function loadProducts() {
    setLoading(true);
    setProductsError(false);
    try {
      const data = await getProducts();
      setProducts(data?.items || data || []);
    } catch (err) {
      // F-015 (UX-02): surface a real error state. Previously this swallowed the
      // throw to console.error and fell through to the empty "no products" view,
      // so an outage looked identical to an empty catalog.
      console.error('Failed to load products:', err);
      setProductsError(true);
    } finally {
      setLoading(false);
    }
  }

  async function loadRecentTransactions() {
    setLoadingTransactions(true);
    try {
      const data = await getTransactions(1, 20);
      const raw = (data?.transactions || data?.items || data || []) as Transaction[];
      // POS-07: parse items_json into typed line items (with product_id) so the
      // refund panel can offer per-line quantity selection.
      const parsed = raw.map((txn) => {
        let items = txn.items;
        if (!items && txn.items_json) {
          try {
            items = JSON.parse(txn.items_json);
          } catch {
            items = [];
          }
        }
        return { ...txn, items: items || [] };
      });
      setRecentTransactions(parsed);
    } catch (err) {
      console.error('Failed to load transactions:', err);
    } finally {
      setLoadingTransactions(false);
    }
  }

  // ---- POS-10: park/hold & recall ----
  async function loadHeld() {
    try {
      const data = await getHeldSales();
      setHeldTickets(data?.items || []);
      setHeldError('');
    } catch (err) {
      console.error('Failed to load held tickets:', err);
      setHeldError(t('held_load_error'));
    }
  }

  async function handleHold() {
    if (cart.length === 0) return;
    setHolding(true);
    try {
      const customer = customers.find((c) => String(c.id) === selectedCustomerId);
      await holdSale({
        items: cart.map((item) => ({
          product_id: item.product.id,
          name: item.product.name,
          name_ar: item.product.name_ar,
          price: item.product.price,
          quantity: item.quantity,
        })),
        label: customer?.name || undefined,
        customer_name: customer?.name,
        branch_id:
          selectedBranchId && selectedBranchId !== 'all' ? Number(selectedBranchId) : undefined,
      });
      // Clear the cart so the cashier can serve the next customer; the ticket is
      // parked server-side and recallable.
      setCart([]);
      setAppliedDiscount(null);
      setDiscountCode('');
      setRedeemPoints('');
      setBarcodeMessage({ text: `✓ ${t('sale_held')}`, type: 'success' });
      await loadHeld();
    } catch (err) {
      console.error('Failed to hold sale:', err);
      setBarcodeMessage({ text: `✕ ${t('held_save_error')}`, type: 'error' });
    } finally {
      setHolding(false);
    }
  }

  async function handleRecall(heldId: number) {
    try {
      const recalled = await recallSale(heldId);
      // Rebuild cart items, preferring the live product (full sku/category/barcode)
      // and falling back to the snapshot stored on the held ticket.
      const restored: CartItem[] = recalled.items.map((it) => {
        const live = products.find((p) => p.id === it.product_id);
        const product: Product = live || {
          id: it.product_id,
          name: it.name,
          name_ar: it.name_ar,
          price: it.price,
        };
        return { product, quantity: it.quantity };
      });
      setCart(restored);
      if (recalled.branch_id) setSelectedBranchId(String(recalled.branch_id));
      setShowHeld(false);
      setBarcodeMessage({ text: `✓ ${t('sale_recalled')}`, type: 'success' });
      await loadHeld();
    } catch (err) {
      console.error('Failed to recall sale:', err);
      setBarcodeMessage({ text: `✕ ${t('held_recall_error')}`, type: 'error' });
    }
  }

  function addToCart(product: Product) {
    setCart((prev) => {
      const existing = prev.find((item) => item.product.id === product.id);
      if (existing) {
        return prev.map((item) =>
          item.product.id === product.id ? { ...item, quantity: item.quantity + 1 } : item
        );
      }
      return [...prev, { product, quantity: 1 }];
    });
  }

  function updateQuantity(productId: number, delta: number) {
    setCart((prev) =>
      prev
        .map((item) =>
          item.product.id === productId ? { ...item, quantity: item.quantity + delta } : item
        )
        .filter((item) => item.quantity > 0)
    );
  }

  function removeFromCart(productId: number) {
    setCart((prev) => prev.filter((item) => item.product.id !== productId));
  }

  // Resolve a scanned/typed code to a product and add it to the cart. Shared by
  // the keyboard scanner and the live camera scanner (POS-06).
  function lookupAndAdd(code: string): boolean {
    const barcode = code.trim();
    if (!barcode) return false;
    const matchedProduct = products.find(
      (p) => p.barcode === barcode || p.sku === barcode
    );
    if (matchedProduct) {
      addToCart(matchedProduct);
      setBarcodeMessage({ text: `✓ ${matchedProduct.name} added`, type: 'success' });
      return true;
    }
    setBarcodeMessage({ text: `✕ No product found for "${barcode}"`, type: 'error' });
    return false;
  }

  // Camera barcode scanning via the native BarcodeDetector API (POS-06). Falls
  // back gracefully with a message when the browser/device doesn't support it.
  async function toggleCameraScan() {
    if (cameraScanning) {
      setCameraScanning(false);
      return;
    }
    const DetectorCtor = (window as unknown as { BarcodeDetector?: new (o?: unknown) => { detect: (s: unknown) => Promise<{ rawValue: string }[]> } }).BarcodeDetector;
    if (!DetectorCtor || !navigator.mediaDevices?.getUserMedia) {
      setBarcodeMessage({ text: '✕ Camera scanning not supported on this device', type: 'error' });
      return;
    }
    setCameraScanning(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      const video = document.createElement('video');
      video.srcObject = stream;
      await video.play();
      const detector = new DetectorCtor({ formats: ['ean_13', 'code_128', 'qr_code', 'upc_a'] });
      const stop = () => stream.getTracks().forEach((tr) => tr.stop());
      const tick = async () => {
        if (!video.srcObject) return;
        try {
          const codes = await detector.detect(video);
          if (codes.length > 0) {
            const found = lookupAndAdd(codes[0].rawValue);
            if (found) { stop(); setCameraScanning(false); return; }
          }
        } catch { /* transient frame error */ }
        if (video.srcObject) requestAnimationFrame(tick);
      };
      // Stop when the user toggles off: clearing srcObject ends the loop.
      requestAnimationFrame(tick);
      // Auto-stop after 20s so the camera never stays on indefinitely.
      setTimeout(() => { stop(); video.srcObject = null; setCameraScanning(false); }, 20000);
    } catch {
      setBarcodeMessage({ text: '✕ Could not access the camera', type: 'error' });
      setCameraScanning(false);
    }
  }

  // Barcode scan handler
  function handleBarcodeScan(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && barcodeInput.trim()) {
      lookupAndAdd(barcodeInput.trim());
      setBarcodeInput('');
    }
  }

  // Discount apply handler
  async function handleApplyDiscount() {
    if (!discountCode.trim()) return;
    setApplyingDiscount(true);
    setDiscountError('');
    try {
      // PRC-01: the server is authoritative for whether a code applies (active /
      // min-purchase / usage cap) and how much it is worth — never trust a
      // client-side computation. The use is only consumed when the sale commits.
      const result = await validateDiscount(discountCode.trim(), subtotal);
      setAppliedDiscount({
        id: result.code,
        code: result.code,
        type: result.type,
        value: result.value,
      });
      setDiscountError('');
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setDiscountError(detail || 'Invalid or expired discount code');
      setAppliedDiscount(null);
    } finally {
      setApplyingDiscount(false);
    }
  }

  function removeDiscount() {
    setAppliedDiscount(null);
    setDiscountCode('');
    setDiscountError('');
  }

  const subtotal = cart.reduce((sum, item) => sum + item.product.price * item.quantity, 0);

  // Calculate discount amount
  const discountAmount = appliedDiscount
    ? appliedDiscount.type === 'percentage'
      ? subtotal * (appliedDiscount.value / 100)
      : Math.min(appliedDiscount.value, subtotal)
    : 0;

  const discountedSubtotal = subtotal - discountAmount;
  const vatAmount = discountedSubtotal * 0.15;
  const total = discountedSubtotal + vatAmount;

  // POS-06: products filtered by the name-search box (Arabic name included).
  const filteredProducts = searchQuery.trim()
    ? products.filter((p) => {
        const q = searchQuery.trim().toLowerCase();
        return (
          p.name.toLowerCase().includes(q) ||
          (p.name_ar || '').toLowerCase().includes(q) ||
          (p.sku || '').toLowerCase().includes(q)
        );
      })
    : products;

  // POS-02: split tenders must add up to the invoice total before checkout.
  const splitTotal = splitPayments.reduce((s, p) => s + (Number(p.amount) || 0), 0);
  const splitBalanced = Math.abs(splitTotal - total) < 0.01;

  function updateSplitPayment(idx: number, field: 'method' | 'amount', value: string) {
    setSplitPayments((prev) =>
      prev.map((p, i) =>
        i === idx ? { ...p, [field]: field === 'amount' ? Number(value) || 0 : value } : p
      )
    );
  }

  // Customer-facing display sync: mirror the live cart into the localStorage key
  // the CustomerDisplay page polls, so a second screen shows items + totals.
  useEffect(() => {
    try {
      localStorage.setItem(
        'pos-customer-display',
        JSON.stringify({
          items: cart.map((item) => ({
            name: item.product.name,
            quantity: item.quantity,
            price: item.product.price,
          })),
          subtotal,
          vat: vatAmount,
          total,
          status: cart.length > 0 ? 'active' : 'idle',
        })
      );
    } catch {
      /* localStorage unavailable — display sync is best-effort */
    }
  }, [cart, subtotal, vatAmount, total]);

  async function handleCheckout() {
    if (cart.length === 0) return;
    // POS-02: a split payment must be fully allocated before we send it.
    if (splitMode && !splitBalanced) {
      setBarcodeMessage({ text: '✕ Split payments must equal the total', type: 'error' });
      return;
    }
    setProcessing(true);
    try {
      const items = cart.map((item) => ({
        product_id: item.product.id,
        name: item.product.name,
        // Carry the Arabic name so the always-Arabic thermal receipt prints it
        // (PRN-01 / L10N-06).
        name_ar: item.product.name_ar,
        quantity: item.quantity,
        price: item.product.price,
        vat_rate: 0.15,
      }));
      // POS-01/POS-02: persist the applied discount and (when split) the per-method
      // tenders. Inventory is deducted atomically by the backend as part of the sale.
      const result = await createTransaction({
        items,
        payment_method: paymentMethod,
        // PRC-01: when a code is applied the server re-prices and consumes it; the
        // discount_amount is only the cashier-visible preview (manual amounts with
        // no code are gated behind the pos.discount permission server-side).
        discount_code: appliedDiscount?.code,
        discount_amount: discountAmount > 0 ? discountAmount : undefined,
        payments: splitMode
          ? splitPayments.filter((p) => (Number(p.amount) || 0) > 0)
          : undefined,
        // Loyalty (Phase 4): accrue/redeem against the selected customer.
        customer_id:
          selectedCustomerId && selectedCustomerId !== 'walkin'
            ? Number(selectedCustomerId)
            : undefined,
        redeem_points: redeemPoints && Number(redeemPoints) > 0 ? Number(redeemPoints) : undefined,
        // Multi-branch (Phase 6): deduct from the selected branch's stock ledger.
        branch_id:
          selectedBranchId && selectedBranchId !== 'all' ? Number(selectedBranchId) : undefined,
      });

      setReceipt({
        id: result.id,
        invoice_number: result.invoice_number,
        total_amount: result.total_amount,
        vat_amount: result.vat_amount,
        subtotal: result.subtotal,
        payment_method: result.payment_method || paymentMethod,
        zatca_qr_base64: result.zatca_qr_base64 || '',
        zatca_status: result.zatca_status,
        items: cart.map((item) => ({
          name: item.product.name,
          quantity: item.quantity,
          price: item.product.price,
        })),
        discount_amount: discountAmount > 0 ? discountAmount : undefined,
        discount_code: appliedDiscount?.code,
        tenders: result.tenders,
      });
      // Flash the customer-facing display to a "thank you" state.
      try {
        localStorage.setItem(
          'pos-customer-display',
          JSON.stringify({ items: [], subtotal: 0, vat: 0, total: 0, status: 'paid' })
        );
      } catch { /* best-effort */ }
      setQueuedOffline(false);
      setCart([]);
      setAppliedDiscount(null);
      setDiscountCode('');
      setSplitMode(false);
      setSplitPayments([{ method: 'cash', amount: 0 }, { method: 'card', amount: 0 }]);
      setRedeemPoints('');
      setSelectedCustomerId('');
    } catch (err) {
      // Offline POS (Phase E): if the device is offline (or the network call
      // failed), buffer the sale in IndexedDB and replay it on reconnect rather
      // than losing it. A queued sale gets no fiscal QR until it syncs.
      if (!isOnline()) {
        try {
          const subtotal = cart.reduce((s, i) => s + i.product.price * i.quantity, 0);
          const taxable = Math.max(0, subtotal - discountAmount);
          const vat = Math.round(taxable * 0.15 * 100) / 100;
          const queued = await enqueueTransaction({
            subtotal,
            discount_amount: discountAmount,
            vat_amount: vat,
            total_amount: Math.round((taxable + vat) * 100) / 100,
            payment_method: paymentMethod,
            items: cart.map((item) => ({
              product_id: item.product.id,
              name: item.product.name,
              quantity: item.quantity,
              price: item.product.price,
            })),
          });
          setReceipt({
            invoice_number: queued.offline_id,
            total_amount: queued.total_amount || 0,
            vat_amount: queued.vat_amount || 0,
            subtotal: queued.subtotal || 0,
            payment_method: paymentMethod,
            zatca_qr_base64: '',
            items: cart.map((item) => ({
              name: item.product.name,
              quantity: item.quantity,
              price: item.product.price,
            })),
            discount_amount: discountAmount > 0 ? discountAmount : undefined,
            discount_code: appliedDiscount?.code,
          });
          setQueuedOffline(true);
          setCart([]);
          setAppliedDiscount(null);
          setDiscountCode('');
        } catch (queueErr) {
          console.error('Offline queue failed:', queueErr);
        }
      } else {
        console.error('Checkout failed:', err);
      }
    } finally {
      setProcessing(false);
    }
  }

  async function handleThermalPrint() {
    if (!receipt?.id) return;
    try {
      const payload = await getEscposReceipt(receipt.id);
      await printEscPos(payload);
    } catch (err) {
      console.error('Thermal print failed:', err);
    }
  }

  // POS-07: select a sale for refund and default every line's return quantity to
  // its full sold quantity (whole-invoice refund as the starting point).
  function selectTransactionForRefund(txn: Transaction) {
    setSelectedTransaction(txn);
    const defaults: Record<number, number> = {};
    (txn.items || []).forEach((item, idx) => {
      defaults[idx] = item.quantity;
    });
    setRefundQty(defaults);
  }

  function setLineRefundQty(idx: number, value: number, max: number) {
    const clamped = Math.max(0, Math.min(value, max));
    setRefundQty((prev) => ({ ...prev, [idx]: clamped }));
  }

  // Sum of the selected return quantities — drives the live refund total.
  const refundHasLineItems = (selectedTransaction?.items?.length ?? 0) > 0;
  const refundLines = (selectedTransaction?.items || [])
    .map((item, idx) => ({ item, qty: refundQty[idx] ?? 0 }))
    .filter((l) => l.qty > 0);
  const refundSelectedAmount = refundLines.reduce(
    (sum, l) => sum + l.item.price * l.qty,
    0
  );
  const refundAnythingSelected = refundLines.length > 0;
  const refundIsPartial =
    refundAnythingSelected &&
    (selectedTransaction?.items || []).some((item, idx) => (refundQty[idx] ?? 0) < item.quantity);
  // When the original lines can't be parsed we fall back to a whole-invoice
  // refund (legacy behavior), so the button stays enabled.
  const canSubmitRefund = refundHasLineItems ? refundAnythingSelected : true;

  async function handleRefund() {
    if (!selectedTransaction?.id || !canSubmitRefund) return;
    setRefundProcessing(true);
    try {
      // POS-07: build the returned lines. When the original lines carry a
      // product_id we send them so the backend credits only those units
      // (partial/line-level); otherwise we fall back to a whole-invoice refund.
      const selected = (selectedTransaction.items || [])
        .map((item, idx) => ({ item, qty: refundQty[idx] ?? 0 }))
        .filter((l) => l.qty > 0);
      const haveProductIds = selected.every((l) => typeof l.item.product_id === 'number');
      const lines = haveProductIds
        ? selected.map((l) => ({ product_id: l.item.product_id as number, quantity: l.qty }))
        : undefined;

      // The backend issues a real ZATCA credit note (type 381), restores the
      // returned units, and signs it. No negative-price fake refund.
      const result = await refundTransaction(selectedTransaction.id, lines);

      setReceipt({
        invoice_number: result.credit_note_number,
        total_amount: result.total_amount,
        vat_amount: 0,
        subtotal: 0,
        payment_method: 'refund',
        zatca_qr_base64: result.zatca_qr_base64 || '',
        zatca_status: result.zatca_status,
        items: selected.map((l) => ({
          name: l.item.name,
          quantity: l.qty,
          price: -Math.abs(l.item.price),
        })),
      });
      setSelectedTransaction(null);
      setRefundQty({});
    } catch (err) {
      console.error('Refund failed:', err);
    } finally {
      setRefundProcessing(false);
    }
  }

  // POS-08: void the selected sale. Unlike a refund this issues no credit note
  // — the backend marks it `voided`, restores stock, and writes an audit row
  // (gated by `pos.void`). A 409 means the invoice was already reported to ZATCA
  // and must be refunded instead; we surface that as an in-panel error.
  async function handleVoid() {
    if (!selectedTransaction?.id || voidProcessing) return;
    setVoidError('');
    setVoidProcessing(true);
    try {
      await voidTransaction(selectedTransaction.id);
      setSelectedTransaction(null);
      setRefundQty({});
      await loadRecentTransactions();
    } catch (err) {
      console.error('Void failed:', err);
      setVoidError(t('void_failed'));
    } finally {
      setVoidProcessing(false);
    }
  }

  function handleNewSale() {
    setReceipt(null);
    setCart([]);
    setMode('sale');
    setSelectedTransaction(null);
    setRefundQty({});
    setVoidError('');
    setAppliedDiscount(null);
    setDiscountCode('');
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  // Receipt view (for both sale and refund).
  //
  // The receipt is ALWAYS rendered in Arabic (RTL, Arabic-Indic numerals, SAR)
  // regardless of the cashier's UI language — SRS §7 "receipts/quotations always
  // Arabic". The surrounding action buttons stay neutral; only the fiscal
  // receipt content is forced Arabic.
  if (receipt) {
    const isRefund = receipt.payment_method === 'refund';
    const paymentAr: Record<string, string> = {
      cash: 'نقدي',
      card: 'بطاقة',
      mada: 'مدى',
      applepay: 'Apple Pay',
      stcpay: 'STC Pay',
      tabby: 'تابي',
      tamara: 'تمارا',
      transfer: 'تحويل',
      refund: 'استرجاع',
      mixed: 'مدفوعات متعددة',
    };
    // Arabic tender labels for the captured-approval lines (always-Arabic receipt).
    const tenderAr: Record<string, string> = {
      cash: 'نقدي',
      card: 'بطاقة',
      mada: 'مدى',
      applepay: 'Apple Pay',
      stcpay: 'STC Pay',
      tabby: 'تابي',
      tamara: 'تمارا',
      transfer: 'تحويل',
    };
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
        <Card className="w-full max-w-md bg-slate-800 border-slate-700">
          <CardContent dir="rtl" lang="ar" className="p-6 space-y-4 text-right">
            <div className="text-center">
              <h2 className={`text-xl font-bold ${isRefund ? 'text-orange-400' : 'text-green-400'}`}>
                {isRefund ? '↩ تمت معالجة الاسترجاع' : '✓ تمت العملية بنجاح'}
              </h2>
              <p className="text-slate-400 mt-1">رقم الفاتورة: {receipt.invoice_number}</p>
            </div>

            <div className="border-t border-slate-700 pt-4 space-y-2">
              {receipt.items.map((item, idx) => (
                <div key={idx} className="flex justify-between text-slate-300 text-sm">
                  <span>{item.name} ×{toArabicDigits(item.quantity)}</span>
                  <span>{formatMoneyAr(item.price * item.quantity)}</span>
                </div>
              ))}
            </div>

            <div className="border-t border-slate-700 pt-3 space-y-1">
              <div className="flex justify-between text-slate-400 text-sm">
                <span>المجموع الفرعي</span>
                <span>{formatMoneyAr(receipt.subtotal || 0)}</span>
              </div>
              {receipt.discount_amount && receipt.discount_amount > 0 && (
                <div className="flex justify-between text-green-400 text-sm">
                  <span>الخصم ({receipt.discount_code})</span>
                  <span>-{formatMoneyAr(receipt.discount_amount)}</span>
                </div>
              )}
              <div className="flex justify-between text-slate-400 text-sm">
                <span>ضريبة القيمة المضافة</span>
                <span>{formatMoneyAr(receipt.vat_amount || 0)}</span>
              </div>
              <div className="flex justify-between text-white font-bold">
                <span>الإجمالي</span>
                <span>{formatMoneyAr(receipt.total_amount || 0)}</span>
              </div>
            </div>

            <div className="flex justify-between text-slate-300 text-sm">
              <span>طريقة الدفع</span>
              <Badge className={`${isRefund ? 'bg-orange-600' : 'bg-blue-600'} text-white`}>
                {paymentAr[receipt.payment_method] || receipt.payment_method}
              </Badge>
            </div>

            {/* PAY-01: captured tender approval (network + auth code) for card-like
                tenders, so the receipt proves the card was actually charged. */}
            {receipt.tenders && receipt.tenders.some((tn) => tn.approval_code) && (
              <div className="border-t border-slate-700 pt-3 space-y-1">
                {receipt.tenders
                  .filter((tn) => tn.approval_code)
                  .map((tn, idx) => (
                    <div key={idx} className="flex justify-between text-slate-400 text-xs">
                      <span>
                        {tenderAr[tn.tender_type] || tn.tender_type}
                        {tn.last4 ? ` ••${toArabicDigits(tn.last4)}` : ''}
                      </span>
                      <span className="font-mono">
                        {tn.network ? `${tn.network} · ` : ''}
                        موافقة {tn.approval_code}
                      </span>
                    </div>
                  ))}
              </div>
            )}

            {/* ZATCA QR Code */}
            {receipt.zatca_qr_base64 && (
              <div className="border-t border-slate-700 pt-4">
                <p className="text-sm text-slate-400 mb-2 text-center">رمز الاستجابة السريعة (ZATCA)</p>
                <div className="flex justify-center">
                  <div className="bg-white p-3 rounded-lg">
                    <img
                      src={`data:image/png;base64,${receipt.zatca_qr_base64}`}
                      alt="ZATCA QR"
                      className="w-32 h-32"
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        target.style.display = 'none';
                        target.parentElement!.innerHTML = `<div class="w-32 h-32 flex items-center justify-center bg-gray-100 text-xs text-gray-600 break-all p-1 font-mono">${receipt.zatca_qr_base64.substring(0, 60)}...</div>`;
                      }}
                    />
                  </div>
                </div>
                {receipt.zatca_status && (
                  <p className="text-xs text-slate-500 mt-2 text-center">
                    حالة الفاتورة الإلكترونية: {{
                      signed: 'موقعة',
                      pending: 'بانتظار الإبلاغ',
                      reported: 'تم الإبلاغ',
                      cleared: 'معتمدة',
                      failed: 'فشل الإبلاغ',
                    }[receipt.zatca_status] || receipt.zatca_status}
                  </p>
                )}
              </div>
            )}

            {queuedOffline && (
              <div className="rounded-md bg-amber-900/40 border border-amber-700 text-amber-200 text-sm p-3 text-center">
                تم حفظ العملية دون اتصال وسيتم مزامنتها عند عودة الإنترنت
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <Button onClick={handleNewSale} className="flex-1 bg-blue-600 hover:bg-blue-700 text-white">
                {t('new_sale')}
              </Button>
              {receipt.id && (
                <Button
                  variant="outline"
                  onClick={() => downloadInvoicePdf(receipt.id!, receipt.invoice_number)}
                  className="border-slate-600 text-slate-300 hover:bg-slate-700"
                  title={t('download_pdf') || 'Download PDF'}
                >
                  <FileDown className="w-4 h-4" />
                </Button>
              )}
              {receipt.id && isThermalPrintSupported() && (
                <Button
                  variant="outline"
                  onClick={handleThermalPrint}
                  className="border-slate-600 text-slate-300 hover:bg-slate-700"
                  title="Thermal print"
                >
                  <Printer className="w-4 h-4" />
                </Button>
              )}
              <Button
                variant="outline"
                onClick={() => navigate('/client')}
                className="flex-1 border-slate-600 text-slate-300 hover:bg-slate-700"
              >
                {t('back')}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Refund Mode View
  if (mode === 'refund') {
    return (
      <div className="min-h-screen bg-slate-900 flex flex-col">
        {/* Header */}
        <div className="bg-slate-800 border-b border-slate-700 p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <RotateCcw className="w-5 h-5 text-orange-400" />
            <h2 className="text-lg font-bold text-white">Refund Mode</h2>
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={() => { setMode('sale'); setSelectedTransaction(null); setRefundQty({}); }}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              <ShoppingCart className="w-4 h-4 me-2" />
              {t('new_sale')}
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate('/client')}
              className="border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              {t('back')}
            </Button>
          </div>
        </div>

        <div className="flex-1 flex flex-col lg:flex-row">
          {/* Transaction List */}
          <div className="flex-1 p-4 overflow-y-auto">
            <h3 className="text-white font-semibold mb-3">{t('recent_transactions')}</h3>
            {loadingTransactions ? (
              <div className="text-slate-400 text-center py-8">{t('loading')}</div>
            ) : recentTransactions.length === 0 ? (
              <div className="text-slate-500 text-center py-8">No transactions found</div>
            ) : (
              <div className="space-y-2">
                {recentTransactions.map((txn, idx) => (
                  <Card
                    key={txn.id || idx}
                    className={`bg-slate-800 border-slate-700 cursor-pointer transition-colors ${
                      selectedTransaction?.invoice_number === txn.invoice_number
                        ? 'border-orange-500 ring-1 ring-orange-500'
                        : 'hover:border-slate-500'
                    }`}
                    onClick={() => selectTransactionForRefund(txn)}
                  >
                    <CardContent className="p-4">
                      <div className="flex justify-between items-center">
                        <div>
                          <p className="text-white font-medium text-sm">{txn.invoice_number}</p>
                          <p className="text-slate-400 text-xs mt-1">
                            {txn.created_at ? new Date(txn.created_at).toLocaleString() : 'N/A'}
                          </p>
                        </div>
                        <div className="text-end">
                          <p className="text-blue-400 font-bold">${txn.total_amount?.toFixed(2)}</p>
                          <Badge className="bg-slate-600 text-slate-300 text-xs mt-1">
                            {txn.payment_method}
                          </Badge>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>

          {/* Selected Transaction Detail */}
          <div className="w-full lg:w-96 bg-slate-800 border-t lg:border-t-0 lg:border-s border-slate-700 p-4">
            {selectedTransaction ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-white font-semibold">{t('refund_details')}</h3>
                  {selectedTransaction.status === 'partial_refunded' && (
                    <Badge className="bg-orange-900 text-orange-300 text-xs">
                      {t('already_partially_refunded')}
                    </Badge>
                  )}
                </div>
                <div className="bg-slate-700 rounded-lg p-4 space-y-2">
                  <div className="flex justify-between text-slate-300 text-sm">
                    <span>{t('invoice')}</span>
                    <span>{selectedTransaction.invoice_number}</span>
                  </div>
                  <div className="flex justify-between text-slate-300 text-sm">
                    <span>{t('payment_method')}</span>
                    <span>{selectedTransaction.payment_method}</span>
                  </div>

                  {refundHasLineItems ? (
                    <div className="border-t border-slate-600 pt-2 mt-2 space-y-2">
                      {/* POS-07: choose how many of each line to return. */}
                      <p className="text-slate-400 text-xs">{t('select_return_qty')}</p>
                      {selectedTransaction.items!.map((item, idx) => {
                        const qty = refundQty[idx] ?? 0;
                        return (
                          <div key={idx} className="flex items-center justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <p className="text-slate-200 text-xs truncate">{item.name}</p>
                              <p className="text-slate-500 text-[11px]">
                                ${Math.abs(item.price).toFixed(2)} · {item.quantity} {t('sold')}
                              </p>
                            </div>
                            <div className="flex items-center gap-1">
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="h-7 w-7 p-0 border-slate-500 text-slate-200"
                                onClick={() => setLineRefundQty(idx, qty - 1, item.quantity)}
                                disabled={qty <= 0}
                              >
                                −
                              </Button>
                              <Input
                                type="number"
                                value={qty}
                                min={0}
                                max={item.quantity}
                                onChange={(e) =>
                                  setLineRefundQty(idx, Number(e.target.value), item.quantity)
                                }
                                className="h-7 w-12 text-center bg-slate-800 border-slate-500 text-white text-xs"
                              />
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="h-7 w-7 p-0 border-slate-500 text-slate-200"
                                onClick={() => setLineRefundQty(idx, qty + 1, item.quantity)}
                                disabled={qty >= item.quantity}
                              >
                                +
                              </Button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : null}

                  <div className="border-t border-slate-600 pt-2 mt-2">
                    <div className="flex justify-between text-white font-bold mt-1">
                      <span>
                        {t('refund_amount')}
                        {refundHasLineItems && refundIsPartial && (
                          <span className="ms-2 text-orange-300 text-xs font-normal">
                            ({t('partial_refund')})
                          </span>
                        )}
                      </span>
                      <span className="text-orange-400">
                        $
                        {(refundHasLineItems
                          ? refundSelectedAmount
                          : selectedTransaction.total_amount || 0
                        ).toFixed(2)}
                      </span>
                    </div>
                  </div>
                </div>

                <Button
                  onClick={handleRefund}
                  disabled={refundProcessing || !canRefund || !canSubmitRefund}
                  className="w-full bg-orange-600 hover:bg-orange-700 text-white py-6 text-lg disabled:opacity-50"
                >
                  {refundProcessing ? t('loading') : `↩ ${t('process_refund')}`}
                </Button>
                {!canRefund && (
                  <p className="text-center text-sm text-orange-400/80 mt-2">
                    {t('refund_no_permission')}
                  </p>
                )}

                {/* POS-08: audited void of a sale rung in error (gated by
                    `pos.void`). Only offered on a live sale — a credit note,
                    voided, or already-refunded transaction cannot be voided. */}
                {canVoid &&
                  ['completed', '', null, undefined].includes(
                    selectedTransaction.status as string,
                  ) && (
                    <div className="border-t border-slate-600 pt-3 mt-3">
                      <Button
                        onClick={handleVoid}
                        disabled={voidProcessing}
                        variant="outline"
                        className="w-full border-red-600 text-red-400 hover:bg-red-600/10 disabled:opacity-50"
                      >
                        {voidProcessing ? t('loading') : `✕ ${t('void_sale')}`}
                      </Button>
                      <p className="text-center text-xs text-slate-500 mt-2">
                        {t('void_sale_hint')}
                      </p>
                      {voidError && (
                        <p role="alert" className="text-center text-sm text-red-400 mt-2">
                          {voidError}
                        </p>
                      )}
                    </div>
                  )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-slate-500">
                <p className="text-center">{t('select_transaction_refund')}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Sale Mode View (default)
  return (
    <div className="min-h-screen bg-slate-900 flex flex-col lg:flex-row">
      {/* Product Grid */}
      <div className="flex-1 p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold text-white">{t('products')}</h2>
            {/* F-015 (UX-02): persistent offline indicator inside the POS chrome. */}
            {!online && (
              <span
                role="status"
                className="inline-flex items-center gap-1 rounded-full border border-amber-700 bg-amber-900/40 px-2 py-0.5 text-xs text-amber-200"
              >
                <WifiOff className="h-3 w-3" />
                {t('offline')}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={() => { setShowHeld(true); loadHeld(); }}
              variant="outline"
              className="relative border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              <Pause className="w-4 h-4 me-2" />
              {t('held_tickets')}
              {heldTickets.length > 0 && (
                <span className="ms-2 inline-flex items-center justify-center min-w-5 h-5 px-1 rounded-full bg-blue-600 text-white text-xs">
                  {heldTickets.length}
                </span>
              )}
            </Button>
            {canRefund && (
              <Button
                onClick={() => setMode('refund')}
                variant="outline"
                className="border-orange-600 text-orange-400 hover:bg-orange-600/10"
              >
                <RotateCcw className="w-4 h-4 me-2" />
                Refund
              </Button>
            )}
            <Button
              variant="outline"
              onClick={() => navigate('/client')}
              className="border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              {t('back')}
            </Button>
          </div>
        </div>

        {/* Barcode Scanner Input */}
        <div className="mb-4 relative">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <ScanBarcode className="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input
                value={barcodeInput}
                onChange={(e) => setBarcodeInput(e.target.value)}
                onKeyDown={handleBarcodeScan}
                placeholder="Scan barcode or enter SKU..."
                className="ps-10 bg-slate-800 border-slate-600 text-white placeholder:text-slate-500 focus:border-blue-500"
              />
            </div>
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('search_products')}
              className="flex-1 bg-slate-800 border-slate-600 text-white placeholder:text-slate-500 focus:border-blue-500"
            />
            <Button
              type="button"
              variant={cameraScanning ? 'default' : 'outline'}
              onClick={toggleCameraScan}
              className="shrink-0 border-slate-600"
              title={t('scan_camera')}
            >
              <Camera className="w-4 h-4" />
            </Button>
          </div>
          {barcodeMessage && (
            <div className={`absolute top-full mt-1 start-0 text-xs px-3 py-1.5 rounded ${
              barcodeMessage.type === 'success'
                ? 'bg-green-900/50 text-green-400 border border-green-700'
                : 'bg-red-900/50 text-red-400 border border-red-700'
            }`}>
              {barcodeMessage.text}
            </div>
          )}
        </div>

        {/* Loyalty + branch checkout controls (Phase 4/6) */}
        <div className="mb-4 grid grid-cols-1 sm:grid-cols-3 gap-2">
          {customers.length > 0 && (
            <Select value={selectedCustomerId} onValueChange={setSelectedCustomerId}>
              <SelectTrigger className="bg-slate-800 border-slate-600 text-white">
                <SelectValue placeholder={t('select_customer')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="walkin">{t('walk_in_customer')}</SelectItem>
                {customers.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {selectedCustomerId && selectedCustomerId !== 'walkin' && (
            <Input
              type="number"
              min={0}
              value={redeemPoints}
              onChange={(e) => setRedeemPoints(e.target.value)}
              placeholder={t('redeem_points')}
              className="bg-slate-800 border-slate-600 text-white placeholder:text-slate-500"
            />
          )}
          {branches.length > 0 && (
            <Select value={selectedBranchId} onValueChange={setSelectedBranchId}>
              <SelectTrigger className="bg-slate-800 border-slate-600 text-white">
                <SelectValue placeholder={t('select_branch')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('all_branches')}</SelectItem>
                {branches.map((b) => (
                  <SelectItem key={b.id} value={String(b.id)}>{b.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {productsError ? (
          // F-015 (UX-02): error state distinct from the empty state, with retry.
          <ErrorState message={t('products_load_error')} onRetry={loadProducts} />
        ) : filteredProducts.length === 0 ? (
          <div className="text-center text-slate-500 py-12">{t('no_products')}</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
            {filteredProducts.map((product) => (
              <Card
                key={product.id}
                className="bg-slate-800 border-slate-700 cursor-pointer hover:border-blue-500 transition-colors"
                onClick={() => addToCart(product)}
              >
                <CardContent className="p-4 text-center">
                  <p className="text-white font-medium text-sm truncate">{product.name}</p>
                  {product.category && (
                    <p className="text-slate-500 text-xs mt-1">{product.category}</p>
                  )}
                  {product.barcode && (
                    <p className="text-slate-600 text-xs mt-0.5 font-mono">{product.barcode}</p>
                  )}
                  <p className="text-blue-400 font-bold mt-2">${product.price?.toFixed(2)}</p>
                  <Button size="sm" className="mt-2 w-full bg-blue-600 hover:bg-blue-700 text-white text-xs">
                    {t('add_to_cart')}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Cart Sidebar */}
      <div className="w-full lg:w-96 bg-slate-800 border-t lg:border-t-0 lg:border-s border-slate-700 p-4 flex flex-col">
        <h2 className="text-lg font-bold text-white mb-4">{t('cart')}</h2>

        <div className="flex-1 overflow-y-auto space-y-2">
          {cart.length === 0 ? (
            <p className="text-slate-500 text-center py-8">{t('empty_cart')}</p>
          ) : (
            cart.map((item) => (
              <div key={item.product.id} className="bg-slate-700 rounded-lg p-3">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <p className="text-white text-sm font-medium">{item.product.name}</p>
                    <p className="text-slate-400 text-xs">${item.product.price?.toFixed(2)} each</p>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => removeFromCart(item.product.id)}
                    className="text-red-400 hover:text-red-300 hover:bg-slate-600 h-6 w-6 p-0"
                  >
                    ✕
                  </Button>
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => updateQuantity(item.product.id, -1)}
                    className="h-7 w-7 p-0 border-slate-600 text-white hover:bg-slate-600"
                  >
                    -
                  </Button>
                  <span className="text-white text-sm w-8 text-center">{item.quantity}</span>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => updateQuantity(item.product.id, 1)}
                    className="h-7 w-7 p-0 border-slate-600 text-white hover:bg-slate-600"
                  >
                    +
                  </Button>
                  <span className="text-blue-400 font-medium text-sm ms-auto">
                    ${(item.product.price * item.quantity).toFixed(2)}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Totals & Checkout */}
        <div className="border-t border-slate-700 pt-4 mt-4 space-y-3">
          {/* Discount Code Input */}
          <div>
            <label className="text-slate-400 text-sm block mb-1">
              <Tag className="w-3 h-3 inline me-1" />
              Discount Code
            </label>
            {appliedDiscount ? (
              <div className="flex items-center gap-2 bg-green-900/30 border border-green-700 rounded-md px-3 py-2">
                <Check className="w-4 h-4 text-green-400" />
                <span className="text-green-400 text-sm flex-1">
                  {appliedDiscount.code} ({appliedDiscount.type === 'percentage' ? `${appliedDiscount.value}%` : `$${appliedDiscount.value}`} off)
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={removeDiscount}
                  className="h-6 w-6 p-0 text-red-400 hover:text-red-300 hover:bg-transparent"
                >
                  <X className="w-4 h-4" />
                </Button>
              </div>
            ) : (
              <div className="flex gap-2">
                <Input
                  value={discountCode}
                  onChange={(e) => { setDiscountCode(e.target.value); setDiscountError(''); }}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleApplyDiscount(); }}
                  placeholder="Enter code..."
                  className="bg-slate-700 border-slate-600 text-white placeholder:text-slate-500 text-sm"
                />
                <Button
                  size="sm"
                  onClick={handleApplyDiscount}
                  disabled={!discountCode.trim() || applyingDiscount}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-3 whitespace-nowrap"
                >
                  {applyingDiscount ? '...' : 'Apply'}
                </Button>
              </div>
            )}
            {discountError && (
              <p className="text-red-400 text-xs mt-1">{discountError}</p>
            )}
          </div>

          <div className="flex justify-between text-slate-400 text-sm">
            <span>{t('subtotal')}</span>
            <span>${subtotal.toFixed(2)}</span>
          </div>
          {discountAmount > 0 && (
            <div className="flex justify-between text-green-400 text-sm">
              <span>Discount</span>
              <span>-${discountAmount.toFixed(2)}</span>
            </div>
          )}
          <div className="flex justify-between text-slate-400 text-sm">
            <span>{t('vat')}</span>
            <span>${vatAmount.toFixed(2)}</span>
          </div>
          <div className="flex justify-between text-white font-bold text-lg">
            <span>{t('total')}</span>
            <span>${total.toFixed(2)}</span>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-slate-400 text-sm">{t('payment_method')}</label>
              <button
                type="button"
                onClick={() => setSplitMode((v) => !v)}
                className={`text-xs px-2 py-0.5 rounded border ${
                  splitMode
                    ? 'bg-blue-600 border-blue-500 text-white'
                    : 'border-slate-600 text-slate-300 hover:bg-slate-700'
                }`}
              >
                {t('split_payment')}
              </button>
            </div>
            {!splitMode ? (
              <Select value={paymentMethod} onValueChange={setPaymentMethod}>
                <SelectTrigger className="bg-slate-700 border-slate-600 text-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-slate-700 border-slate-600">
                  <SelectItem value="cash" className="text-white hover:bg-slate-600">{t('cash')}</SelectItem>
                  <SelectItem value="mada" className="text-white hover:bg-slate-600">{t('tender_mada')}</SelectItem>
                  <SelectItem value="card" className="text-white hover:bg-slate-600">{t('card')}</SelectItem>
                  <SelectItem value="applepay" className="text-white hover:bg-slate-600">{t('tender_applepay')}</SelectItem>
                  <SelectItem value="stcpay" className="text-white hover:bg-slate-600">{t('tender_stcpay')}</SelectItem>
                  <SelectItem value="tabby" className="text-white hover:bg-slate-600">{t('tender_tabby')}</SelectItem>
                  <SelectItem value="tamara" className="text-white hover:bg-slate-600">{t('tender_tamara')}</SelectItem>
                  <SelectItem value="bank_transfer" className="text-white hover:bg-slate-600">{t('bank_transfer')}</SelectItem>
                </SelectContent>
              </Select>
            ) : (
              <div className="space-y-2">
                {splitPayments.map((p, idx) => (
                  <div key={idx} className="flex gap-2">
                    <Select value={p.method} onValueChange={(v) => updateSplitPayment(idx, 'method', v)}>
                      <SelectTrigger className="bg-slate-700 border-slate-600 text-white flex-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-slate-700 border-slate-600">
                        <SelectItem value="cash" className="text-white hover:bg-slate-600">{t('cash')}</SelectItem>
                        <SelectItem value="mada" className="text-white hover:bg-slate-600">{t('tender_mada')}</SelectItem>
                        <SelectItem value="card" className="text-white hover:bg-slate-600">{t('card')}</SelectItem>
                        <SelectItem value="applepay" className="text-white hover:bg-slate-600">{t('tender_applepay')}</SelectItem>
                        <SelectItem value="stcpay" className="text-white hover:bg-slate-600">{t('tender_stcpay')}</SelectItem>
                        <SelectItem value="tabby" className="text-white hover:bg-slate-600">{t('tender_tabby')}</SelectItem>
                        <SelectItem value="tamara" className="text-white hover:bg-slate-600">{t('tender_tamara')}</SelectItem>
                        <SelectItem value="transfer" className="text-white hover:bg-slate-600">{t('bank_transfer')}</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input
                      type="number"
                      value={p.amount || ''}
                      onChange={(e) => updateSplitPayment(idx, 'amount', e.target.value)}
                      placeholder="0.00"
                      className="w-24 bg-slate-700 border-slate-600 text-white"
                    />
                  </div>
                ))}
                <div className={`flex justify-between text-xs ${splitBalanced ? 'text-green-400' : 'text-orange-400'}`}>
                  <span>{t('allocated')}: ${splitTotal.toFixed(2)}</span>
                  <span>{t('remaining')}: ${(total - splitTotal).toFixed(2)}</span>
                </div>
              </div>
            )}
          </div>

          <div className="flex gap-2">
            <Button
              onClick={handleHold}
              disabled={cart.length === 0 || holding || processing}
              variant="outline"
              className="flex-1 border-slate-600 text-slate-200 hover:bg-slate-700 py-6 text-base disabled:opacity-50"
            >
              <Pause className="w-4 h-4 me-2" />
              {holding ? t('loading') : t('hold_sale')}
            </Button>
            <Button
              onClick={handleCheckout}
              disabled={cart.length === 0 || processing}
              className="flex-[2] bg-green-600 hover:bg-green-700 text-white py-6 text-lg disabled:opacity-50"
            >
              {processing ? t('loading') : t('checkout')}
            </Button>
          </div>
        </div>
      </div>

      {/* POS-10: Held tickets panel — recall a parked sale */}
      {showHeld && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => setShowHeld(false)}
        >
          <div
            className="bg-slate-800 border border-slate-700 rounded-lg w-full max-w-lg max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <Pause className="w-5 h-5" />
                {t('held_tickets')}
              </h3>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowHeld(false)}
                className="text-slate-400 hover:text-white h-7 w-7 p-0"
              >
                <X className="w-5 h-5" />
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {heldError ? (
                <div role="alert" className="text-center py-8 text-red-400">
                  <p>{heldError}</p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={loadHeld}
                    className="mt-3 border-slate-600 text-slate-200 hover:bg-slate-700"
                  >
                    {t('retry')}
                  </Button>
                </div>
              ) : heldTickets.length === 0 ? (
                <p className="text-slate-500 text-center py-8">{t('no_held_tickets')}</p>
              ) : (
                heldTickets.map((ticket) => (
                  <div
                    key={ticket.id}
                    className="bg-slate-700 rounded-lg p-3 flex items-center justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <p className="text-white text-sm font-medium truncate">
                        {ticket.label || ticket.customer_name || `#${ticket.id}`}
                      </p>
                      <p className="text-slate-400 text-xs">
                        {ticket.item_count} {t('items')} · {ticket.total_amount?.toFixed(2)}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => handleRecall(ticket.id)}
                      className="bg-blue-600 hover:bg-blue-700 text-white whitespace-nowrap"
                    >
                      <Play className="w-4 h-4 me-1" />
                      {t('recall')}
                    </Button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}