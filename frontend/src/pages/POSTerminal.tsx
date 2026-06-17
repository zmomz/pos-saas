import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getProducts, createTransaction, refundTransaction, voidTransaction, getTransactions, validateDiscount, getEscposReceipt, syncOfflineTransactions, getMyPermissions, canUse, downloadInvoicePdf, getCustomers, getBranches, getClientBranding, holdSale, getHeldSales, recallSale, resolveBarcode, listTerminals, productImageSrc, type MyPermissions, type TenderInfo, type HeldTicket, type HeldItem, type Terminal } from '@/lib/api';
import { CUSTOMER_DISPLAY_KEY, buildCustomerDisplayPayload, paidCustomerDisplayPayload } from '@/lib/customerDisplay';
import { useLanguage } from '@/lib/i18n';
import { formatMoney, formatMoneyAr, toArabicDigits } from '@/lib/format';
import { enqueueTransaction, registerAutoFlush, isOnline } from '@/lib/offlineQueue';
import { printEscPos, isThermalPrintSupported } from '@/lib/thermalPrint';
import { useOnlineStatus } from '@/hooks/useOnlineStatus';
import ErrorState from '@/components/states/ErrorState';
import { ScanBarcode, RotateCcw, ShoppingCart, Tag, Check, X, Printer, FileDown, Camera, Pause, Play, WifiOff, Trash2, Lock, Banknote, CreditCard, Split as SplitIcon } from 'lucide-react';

export interface Product {
  id: number;
  name: string;
  name_ar?: string;
  price: number;
  category?: string;
  sku?: string;
  barcode?: string;
  // POS-11 (F-011): weighted (sold by fractional weight) / open-price (price
  // entered at sale) configuration; unit_label labels the weighted measure.
  is_weighted?: boolean;
  is_open_price?: boolean;
  unit_label?: string;
  // ISSUE-065 (P2 catalog): served URL of the product image (POS tile grid).
  image_url?: string | null;
}

export interface CartItem {
  // For a variant line (INV-04) `product` is a synthesized entry carrying the
  // variant's price/name; `product.id` stays the parent product id (sent as
  // product_id) and `variantId` identifies the variant SKU.
  product: Product;
  quantity: number;
  variantId?: number;
  // POS-11 (F-011): sale-time unit price for an open-price line. When undefined the
  // line is priced at the product's catalog price.
  unitPrice?: number;
  // Stable de-dup/render key — distinguishes variant siblings that share a
  // parent product id. `p<productId>` for a plain product, `v<variantId>` for a variant.
  key: string;
}

// POS-11 (F-011): the effective per-unit price for a cart line — the sale-time
// price on an open-price line, else the product's catalog price.
function lineUnitPrice(item: CartItem): number {
  return item.unitPrice ?? item.product.price;
}

function cartKeyFor(productId: number, variantId?: number): string {
  return variantId ? `v${variantId}` : `p${productId}`;
}

// POS-10 / INV-04 (ISSUE-031): serialize a cart line into the held-ticket payload.
// Carries `variant_id` and the effective (open) unit price so a recalled line restores
// exactly what was parked — otherwise a held variant SKU collapses to its parent
// product at catalog price and the recalled sale deducts the parent's stock.
export function holdLineFromCart(item: CartItem): {
  product_id: number;
  name: string;
  name_ar?: string;
  price: number;
  quantity: number;
  variant_id?: number;
} {
  return {
    product_id: item.product.id,
    name: item.product.name,
    name_ar: item.product.name_ar,
    price: lineUnitPrice(item),
    quantity: item.quantity,
    variant_id: item.variantId,
  };
}

// POS-10 / INV-04 (ISSUE-031): rebuild a cart line from a recalled held item. Restores
// the variant id (so the sale deducts the variant's stock, not the parent's), the held
// open price, and a variant-distinct cart key so sibling variants stay separate lines.
// Prefers the live product for full sku/category/barcode, but a variant line keeps the
// held price (the live lookup resolves the *parent*, whose price is the parent's).
export function cartLineFromHeld(it: HeldItem, products: Product[]): CartItem {
  const variantId = it.variant_id ?? undefined;
  const live = products.find((p) => p.id === it.product_id);
  const product: Product = live
    ? variantId
      ? { ...live, price: it.price }
      : live
    : { id: it.product_id, name: it.name, name_ar: it.name_ar, price: it.price };
  // POS-11: a recalled open-price line restores the cashier's entered price; a
  // fixed-price line tracks the current catalog price (unitPrice left undefined).
  const unitPrice = !variantId && live?.is_open_price ? it.price : undefined;
  return {
    product,
    quantity: it.quantity,
    variantId,
    unitPrice,
    key: cartKeyFor(it.product_id, variantId),
  };
}

