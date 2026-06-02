import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { getProducts, createTransaction, refundTransaction, getTransactions, getDiscounts, getEscposReceipt, syncOfflineTransactions, getMyPermissions, canUse, type MyPermissions } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatMoneyAr, toArabicDigits } from '@/lib/format';
import { enqueueTransaction, registerAutoFlush, isOnline } from '@/lib/offlineQueue';
import { printEscPos, isThermalPrintSupported } from '@/lib/thermalPrint';
import { ScanBarcode, RotateCcw, ShoppingCart, Tag, Check, X, Printer } from 'lucide-react';

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
}

interface Transaction {
  id?: number;
  invoice_number: string;
  total_amount: number;
  vat_amount: number;
  subtotal: number;
  payment_method: string;
  items?: { name: string; quantity: number; price: number }[];
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
  const [cart, setCart] = useState<CartItem[]>([]);
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [loading, setLoading] = useState(true);
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

  // Offline POS (Phase E) state.
  const [queuedOffline, setQueuedOffline] = useState(false);

  // Phase 3: permission-aware UI — gate the refund flow on `pos.refund`.
  const [permissions, setPermissions] = useState<MyPermissions | null>(null);
  const canRefund = canUse(permissions, 'pos.refund');

  useEffect(() => {
    loadProducts();
    getMyPermissions().then(setPermissions).catch(() => setPermissions(null));
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
    try {
      const data = await getProducts();
      setProducts(data?.items || data || []);
    } catch (err) {
      console.error('Failed to load products:', err);
    } finally {
      setLoading(false);
    }
  }

  async function loadRecentTransactions() {
    setLoadingTransactions(true);
    try {
      const data = await getTransactions(1, 20);
      setRecentTransactions(data?.transactions || data?.items || data || []);
    } catch (err) {
      console.error('Failed to load transactions:', err);
    } finally {
      setLoadingTransactions(false);
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

  // Barcode scan handler
  function handleBarcodeScan(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && barcodeInput.trim()) {
      const barcode = barcodeInput.trim();
      const matchedProduct = products.find(
        (p) => p.barcode === barcode || p.sku === barcode
      );
      if (matchedProduct) {
        addToCart(matchedProduct);
        setBarcodeMessage({ text: `✓ ${matchedProduct.name} added`, type: 'success' });
      } else {
        setBarcodeMessage({ text: `✕ No product found for "${barcode}"`, type: 'error' });
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
      const data = await getDiscounts();
      const discounts: Discount[] = data?.items || data || [];
      const matched = discounts.find(
        (d) => d.code.toLowerCase() === discountCode.trim().toLowerCase() && d.is_active !== false
      );
      if (!matched) {
        setDiscountError('Invalid or expired discount code');
        setAppliedDiscount(null);
      } else if (matched.min_purchase && subtotal < matched.min_purchase) {
        setDiscountError(`Minimum purchase of $${matched.min_purchase.toFixed(2)} required`);
        setAppliedDiscount(null);
      } else {
        setAppliedDiscount(matched);
        setDiscountError('');
      }
    } catch (err) {
      console.error('Failed to validate discount:', err);
      setDiscountError('Failed to validate discount code');
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
        quantity: item.quantity,
        price: item.product.price,
        vat_rate: 0.15,
      }));
      // POS-01/POS-02: persist the applied discount and (when split) the per-method
      // tenders. Inventory is deducted atomically by the backend as part of the sale.
      const result = await createTransaction({
        items,
        payment_method: paymentMethod,
        discount_amount: discountAmount > 0 ? discountAmount : undefined,
        payments: splitMode
          ? splitPayments.filter((p) => (Number(p.amount) || 0) > 0)
          : undefined,
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

  async function handleRefund() {
    if (!selectedTransaction?.id) return;
    setRefundProcessing(true);
    try {
      // POS-07: the backend issues a real ZATCA credit note (type 381),
      // restores inventory, and signs it. No more negative-price fake refund.
      const result = await refundTransaction(selectedTransaction.id);

      setReceipt({
        invoice_number: result.credit_note_number,
        total_amount: result.total_amount,
        vat_amount: -(selectedTransaction.vat_amount || 0),
        subtotal: -(selectedTransaction.subtotal || 0),
        payment_method: 'refund',
        zatca_qr_base64: result.zatca_qr_base64 || '',
        zatca_status: result.zatca_status,
        items: (selectedTransaction.items || []).map((item) => ({
          name: item.name,
          quantity: item.quantity,
          price: -Math.abs(item.price),
        })),
      });
      setSelectedTransaction(null);
    } catch (err) {
      console.error('Refund failed:', err);
    } finally {
      setRefundProcessing(false);
    }
  }

  function handleNewSale() {
    setReceipt(null);
    setCart([]);
    setMode('sale');
    setSelectedTransaction(null);
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
      transfer: 'تحويل',
      refund: 'استرجاع',
      mixed: 'مدفوعات متعددة',
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
              onClick={() => { setMode('sale'); setSelectedTransaction(null); }}
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
                    onClick={() => setSelectedTransaction(txn)}
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
                <h3 className="text-white font-semibold">Refund Details</h3>
                <div className="bg-slate-700 rounded-lg p-4 space-y-2">
                  <div className="flex justify-between text-slate-300 text-sm">
                    <span>Invoice</span>
                    <span>{selectedTransaction.invoice_number}</span>
                  </div>
                  <div className="flex justify-between text-slate-300 text-sm">
                    <span>{t('payment_method')}</span>
                    <span>{selectedTransaction.payment_method}</span>
                  </div>
                  {selectedTransaction.items && selectedTransaction.items.length > 0 && (
                    <div className="border-t border-slate-600 pt-2 mt-2 space-y-1">
                      {selectedTransaction.items.map((item, idx) => (
                        <div key={idx} className="flex justify-between text-slate-400 text-xs">
                          <span>{item.name} x{item.quantity}</span>
                          <span>${(item.price * item.quantity).toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="border-t border-slate-600 pt-2 mt-2">
                    <div className="flex justify-between text-slate-400 text-sm">
                      <span>{t('subtotal')}</span>
                      <span>${selectedTransaction.subtotal?.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-slate-400 text-sm">
                      <span>{t('vat')}</span>
                      <span>${selectedTransaction.vat_amount?.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between text-white font-bold mt-1">
                      <span>Refund Amount</span>
                      <span className="text-orange-400">${selectedTransaction.total_amount?.toFixed(2)}</span>
                    </div>
                  </div>
                </div>

                <Button
                  onClick={handleRefund}
                  disabled={refundProcessing || !canRefund}
                  className="w-full bg-orange-600 hover:bg-orange-700 text-white py-6 text-lg disabled:opacity-50"
                >
                  {refundProcessing ? t('loading') : '↩ Process Refund'}
                </Button>
                {!canRefund && (
                  <p className="text-center text-sm text-orange-400/80 mt-2">
                    You don't have permission to issue refunds.
                  </p>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-center h-full text-slate-500">
                <p className="text-center">Select a transaction to process refund</p>
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
          <h2 className="text-lg font-bold text-white">{t('products')}</h2>
          <div className="flex items-center gap-2">
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

        {filteredProducts.length === 0 ? (
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
                  <SelectItem value="card" className="text-white hover:bg-slate-600">{t('card')}</SelectItem>
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
                        <SelectItem value="card" className="text-white hover:bg-slate-600">{t('card')}</SelectItem>
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

          <Button
            onClick={handleCheckout}
            disabled={cart.length === 0 || processing}
            className="w-full bg-green-600 hover:bg-green-700 text-white py-6 text-lg disabled:opacity-50"
          >
            {processing ? t('loading') : t('checkout')}
          </Button>
        </div>
      </div>
    </div>
  );
}