// HW-03/PAY-05 (F-005): tenders that capture a real card approval and so can be
// routed to a paired in-store SoftPOS terminal. Cash/gift-card/transfer legs have
// no terminal leg, so the picker is hidden and no terminal_id is sent for them.
const TERMINAL_TENDERS = new Set(['card', 'mada', 'applepay', 'stcpay', 'tabby', 'tamara']);
function isTerminalTender(method: string): boolean {
  return TERMINAL_TENDERS.has(method);
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
  // POS-13 (F-012): gratuity collected on top of total_amount; shown as the amount
  // paid so the on-screen receipt matches what the customer was charged.
  tip_amount?: number | null;
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
  const { t, language } = useLanguage();
  // i18n fallback helper: return the translated string, or the supplied English
  // fallback when the key is missing (translate() returns the key on a miss).
  const tt = (key: string, fallback: string) => {
    const v = t(key);
    return v === key ? fallback : v;
  };

  // Barcode scanner state
  const [barcodeInput, setBarcodeInput] = useState('');
  const [barcodeMessage, setBarcodeMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  // ISSUE-076: price / stock check. When on, a scan/SKU entry only LOOKS UP the
  // product's price and on-hand stock (via the same /resolve-barcode endpoint)
  // instead of adding it to the cart.
  const [priceCheckMode, setPriceCheckMode] = useState(false);
  const [priceCheckResult, setPriceCheckResult] = useState<
    { found: true; name: string; price: number; quantity?: number | null } | { found: false } | null
  >(null);

  // POS-06: free-text product name search (complements barcode/SKU lookup).
  const [searchQuery, setSearchQuery] = useState('');
  // Category filter chips (handoff). 'all' shows everything.
  const [activeCat, setActiveCat] = useState('all');

  // Loyalty checkout (Phase 4): pick the customer to accrue/redeem points and
  // optionally spend points as a discount at checkout.
  const [customers, setCustomers] = useState<{ id: number; name: string }[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('');
  const [redeemPoints, setRedeemPoints] = useState<string>('');

  // Multi-branch (Phase 6): tag the sale to a branch so its stock is deducted.
  const [branches, setBranches] = useState<{ id: number; name: string }[]>([]);
  const [selectedBranchId, setSelectedBranchId] = useState<string>('');

  // HW-05 (F-047): the merchant brand name, mirrored to the customer-facing
  // second screen so it's white-labeled (never the platform brand).
  const [brandName, setBrandName] = useState<string>('');

  // POS-06: live camera barcode scanning via the BarcodeDetector API.
  const [cameraScanning, setCameraScanning] = useState(false);

  // POS-02: split-tender payment. When enabled the cashier allocates the total
  // across multiple methods; the per-method amounts are sent as payments[].
  const [splitMode, setSplitMode] = useState(false);
  const [splitPayments, setSplitPayments] = useState<
    { method: string; amount: number; gift_card_code?: string }[]
  >([
    { method: 'cash', amount: 0 },
    { method: 'card', amount: 0 },
  ]);
  // CRM-03/PRC-05 (F-038): bearer code for a single-tender gift-card sale.
  const [giftCardCode, setGiftCardCode] = useState('');

  // HW-03/PAY-05 (F-005, H16): paired in-store SoftPOS terminals. When the cashier
  // picks one for a card-like single tender, the charge routes to that terminal's
  // gateway (`payment_terminal_id`) instead of the online gateway. Empty selection
  // keeps the online/sandbox gateway.
  const [terminals, setTerminals] = useState<Terminal[]>([]);
  const [selectedTerminalId, setSelectedTerminalId] = useState<string>('');

  // POS-13 (F-012): tip / gratuity collected on top of the invoice total. Outside
  // the VAT base; added to the amount due so the tenders cover total + tip.
  const [tipAmount, setTipAmount] = useState(0);

  // ISSUE-074: cash-drawer change helper. On a cash payment the cashier records the
  // cash the customer handed over; the UI shows the change owed back and the
  // checkout sends `cash_tendered` so the backend records tendered + change.
  const [cashTendered, setCashTendered] = useState('');

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
  // ISSUE-075: reprint-in-progress flag for the selected past sale.
  const [reprinting, setReprinting] = useState(false);
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
    // HW-03 (F-005): the merchant's paired SoftPOS terminals — fuels the checkout
    // terminal picker (best-effort; no terminals just hides it).
    listTerminals()
      .then((ts) => setTerminals(ts.filter((tm) => tm.status !== 'inactive')))
      .catch(() => setTerminals([]));
    // HW-05: resolve the merchant brand name for the customer display header
    // (best-effort; falls back to the display's own default when absent).
    getClientBranding()
      .then((b) => setBrandName((b as { company_name?: string } | null)?.company_name || ''))
      .catch(() => setBrandName(''));
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
        items: cart.map(holdLineFromCart),
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
      // Rebuild cart items via the shared serialization helper so a recalled variant
      // SKU keeps its variant_id, open price, and distinct cart key (ISSUE-031).
      const restored: CartItem[] = recalled.items.map((it) => cartLineFromHeld(it, products));
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

  function addToCart(product: Product, variantId?: number) {
    const key = cartKeyFor(product.id, variantId);
    setCart((prev) => {
      const existing = prev.find((item) => item.key === key);
      if (existing) {
        return prev.map((item) =>
          item.key === key ? { ...item, quantity: item.quantity + 1 } : item
        );
      }
      // POS-11 (F-011): an open-price line seeds its sale-time price from the
      // catalog default so the cashier can adjust it inline before checkout.
      const unitPrice = product.is_open_price ? product.price : undefined;
      return [...prev, { product, quantity: 1, variantId, unitPrice, key }];
    });
  }

  function updateQuantity(key: string, delta: number) {
    setCart((prev) =>
      prev
        .map((item) => (item.key === key ? { ...item, quantity: item.quantity + delta } : item))
        .filter((item) => item.quantity > 0)
    );
  }

  // POS-11 (F-011): set an exact (possibly fractional, weighted) line quantity.
  function setLineQuantity(key: string, value: string) {
    const qty = Math.max(0, Number(value) || 0);
    setCart((prev) => prev.map((item) => (item.key === key ? { ...item, quantity: qty } : item)));
  }

  // POS-11 (F-011): set the sale-time unit price on an open-price line.
  function setLineUnitPrice(key: string, value: string) {
    const price = Math.max(0, Number(value) || 0);
    setCart((prev) => prev.map((item) => (item.key === key ? { ...item, unitPrice: price } : item)));
  }

  function removeFromCart(key: string) {
    setCart((prev) => prev.filter((item) => item.key !== key));
  }

  // Resolve a scanned/typed code to a product OR a variant SKU and add it to the
  // cart. Shared by the keyboard scanner and the live camera scanner (POS-06).
  // Local product barcodes resolve client-side; anything else (notably variant
  // barcodes, INV-04) is resolved against the server so a scanned variant adds
  // the variant line with its own price/stock.
  async function lookupAndAdd(code: string): Promise<boolean> {
    const barcode = code.trim();
    if (!barcode) return false;
    const matchedProduct = products.find((p) => p.barcode === barcode || p.sku === barcode);
    if (matchedProduct) {
      addToCart(matchedProduct);
      setBarcodeMessage({ text: `✓ ${matchedProduct.name} ${tt('added', 'added')}`, type: 'success' });
      return true;
    }
    try {
      const res = await resolveBarcode(barcode);
      if (res.kind === 'variant' && res.product_id) {
        addToCart(
          {
            id: res.product_id,
            name: res.name,
            name_ar: res.name_ar,
            price: res.price,
            barcode: res.barcode,
          },
          res.variant_id,
        );
        setBarcodeMessage({ text: `✓ ${res.name} ${tt('added', 'added')}`, type: 'success' });
        return true;
      }
      if (res.kind === 'product' && res.product_id) {
        const local = products.find((p) => p.id === res.product_id);
        addToCart(
          local || {
            id: res.product_id,
            name: res.name,
            name_ar: res.name_ar,
            price: res.price,
            barcode: res.barcode,
          },
        );
        setBarcodeMessage({ text: `✓ ${res.name} ${tt('added', 'added')}`, type: 'success' });
        return true;
      }
    } catch (err) {
      console.error('Barcode resolution failed:', err);
    }
    setBarcodeMessage({ text: `✕ ${tt('no_product_found_for', 'No product found for')} "${barcode}"`, type: 'error' });
    return false;
  }

  // ISSUE-076: resolve a scanned/typed code to a product OR variant SKU and show
  // its current price and on-hand stock WITHOUT touching the cart. The server is
  // authoritative for both the price and the on-hand quantity (it resolves
  // variants too), so the lookup always goes through /resolve-barcode.
  async function lookupPriceStock(code: string): Promise<void> {
    const barcode = code.trim();
    if (!barcode) return;
    try {
      const res = await resolveBarcode(barcode);
      if (res.kind !== 'none' && res.product_id) {
        setPriceCheckResult({ found: true, name: res.name, price: res.price, quantity: res.quantity });
        return;
      }
    } catch (err) {
      console.error('Price check failed:', err);
    }
    setPriceCheckResult({ found: false });
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
      setBarcodeMessage({ text: `✕ ${tt('camera_scan_unsupported', 'Camera scanning not supported on this device')}`, type: 'error' });
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
            if (priceCheckMode) {
              // ISSUE-076: a scan in price-check mode looks up price/stock only.
              await lookupPriceStock(codes[0].rawValue);
              stop(); setCameraScanning(false); return;
            }
            const found = await lookupAndAdd(codes[0].rawValue);
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
      setBarcodeMessage({ text: `✕ ${tt('camera_access_failed', 'Could not access the camera')}`, type: 'error' });
      setCameraScanning(false);
    }
  }

  // Barcode scan handler
  function handleBarcodeScan(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && barcodeInput.trim()) {
      if (priceCheckMode) {
        void lookupPriceStock(barcodeInput.trim());
      } else {
        void lookupAndAdd(barcodeInput.trim());
      }
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
      setDiscountError(detail || tt('invalid_discount_code', 'Invalid or expired discount code'));
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

  const subtotal = cart.reduce((sum, item) => sum + lineUnitPrice(item) * item.quantity, 0);

  // Calculate discount amount
  const discountAmount = appliedDiscount
    ? appliedDiscount.type === 'percentage'
      ? subtotal * (appliedDiscount.value / 100)
      : Math.min(appliedDiscount.value, subtotal)
    : 0;

  const discountedSubtotal = subtotal - discountAmount;
  const vatAmount = discountedSubtotal * 0.15;
  const total = discountedSubtotal + vatAmount;
  // POS-13 (F-012): the tip is OUTSIDE the VAT base above; the customer pays the
  // invoice total plus the tip, so the tenders (split or single) must cover this.
  const tip = Math.max(0, Number(tipAmount) || 0);
  const amountDue = total + tip;
  // ISSUE-074: change owed back on a single-tender cash sale. Only meaningful when
  // the cashier has entered the cash handed over and it covers the amount due.
  const cashGiven = Math.max(0, Number(cashTendered) || 0);
  const isCashSale = !splitMode && paymentMethod === 'cash';
  const changeDue = isCashSale && cashGiven > 0 ? cashGiven - amountDue : 0;

  // POS-06: products filtered by the name-search box (Arabic name included) and
  // the active category chip (handoff).
  const q = searchQuery.trim().toLowerCase();
  const filteredProducts = products.filter((p) => {
    if (activeCat !== 'all' && (p.category || t('uncategorized') || 'Other') !== activeCat) return false;
    if (!q) return true;
    return (
      p.name.toLowerCase().includes(q) ||
      (p.name_ar || '').toLowerCase().includes(q) ||
      (p.sku || '').toLowerCase().includes(q)
    );
  });

  // Distinct category chips, in first-seen order, with an "All" leader.
  const categories = ['all', ...Array.from(new Set(products.map((p) => p.category || t('uncategorized') || 'Other')))];

  // Deterministic tint per category (handoff product-thumbnail palette).
  const TINTS = [
    'bg-warning/12 text-warning',
    'bg-sky/12 text-sky',
    'bg-gold-50 text-gold-600',
    'bg-success/12 text-success',
    'bg-violet/12 text-violet',
    'bg-brand-50 text-brand-700',
    'bg-danger/12 text-danger',
  ];
  function tintFor(cat?: string): string {
    const key = cat || 'Other';
    let h = 0;
    for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
    return TINTS[h % TINTS.length];
  }

  // Locale-aware currency display for the sale screen (Arabic-Indic digits for
  // ar/ur). The always-Arabic fiscal receipt uses formatMoneyAr directly.
  const SAR = (n: number) => formatMoney(n || 0, language);

  // Per-product quantity already in the cart (drives the tile qty badge).
  const cartQtyByProduct = cart.reduce<Record<number, number>>((acc, it) => {
    acc[it.product.id] = (acc[it.product.id] || 0) + it.quantity;
    return acc;
  }, {});
  const cartCount = cart.reduce((s, it) => s + it.quantity, 0);

  // POS-02: split tenders must add up to the amount due (invoice total + tip,
  // POS-13) before checkout.
  const splitTotal = splitPayments.reduce((s, p) => s + (Number(p.amount) || 0), 0);
  const splitBalanced = Math.abs(splitTotal - amountDue) < 0.01;

  function updateSplitPayment(
    idx: number,
    field: 'method' | 'amount' | 'gift_card_code',
    value: string
  ) {
    setSplitPayments((prev) =>
      prev.map((p, i) =>
        i === idx ? { ...p, [field]: field === 'amount' ? Number(value) || 0 : value } : p
      )
    );
  }

  // Customer-facing display sync: mirror the live cart into the localStorage key
  // the CustomerDisplay page polls, so a second screen shows items + totals.
  // HW-05 (F-047): carry each line's Arabic name (bilingual, RTL) and the
  // merchant brand name (white-label) — the payload was previously English-only
  // and unbranded.
  useEffect(() => {
    try {
      localStorage.setItem(
        CUSTOMER_DISPLAY_KEY,
        JSON.stringify(
          buildCustomerDisplayPayload(
            cart.map((item) => ({
              name: item.product.name,
              name_ar: item.product.name_ar,
              quantity: item.quantity,
              price: lineUnitPrice(item),
            })),
            { subtotal, vat: vatAmount, total },
            brandName,
          ),
        )
      );
    } catch {
      /* localStorage unavailable — display sync is best-effort */
    }
  }, [cart, subtotal, vatAmount, total, brandName]);

  async function handleCheckout() {
    if (cart.length === 0) return;
    // POS-02: a split payment must be fully allocated before we send it.
    if (splitMode && !splitBalanced) {
      setBarcodeMessage({ text: `✕ ${tt('split_must_equal_total', 'Split payments must equal the total')}`, type: 'error' });
      return;
    }
    setProcessing(true);
    try {
      const items = cart.map((item) => ({
        product_id: item.product.id,
        // INV-04: a variant line decrements the variant's own stock server-side.
        variant_id: item.variantId,
        name: item.product.name,
        // Carry the Arabic name so the always-Arabic thermal receipt prints it
        // (PRN-01 / L10N-06).
        name_ar: item.product.name_ar,
        quantity: item.quantity,
        price: lineUnitPrice(item),
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
        // POS-13 (F-012): gratuity on top of the invoice total; the backend adds it
        // to the amount the tenders must cover and reports it in the Z-report.
        tip_amount: tip > 0 ? Number(tip.toFixed(2)) : undefined,
        // ISSUE-074: on a single-tender cash sale, send the cash handed over so the
        // backend records the change owed back. Drawer-facing — never changes the
        // captured tender (which covers the amount due).
        cash_tendered:
          isCashSale && cashGiven > 0 ? Number(cashGiven.toFixed(2)) : undefined,
        payments: splitMode
          ? splitPayments.filter((p) => (Number(p.amount) || 0) > 0)
          : undefined,
        // PRC-05 (F-038): single-tender gift-card sale — the bearer code the
        // backend validates + decrements atomically with the sale.
        payment_gift_card_code:
          !splitMode && paymentMethod === 'giftcard' && giftCardCode.trim()
            ? giftCardCode.trim()
            : undefined,
        // HW-03/PAY-05 (F-005, H16): a single card-like tender the cashier chose to
        // capture on a paired in-store terminal; sale_core routes it to that
        // terminal's gateway (a decline blocks the sale).
        payment_terminal_id:
          !splitMode && selectedTerminalId && isTerminalTender(paymentMethod)
            ? Number(selectedTerminalId)
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
        tip_amount: result.tip_amount,
        payment_method: result.payment_method || paymentMethod,
        zatca_qr_base64: result.zatca_qr_base64 || '',
        zatca_status: result.zatca_status,
        items: cart.map((item) => ({
          name: item.product.name,
          quantity: item.quantity,
          price: lineUnitPrice(item),
        })),
        discount_amount: discountAmount > 0 ? discountAmount : undefined,
        discount_code: appliedDiscount?.code,
        tenders: result.tenders,
      });
      // Flash the customer-facing display to a "thank you" state (still branded).
      try {
        localStorage.setItem(
          CUSTOMER_DISPLAY_KEY,
          JSON.stringify(paidCustomerDisplayPayload(brandName))
        );
      } catch { /* best-effort */ }
      setQueuedOffline(false);
      setCart([]);
      setAppliedDiscount(null);
      setDiscountCode('');
      setSplitMode(false);
      setSplitPayments([{ method: 'cash', amount: 0 }, { method: 'card', amount: 0 }]);
      setGiftCardCode('');
      setSelectedTerminalId('');
      setTipAmount(0);
      setCashTendered('');
      setRedeemPoints('');
      setSelectedCustomerId('');
    } catch (err) {
      // Offline POS (Phase E): if the device is offline (or the network call
      // failed), buffer the sale in IndexedDB and replay it on reconnect rather
      // than losing it. A queued sale gets no fiscal QR until it syncs.
      if (!isOnline()) {
        try {
          const subtotal = cart.reduce((s, i) => s + lineUnitPrice(i) * i.quantity, 0);
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
              price: lineUnitPrice(item),
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
              price: lineUnitPrice(item),
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

  // ISSUE-075: reprint a PAST sale's receipt. Re-renders from the stored sale
  // through the same renderer (template/Arabic/totals/QR all match the original)
  // and flags `reprint` so the backend stamps the duplicate copy + audits it.
  async function handleReprint(txn: Transaction) {
    if (!txn?.id) return;
    setReprinting(true);
    try {
      const payload = await getEscposReceipt(txn.id, { reprint: true });
      await printEscPos(payload);
    } catch (err) {
      console.error('Reprint failed:', err);
    } finally {
      setReprinting(false);
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
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-foreground animate-pulse">{t('loading')}</div>
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
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <div className="w-full max-w-md rounded-2xl border border-border bg-card">
          <div dir="rtl" lang="ar" className="p-6 space-y-4 text-right">
            <div className="text-center">
              <h2 className={`text-xl font-bold ${isRefund ? 'text-warning' : 'text-success'}`}>
                {isRefund ? '↩ تمت معالجة الاسترجاع' : '✓ تمت العملية بنجاح'}
              </h2>
              <p className="text-muted-foreground mt-1">رقم الفاتورة: {receipt.invoice_number}</p>
            </div>

            <div className="border-t border-border pt-4 space-y-2">
              {receipt.items.map((item, idx) => (
                <div key={idx} className="flex justify-between text-foreground text-sm">
                  <span>{item.name} ×{toArabicDigits(item.quantity)}</span>
                  <span>{formatMoneyAr(item.price * item.quantity)}</span>
                </div>
              ))}
            </div>

            <div className="border-t border-border pt-3 space-y-1">
              <div className="flex justify-between text-muted-foreground text-sm">
                <span>المجموع الفرعي</span>
                <span>{formatMoneyAr(receipt.subtotal || 0)}</span>
              </div>
              {receipt.discount_amount && receipt.discount_amount > 0 && (
                <div className="flex justify-between text-success text-sm">
                  <span>الخصم ({receipt.discount_code})</span>
                  <span>-{formatMoneyAr(receipt.discount_amount)}</span>
                </div>
              )}
              <div className="flex justify-between text-muted-foreground text-sm">
                <span>ضريبة القيمة المضافة</span>
                <span>{formatMoneyAr(receipt.vat_amount || 0)}</span>
              </div>
              <div className="flex justify-between text-foreground font-bold">
                <span>الإجمالي</span>
                <span>{formatMoneyAr(receipt.total_amount || 0)}</span>
              </div>
              {/* POS-13 (F-012): tip + the amount actually paid (total + tip). */}
              {receipt.tip_amount && receipt.tip_amount > 0 && (
                <>
                  <div className="flex justify-between text-muted-foreground text-sm">
                    <span>البقشيش</span>
                    <span>{formatMoneyAr(receipt.tip_amount)}</span>
                  </div>
                  <div className="flex justify-between text-success font-bold">
                    <span>المبلغ المدفوع</span>
                    <span>{formatMoneyAr((receipt.total_amount || 0) + receipt.tip_amount)}</span>
                  </div>
                </>
              )}
            </div>

            <div className="flex justify-between text-foreground text-sm">
              <span>طريقة الدفع</span>
              <span className={isRefund ? 'pill-warning' : 'pill-success'}>
                {paymentAr[receipt.payment_method] || receipt.payment_method}
              </span>
            </div>

            {/* PAY-01: captured tender approval (network + auth code) for card-like
                tenders, so the receipt proves the card was actually charged. */}
            {receipt.tenders && receipt.tenders.some((tn) => tn.approval_code) && (
              <div className="border-t border-border pt-3 space-y-1">
                {receipt.tenders
                  .filter((tn) => tn.approval_code)
                  .map((tn, idx) => (
                    <div key={idx} className="flex justify-between text-muted-foreground text-xs">
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
              <div className="border-t border-border pt-4">
                <p className="text-sm text-muted-foreground mb-2 text-center">رمز الاستجابة السريعة (ZATCA)</p>
                <div className="flex justify-center">
                  <div className="bg-white p-3 rounded-lg">
                    <img
                      src={`data:image/png;base64,${receipt.zatca_qr_base64}`}
                      alt="ZATCA QR"
                      className="w-32 h-32"
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        target.style.display = 'none';
                        target.parentElement!.innerHTML = `<div class="w-32 h-32 flex items-center justify-center bg-muted text-xs text-muted-foreground break-all p-1 font-mono">${receipt.zatca_qr_base64.substring(0, 60)}...</div>`;
                      }}
                    />
                  </div>
                </div>
                {receipt.zatca_status && (
                  <p className="text-xs text-muted-foreground mt-2 text-center">
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
              <div className="rounded-md bg-warning/15 border border-warning/40 text-warning text-sm p-3 text-center">
                تم حفظ العملية دون اتصال وسيتم مزامنتها عند عودة الإنترنت
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <Button onClick={handleNewSale} className="flex-1">
                {t('new_sale')}
              </Button>
              {receipt.id && (
                <Button
                  variant="outline"
                  onClick={() => downloadInvoicePdf(receipt.id!, receipt.invoice_number)}
                  className="border-border text-foreground hover:bg-muted"
                  title={t('download_pdf') || 'Download PDF'}
                >
                  <FileDown className="w-4 h-4" />
                </Button>
              )}
              {receipt.id && isThermalPrintSupported() && (
                <Button
                  variant="outline"
                  onClick={handleThermalPrint}
                  className="border-border text-foreground hover:bg-muted"
                  title={t('thermal_print')}
                >
                  <Printer className="w-4 h-4" />
                </Button>
              )}
              <Button
                variant="outline"
                onClick={() => navigate('/client')}
                className="flex-1 border-border text-foreground hover:bg-muted"
              >
                {t('back')}
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Refund Mode View
  if (mode === 'refund') {
    return (
      <div className="min-h-screen bg-background flex flex-col">
        {/* Header */}
        <div className="bg-card border-b border-border p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <RotateCcw className="w-5 h-5 text-warning" />
            <h2 className="text-lg font-bold text-foreground">{t('refund_mode')}</h2>
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={() => { setMode('sale'); setSelectedTransaction(null); setRefundQty({}); }}
            >
              <ShoppingCart className="w-4 h-4 me-2" />
              {t('new_sale')}
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate('/client')}
              className="border-border text-foreground hover:bg-muted"
            >
              {t('back')}
            </Button>
          </div>
        </div>

        <div className="flex-1 flex flex-col lg:flex-row">
          {/* Transaction List */}
          <div className="flex-1 p-4 overflow-y-auto">
            <h3 className="text-foreground font-semibold mb-3">{t('recent_transactions')}</h3>
            {loadingTransactions ? (
              <div className="text-muted-foreground text-center py-8">{t('loading')}</div>
            ) : recentTransactions.length === 0 ? (
              <div className="text-muted-foreground text-center py-8">{t('no_transactions')}</div>
            ) : (
              <div className="space-y-2">
                {recentTransactions.map((txn, idx) => (
                  <div
                    key={txn.id || idx}
                    className={`rounded-2xl border bg-card p-4 cursor-pointer transition-colors ${
                      selectedTransaction?.invoice_number === txn.invoice_number
                        ? 'border-brand ring-1 ring-brand'
                        : 'border-border hover:border-input'
                    }`}
                    onClick={() => selectTransactionForRefund(txn)}
                  >
                    <div className="flex justify-between items-center">
                      <div>
                        <p className="text-foreground font-medium text-sm">{txn.invoice_number}</p>
                        <p className="text-muted-foreground text-xs mt-1">
                          {txn.created_at ? new Date(txn.created_at).toLocaleString() : 'N/A'}
                        </p>
                      </div>
                      <div className="text-end">
                        <p className="text-brand-700 font-bold">{SAR(txn.total_amount || 0)}</p>
                        <span className="pill-muted text-xs mt-1">
                          {txn.payment_method}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Selected Transaction Detail */}
          <div className="w-full lg:w-96 bg-card border-t lg:border-t-0 lg:border-s border-border p-4">
            {selectedTransaction ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-foreground font-semibold">{t('refund_details')}</h3>
                  {selectedTransaction.status === 'partial_refunded' && (
                    <span className="pill-warning text-xs">
                      {t('already_partially_refunded')}
                    </span>
                  )}
                </div>
                <div className="bg-muted rounded-lg p-4 space-y-2">
                  <div className="flex justify-between text-foreground text-sm">
                    <span>{t('invoice')}</span>
                    <span>{selectedTransaction.invoice_number}</span>
                  </div>
                  <div className="flex justify-between text-foreground text-sm">
                    <span>{t('payment_method')}</span>
                    <span>{selectedTransaction.payment_method}</span>
                  </div>

                  {refundHasLineItems ? (
                    <div className="border-t border-border pt-2 mt-2 space-y-2">
                      {/* POS-07: choose how many of each line to return. */}
                      <p className="text-muted-foreground text-xs">{t('select_return_qty')}</p>
                      {selectedTransaction.items!.map((item, idx) => {
                        const qty = refundQty[idx] ?? 0;
                        return (
                          <div key={idx} className="flex items-center justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <p className="text-foreground text-xs truncate">{item.name}</p>
                              <p className="text-muted-foreground text-[11px]">
                                {SAR(Math.abs(item.price))} · {item.quantity} {t('sold')}
                              </p>
                            </div>
                            <div className="flex items-center gap-1">
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="h-7 w-7 p-0 border-input text-foreground"
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
                                className="h-7 w-12 text-center bg-card border-input text-foreground text-xs"
                              />
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="h-7 w-7 p-0 border-input text-foreground"
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

                  <div className="border-t border-border pt-2 mt-2">
                    <div className="flex justify-between text-foreground font-bold mt-1">
                      <span>
                        {t('refund_amount')}
                        {refundHasLineItems && refundIsPartial && (
                          <span className="ms-2 text-warning text-xs font-normal">
                            ({t('partial_refund')})
                          </span>
                        )}
                      </span>
                      <span className="text-warning">
                        {SAR(
                          refundHasLineItems
                            ? refundSelectedAmount
                            : selectedTransaction.total_amount || 0
                        )}
                      </span>
                    </div>
                  </div>
                </div>

                <Button
                  onClick={handleRefund}
                  disabled={refundProcessing || !canRefund || !canSubmitRefund}
                  className="w-full bg-warning text-white py-6 text-lg shadow-brand hover:opacity-90 disabled:opacity-50"
                >
                  {refundProcessing ? t('loading') : `↩ ${t('process_refund')}`}
                </Button>
                {!canRefund && (
                  <p className="text-center text-sm text-warning mt-2">
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
                    <div className="border-t border-border pt-3 mt-3">
                      <Button
                        onClick={handleVoid}
                        disabled={voidProcessing}
                        variant="outline"
                        className="w-full border-destructive text-destructive hover:bg-destructive/10 disabled:opacity-50"
                      >
                        {voidProcessing ? t('loading') : `✕ ${t('void_sale')}`}
                      </Button>
                      <p className="text-center text-xs text-muted-foreground mt-2">
                        {t('void_sale_hint')}
                      </p>
                      {voidError && (
                        <p role="alert" className="text-center text-sm text-destructive mt-2">
                          {voidError}
                        </p>
                      )}
                    </div>
                  )}

                {/* ISSUE-075: reprint this past sale's receipt (a stamped,
                    audited duplicate). Available for any past sale regardless of
                    refund/void eligibility. */}
                <div className="border-t border-border pt-3 mt-3">
                  <Button
                    onClick={() => handleReprint(selectedTransaction)}
                    disabled={reprinting}
                    variant="outline"
                    className="w-full border-border text-foreground hover:bg-muted disabled:opacity-50"
                  >
                    <Printer className="w-4 h-4 me-2" />
                    {reprinting ? t('loading') : t('reprint_receipt')}
                  </Button>
                  <p className="text-center text-xs text-muted-foreground mt-2">
                    {t('reprint_receipt_hint')}
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">
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
    <div className="min-h-screen bg-background flex flex-col lg:flex-row">
      {/* Product Grid */}
      <div className="flex-1 p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold text-foreground">{t('products')}</h2>
            {/* F-015 (UX-02): persistent offline indicator inside the POS chrome. */}
            {!online && (
              <span
                role="status"
                className="inline-flex items-center gap-1 rounded-full border border-warning/40 bg-warning/15 px-2 py-0.5 text-xs text-warning"
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
              className="relative border-border text-foreground hover:bg-muted"
            >
              <Pause className="w-4 h-4 me-2" />
              {t('held_tickets')}
              {heldTickets.length > 0 && (
                <span className="ms-2 inline-flex items-center justify-center min-w-5 h-5 px-1 rounded-full bg-brand-600 text-white text-xs">
                  {heldTickets.length}
                </span>
              )}
            </Button>
            {canRefund && (
              <Button
                onClick={() => setMode('refund')}
                variant="outline"
                className="border-warning/50 text-warning hover:bg-warning/10"
              >
                <RotateCcw className="w-4 h-4 me-2" />
                {t('refund')}
              </Button>
            )}
            <Button
              variant="outline"
              onClick={() => navigate('/client')}
              className="border-border text-foreground hover:bg-muted"
            >
              {t('back')}
            </Button>
          </div>
        </div>

        {/* Barcode Scanner Input */}
        <div className="mb-4 relative">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <ScanBarcode className="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                value={barcodeInput}
                onChange={(e) => setBarcodeInput(e.target.value)}
                onKeyDown={handleBarcodeScan}
                placeholder={t('scan_barcode')}
                className="ps-10 bg-card border-border text-foreground placeholder:text-muted-foreground focus:border-brand-500"
              />
            </div>
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('search_products')}
              className="flex-1 bg-card border-border text-foreground placeholder:text-muted-foreground focus:border-brand-500"
            />
            <Button
              type="button"
              variant={priceCheckMode ? 'default' : 'outline'}
              onClick={() => { setPriceCheckMode((v) => !v); setPriceCheckResult(null); }}
              className="shrink-0 border-border"
              title={t('price_check')}
              aria-pressed={priceCheckMode}
            >
              <Tag className="w-4 h-4" />
            </Button>
            <Button
              type="button"
              variant={cameraScanning ? 'default' : 'outline'}
              onClick={toggleCameraScan}
              className="shrink-0 border-border"
              title={t('scan_camera')}
            >
              <Camera className="w-4 h-4" />
            </Button>
          </div>
          {priceCheckMode && priceCheckResult && (
            <div className="mt-2 rounded border border-brand bg-brand-50 px-3 py-2 text-sm">
              {priceCheckResult.found ? (
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium text-foreground">{priceCheckResult.name}</span>
                  <span className="text-brand-700 font-bold">{SAR(priceCheckResult.price)}</span>
                  <span className="text-muted-foreground">
                    {t('on_hand')}: {priceCheckResult.quantity ?? 0}
                  </span>
                </div>
              ) : (
                <span className="text-danger">{t('price_check_none')}</span>
              )}
            </div>
          )}
          {barcodeMessage && (
            <div className={`absolute top-full mt-1 start-0 text-xs px-3 py-1.5 rounded ${
              barcodeMessage.type === 'success'
                ? 'bg-success/10 text-success border border-success/40'
                : 'bg-danger/10 text-danger border border-danger/40'
            }`}>
              {barcodeMessage.text}
            </div>
          )}
        </div>

        {/* Loyalty + branch checkout controls (Phase 4/6) */}
        <div className="mb-4 grid grid-cols-1 sm:grid-cols-3 gap-2">
          {customers.length > 0 && (
            <Select value={selectedCustomerId} onValueChange={setSelectedCustomerId}>
              <SelectTrigger className="bg-card border-border text-foreground">
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
              className="bg-card border-border text-foreground placeholder:text-muted-foreground"
            />
          )}
          {branches.length > 0 && (
            <Select value={selectedBranchId} onValueChange={setSelectedBranchId}>
              <SelectTrigger className="bg-card border-border text-foreground">
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

        {/* Category chips (handoff). */}
        {categories.length > 1 && (
          <div className="mb-4 flex flex-wrap gap-2">
            {categories.map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setActiveCat(cat)}
                className={
                  activeCat === cat
                    ? 'inline-flex items-center rounded-full border border-brand bg-brand px-[15px] py-2 text-[13.5px] font-semibold text-white'
                    : 'chip-link'
                }
              >
                {cat === 'all' ? (t('all') || 'All') : cat}
              </button>
            ))}
          </div>
        )}

        {productsError ? (
          // F-015 (UX-02): error state distinct from the empty state, with retry.
          <ErrorState message={t('products_load_error')} onRetry={loadProducts} />
        ) : filteredProducts.length === 0 ? (
          <div className="text-center text-muted-foreground py-12">{t('no_products')}</div>
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
            {filteredProducts.map((product) => {
              const inCart = cartQtyByProduct[product.id] || 0;
              return (
                <button
                  key={product.id}
                  type="button"
                  onClick={() => addToCart(product)}
                  className={`group relative flex flex-col gap-2.5 rounded-2xl border bg-card p-3 text-start shadow-card transition-all hover:-translate-y-0.5 hover:border-brand hover:shadow-brand ${inCart ? 'border-brand ring-1 ring-brand/40' : 'border-border'}`}
                >
                  {inCart > 0 && (
                    <span className="absolute end-2 top-2 z-10 flex h-6 min-w-6 items-center justify-center rounded-full bg-brand px-1.5 text-xs font-bold text-white shadow">
                      {inCart}
                    </span>
                  )}
                  {/* ISSUE-065: show the product image when set; otherwise fall
                      back to the category-tinted name initial. */}
                  {productImageSrc(product.image_url) ? (
                    <img
                      src={productImageSrc(product.image_url)}
                      alt={product.name}
                      className="h-20 w-full rounded-xl object-cover"
                    />
                  ) : (
                    <div className={`flex h-20 items-center justify-center rounded-xl text-2xl font-extrabold ${tintFor(product.category)}`}>
                      {product.name?.charAt(0)?.toUpperCase() || '?'}
                    </div>
                  )}
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-foreground">{product.name}</div>
                    <div className="mt-0.5 font-bold tabular-nums text-brand-700">
                      {formatMoney(product.price ?? 0, language)}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Cart Sidebar */}
      <div className="flex w-full flex-col border-t border-border bg-card p-4 lg:w-[400px] lg:border-s lg:border-t-0">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-bold text-foreground">
            <ShoppingCart className="h-[18px] w-[18px]" /> {t('current_sale') || 'Current Sale'}
            <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-brand-50 px-1.5 text-xs font-bold text-brand-700">{cartCount}</span>
          </h2>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleHold}
              disabled={cart.length === 0 || holding || processing}
              className="inline-flex items-center gap-1.5 rounded-lg border border-input px-2.5 py-1.5 text-xs font-semibold text-muted-foreground transition-colors hover:border-brand hover:text-brand-700 disabled:opacity-50"
            >
              <Pause className="h-3.5 w-3.5" /> {holding ? t('loading') : t('hold_sale')}
            </button>
            <button
              type="button"
              onClick={() => { setCart([]); setAppliedDiscount(null); setDiscountCode(''); setTipAmount(0); }}
              disabled={cart.length === 0}
              title={t('clear') || 'Clear'}
              className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-input text-danger transition-colors hover:bg-danger/10 disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto space-y-2">
          {cart.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center text-muted-foreground">
              <ShoppingCart className="h-10 w-10 opacity-30" />
              <p className="text-sm">{t('empty_cart')}</p>
            </div>
          ) : (
            cart.map((item) => (
              <div key={item.key} className="rounded-xl border border-border bg-card p-3 shadow-card">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <p className="text-foreground text-sm font-medium">
                      {item.product.name}
                      {item.variantId && (
                        <span className="ms-1 text-[10px] uppercase tracking-wide text-brand-700">
                          {t('variant')}
                        </span>
                      )}
                      {item.product.is_weighted && (
                        <span className="ms-1 text-[10px] uppercase tracking-wide text-warning">
                          {t('weighted')}
                        </span>
                      )}
                      {item.product.is_open_price && (
                        <span className="ms-1 text-[10px] uppercase tracking-wide text-success">
                          {t('open_price')}
                        </span>
                      )}
                    </p>
                    {/* POS-11: open-price lines show an editable sale-time unit price */}
                    {item.product.is_open_price ? (
                      <div className="flex items-center gap-1 mt-1">
                        <span className="text-muted-foreground text-xs">{t('unit_price')}</span>
                        <Input
                          type="number"
                          min="0"
                          step="0.01"
                          value={lineUnitPrice(item)}
                          onChange={(e) => setLineUnitPrice(item.key, e.target.value)}
                          dir="ltr"
                          className="h-6 w-20 bg-card border-border text-foreground text-xs"
                        />
                      </div>
                    ) : (
                      <p className="text-muted-foreground text-xs">
                        {SAR(lineUnitPrice(item))}
                        {item.product.is_weighted && item.product.unit_label
                          ? ` / ${item.product.unit_label}`
                          : ` ${t('each')}`}
                      </p>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => removeFromCart(item.key)}
                    className="text-destructive hover:text-destructive hover:bg-muted h-6 w-6 p-0"
                  >
                    ✕
                  </Button>
                </div>
                <div className="flex items-center gap-2 mt-2">
                  {item.product.is_weighted ? (
                    // POS-11: weighted lines capture a fractional quantity (weight).
                    <div className="flex items-center gap-1">
                      <Input
                        type="number"
                        min="0"
                        step="0.001"
                        value={item.quantity}
                        onChange={(e) => setLineQuantity(item.key, e.target.value)}
                        dir="ltr"
                        className="h-7 w-24 bg-card border-border text-foreground text-xs"
                      />
                      {item.product.unit_label && (
                        <span className="text-muted-foreground text-xs">{item.product.unit_label}</span>
                      )}
                    </div>
                  ) : (
                    <>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => updateQuantity(item.key, -1)}
                        className="h-7 w-7 p-0 border-border text-foreground hover:bg-muted"
                      >
                        -
                      </Button>
                      <span className="text-foreground text-sm w-8 text-center">{item.quantity}</span>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => updateQuantity(item.key, 1)}
                        className="h-7 w-7 p-0 border-border text-foreground hover:bg-muted"
                      >
                        +
                      </Button>
                    </>
                  )}
                  <span className="ms-auto text-sm font-bold tabular-nums text-brand-700">
                    {SAR(lineUnitPrice(item) * item.quantity)}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Totals & Checkout */}
        <div className="border-t border-border pt-4 mt-4 space-y-3">
          {/* Discount Code Input */}
          <div>
            <label className="text-muted-foreground text-sm block mb-1">
              <Tag className="w-3 h-3 inline me-1" />
              {t('discount_code')}
            </label>
            {appliedDiscount ? (
              <div className="flex items-center gap-2 rounded-lg border border-success/40 bg-success/10 px-3 py-2">
                <Check className="w-4 h-4 text-success" />
                <span className="text-success text-sm flex-1">
                  {appliedDiscount.code} · {appliedDiscount.type === 'percentage' ? `${appliedDiscount.value}%` : SAR(appliedDiscount.value)}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={removeDiscount}
                  className="h-6 w-6 p-0 text-destructive hover:text-destructive hover:bg-transparent"
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
                  placeholder={t('enter_code')}
                  className="bg-muted border-border text-foreground placeholder:text-muted-foreground text-sm"
                />
                <Button
                  size="sm"
                  onClick={handleApplyDiscount}
                  disabled={!discountCode.trim() || applyingDiscount}
                  className="px-3 whitespace-nowrap"
                >
                  {applyingDiscount ? '...' : t('apply')}
                </Button>
              </div>
            )}
            {discountError && (
              <p className="text-destructive text-xs mt-1">{discountError}</p>
            )}
          </div>

          <div className="flex justify-between text-sm text-muted-foreground">
            <span>{t('subtotal')}</span>
            <span className="tabular-nums">{SAR(subtotal)}</span>
          </div>
          {discountAmount > 0 && (
            <div className="flex justify-between text-sm text-success">
              <span>{t('discount') || 'Discount'}</span>
              <span className="tabular-nums">−{SAR(discountAmount)}</span>
            </div>
          )}
          <div className="flex justify-between text-sm text-muted-foreground">
            <span>{t('vat')}</span>
            <span className="tabular-nums">{SAR(vatAmount)}</span>
          </div>
          <div className="flex justify-between border-t border-border pt-2 text-lg font-bold text-foreground">
            <span>{t('total')}</span>
            <span className="tabular-nums">{SAR(total)}</span>
          </div>

          {/* POS-13 (F-012): tip / gratuity on top of the invoice total. Outside the
              VAT base; quick-percent buttons compute off the total, or enter a custom
              amount. The amount due (total + tip) is what the tenders must cover. */}
          <div>
            <label className="text-muted-foreground text-sm block mb-1">{t('tip')}</label>
            <div className="flex gap-2">
              <Input
                type="number"
                min={0}
                step="0.01"
                inputMode="decimal"
                value={tipAmount ? String(tipAmount) : ''}
                onChange={(e) => setTipAmount(Math.max(0, Number(e.target.value) || 0))}
                placeholder="0.00"
                dir="ltr"
                className="bg-muted border-border text-foreground placeholder:text-muted-foreground text-sm"
              />
              {[10, 15, 20].map((pct) => (
                <Button
                  key={pct}
                  size="sm"
                  type="button"
                  variant="ghost"
                  onClick={() => setTipAmount(Number(((total * pct) / 100).toFixed(2)))}
                  className="border border-border text-foreground hover:bg-muted px-2 whitespace-nowrap"
                >
                  {pct}%
                </Button>
              ))}
              {tip > 0 && (
                <Button
                  size="sm"
                  type="button"
                  variant="ghost"
                  onClick={() => setTipAmount(0)}
                  className="h-9 w-9 p-0 text-destructive hover:text-destructive hover:bg-transparent"
                  aria-label={t('clear_tip')}
                >
                  <X className="w-4 h-4" />
                </Button>
              )}
            </div>
          </div>

          {tip > 0 && (
            <div className="flex justify-between border-t border-border pt-2 text-lg font-bold text-success">
              <span>{t('amount_due')}</span>
              <span className="tabular-nums">{SAR(amountDue)}</span>
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-muted-foreground text-sm">{t('payment_method')}</label>
              <button
                type="button"
                onClick={() => setSplitMode((v) => !v)}
                className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-semibold transition-colors ${
                  splitMode
                    ? 'border-brand bg-brand text-white'
                    : 'border-input text-muted-foreground hover:border-brand hover:text-brand-700'
                }`}
              >
                <SplitIcon className="h-3.5 w-3.5" /> {t('split_payment')}
              </button>
            </div>
            {!splitMode ? (
              <>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { v: 'cash', label: t('cash'), icon: Banknote },
                    { v: 'mada', label: t('tender_mada') },
                    { v: 'card', label: t('card'), icon: CreditCard },
                    { v: 'applepay', label: t('tender_applepay') },
                    { v: 'stcpay', label: t('tender_stcpay') },
                    { v: 'tabby', label: t('tender_tabby') },
                    { v: 'tamara', label: t('tender_tamara') },
                    { v: 'giftcard', label: t('tender_gift_card') },
                    { v: 'bank_transfer', label: t('bank_transfer') },
                  ].map((m) => {
                    const Icon = m.icon;
                    const active = paymentMethod === m.v;
                    return (
                      <button
                        key={m.v}
                        type="button"
                        onClick={() => setPaymentMethod(m.v)}
                        className={`inline-flex items-center justify-center gap-1.5 rounded-lg border px-2 py-2 text-[13px] font-semibold transition-colors ${
                          active
                            ? 'border-brand bg-brand-50 text-brand-700'
                            : 'border-input text-muted-foreground hover:border-brand hover:text-brand-700'
                        }`}
                      >
                        {Icon ? <Icon className="h-4 w-4" /> : null} {m.label}
                      </button>
                    );
                  })}
                </div>
                {paymentMethod === 'giftcard' && (
                  <Input
                    value={giftCardCode}
                    onChange={(e) => setGiftCardCode(e.target.value)}
                    placeholder={t('gift_card_code_placeholder')}
                    dir="ltr"
                    className="mt-2 bg-muted border-border text-foreground"
                  />
                )}
                {/* ISSUE-074: cash-drawer change helper. The cashier enters the cash
                    the customer handed over; the change owed back is shown and sent
                    on the sale. Only on a single-tender cash payment. */}
                {paymentMethod === 'cash' && (
                  <div className="mt-2">
                    <label
                      htmlFor="cash-tendered"
                      className="text-muted-foreground text-sm block mb-1"
                    >
                      {t('cash_tendered')}
                    </label>
                    <Input
                      id="cash-tendered"
                      type="number"
                      inputMode="decimal"
                      min={0}
                      step="0.01"
                      value={cashTendered}
                      onChange={(e) => setCashTendered(e.target.value)}
                      placeholder="0.00"
                      className="bg-muted border-border text-foreground"
                    />
                    {cashGiven > 0 && (
                      <div className="flex justify-between mt-2 text-sm font-semibold">
                        <span className="text-muted-foreground">{t('change_due')}</span>
                        <span
                          className={`tabular-nums ${changeDue < 0 ? 'text-danger' : 'text-success'}`}
                        >
                          {SAR(Math.max(0, changeDue))}
                        </span>
                      </div>
                    )}
                  </div>
                )}
                {/* HW-03 (F-005, H16): pick a paired in-store terminal for a
                    card-like tender; the charge routes to its gateway. */}
                {terminals.length > 0 && isTerminalTender(paymentMethod) && (
                  <div className="mt-2">
                    <label className="text-muted-foreground text-xs">{t('charge_on')}</label>
                    <div className="mt-1 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedTerminalId('')}
                        className={`rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                          selectedTerminalId === ''
                            ? 'border-brand bg-brand-50 text-brand-700'
                            : 'border-input text-muted-foreground hover:border-brand hover:text-brand-700'
                        }`}
                      >
                        {t('online_gateway')}
                      </button>
                      {terminals.map((tm) => {
                        const active = selectedTerminalId === String(tm.id);
                        return (
                          <button
                            key={tm.id}
                            type="button"
                            onClick={() => setSelectedTerminalId(String(tm.id))}
                            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                              active
                                ? 'border-brand bg-brand-50 text-brand-700'
                                : 'border-input text-muted-foreground hover:border-brand hover:text-brand-700'
                            }`}
                          >
                            <CreditCard className="h-3.5 w-3.5" />
                            {tm.label || tm.serial || `#${tm.id}`}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="space-y-2">
                {splitPayments.map((p, idx) => (
                  <div key={idx} className="space-y-2">
                    <div className="flex gap-2">
                      <Select value={p.method} onValueChange={(v) => updateSplitPayment(idx, 'method', v)}>
                        <SelectTrigger className="bg-muted border-border text-foreground flex-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="bg-muted border-border">
                          <SelectItem value="cash" className="text-foreground hover:bg-muted">{t('cash')}</SelectItem>
                          <SelectItem value="mada" className="text-foreground hover:bg-muted">{t('tender_mada')}</SelectItem>
                          <SelectItem value="card" className="text-foreground hover:bg-muted">{t('card')}</SelectItem>
                          <SelectItem value="applepay" className="text-foreground hover:bg-muted">{t('tender_applepay')}</SelectItem>
                          <SelectItem value="stcpay" className="text-foreground hover:bg-muted">{t('tender_stcpay')}</SelectItem>
                          <SelectItem value="tabby" className="text-foreground hover:bg-muted">{t('tender_tabby')}</SelectItem>
                          <SelectItem value="tamara" className="text-foreground hover:bg-muted">{t('tender_tamara')}</SelectItem>
                          <SelectItem value="giftcard" className="text-foreground hover:bg-muted">{t('tender_gift_card')}</SelectItem>
                          <SelectItem value="transfer" className="text-foreground hover:bg-muted">{t('bank_transfer')}</SelectItem>
                        </SelectContent>
                      </Select>
                      <Input
                        type="number"
                        value={p.amount || ''}
                        onChange={(e) => updateSplitPayment(idx, 'amount', e.target.value)}
                        placeholder="0.00"
                        className="w-24 bg-muted border-border text-foreground"
                      />
                    </div>
                    {p.method === 'giftcard' && (
                      <Input
                        value={p.gift_card_code || ''}
                        onChange={(e) => updateSplitPayment(idx, 'gift_card_code', e.target.value)}
                        placeholder={t('gift_card_code_placeholder')}
                        dir="ltr"
                        className="bg-muted border-border text-foreground"
                      />
                    )}
                  </div>
                ))}
                <div className={`flex justify-between text-xs ${splitBalanced ? 'text-success' : 'text-warning'}`}>
                  <span>{t('allocated')}: {SAR(splitTotal)}</span>
                  <span>{t('remaining')}: {SAR(amountDue - splitTotal)}</span>
                </div>
              </div>
            )}
          </div>

          <button
            onClick={handleCheckout}
            disabled={cart.length === 0 || processing || (splitMode && !splitBalanced)}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand py-4 text-base font-bold text-white shadow-brand transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {cart.length === 0 ? (
              <>
                <Lock className="h-5 w-5" /> {t('add_items_to_pay') || 'Add items to pay'}
              </>
            ) : (
              <>
                <ShoppingCart className="h-5 w-5" />
                {processing ? t('loading') : `${t('pay') || 'Pay'} ${SAR(amountDue)}`}
              </>
            )}
          </button>
        </div>
      </div>

      {/* POS-10: Held tickets panel — recall a parked sale */}
      {showHeld && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => setShowHeld(false)}
        >
          <div
            className="bg-card border border-border rounded-lg w-full max-w-lg max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-border">
              <h3 className="text-lg font-bold text-foreground flex items-center gap-2">
                <Pause className="w-5 h-5" />
                {t('held_tickets')}
              </h3>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setShowHeld(false)}
                className="text-muted-foreground hover:text-foreground h-7 w-7 p-0"
              >
                <X className="w-5 h-5" />
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {heldError ? (
                <div role="alert" className="text-center py-8 text-destructive">
                  <p>{heldError}</p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={loadHeld}
                    className="mt-3 border-border text-foreground hover:bg-muted"
                  >
                    {t('retry')}
                  </Button>
                </div>
              ) : heldTickets.length === 0 ? (
                <p className="text-muted-foreground text-center py-8">{t('no_held_tickets')}</p>
              ) : (
                heldTickets.map((ticket) => (
                  <div
                    key={ticket.id}
                    className="bg-muted rounded-lg p-3 flex items-center justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <p className="text-foreground text-sm font-medium truncate">
                        {ticket.label || ticket.customer_name || `#${ticket.id}`}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        {ticket.item_count} {t('items')} · {SAR(ticket.total_amount ?? 0)}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => handleRecall(ticket.id)}
                      className="whitespace-nowrap"
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