import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import { getSalesSummary, getTopProducts, exportCSV, getPaymentBreakdown } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

interface SalesDataPoint {
  date: string;
  total_sales: number;
  transaction_count: number;
}

interface TopProduct {
  product_id: number;
  name: string;
  total_quantity: number;
  total_revenue: number;
}

interface PaymentTender {
  tender_type: string;
  collected: number;
  refunds: number;
  net: number;
  count: number;
}

const reportTranslations: Record<string, Record<string, string>> = {
  en: {
    reports_analytics: 'Reports & Analytics',
    back_to_dashboard: 'Back to Dashboard',
    period: 'Period',
    daily: 'Daily',
    weekly: 'Weekly',
    monthly: 'Monthly',
    total_revenue: 'Total Revenue',
    total_transactions: 'Total Transactions',
    avg_order_value: 'Average Order Value',
    sales_chart: 'Sales Overview',
    top_products: 'Top Products',
    rank: 'Rank',
    product_name: 'Product Name',
    qty_sold: 'Qty Sold',
    revenue: 'Revenue',
    export_csv: 'Export CSV',
    loading: 'Loading...',
    no_data: 'No data available',
    sar: 'SAR',
    payment_breakdown: 'Payment Breakdown',
    method: 'Method',
    collected: 'Collected',
    refunds: 'Refunds',
    net: 'Net',
    txns: 'Txns',
    total: 'Total',
    error_loading: 'Could not load data. Please retry.',
    tender_cash: 'Cash',
    tender_card: 'Card',
    tender_mada: 'Mada',
    tender_applepay: 'Apple Pay',
    tender_stcpay: 'STC Pay',
    tender_tabby: 'Tabby',
    tender_tamara: 'Tamara',
    tender_transfer: 'Bank Transfer',
    tender_loyalty: 'Loyalty',
  },
  ar: {
    reports_analytics: 'التقارير والتحليلات',
    back_to_dashboard: 'العودة للوحة التحكم',
    period: 'الفترة',
    daily: 'يومي',
    weekly: 'أسبوعي',
    monthly: 'شهري',
    total_revenue: 'إجمالي الإيرادات',
    total_transactions: 'إجمالي المعاملات',
    avg_order_value: 'متوسط قيمة الطلب',
    sales_chart: 'نظرة عامة على المبيعات',
    top_products: 'أفضل المنتجات',
    rank: 'الترتيب',
    product_name: 'اسم المنتج',
    qty_sold: 'الكمية المباعة',
    revenue: 'الإيرادات',
    export_csv: 'تصدير CSV',
    loading: 'جاري التحميل...',
    no_data: 'لا توجد بيانات',
    sar: 'ر.س',
    payment_breakdown: 'تفصيل طرق الدفع',
    method: 'الطريقة',
    collected: 'المحصّل',
    refunds: 'المستردات',
    net: 'الصافي',
    txns: 'العمليات',
    total: 'الإجمالي',
    error_loading: 'تعذّر تحميل البيانات. حاول مرة أخرى.',
    tender_cash: 'نقدي',
    tender_card: 'بطاقة',
    tender_mada: 'مدى',
    tender_applepay: 'أبل باي',
    tender_stcpay: 'STC Pay',
    tender_tabby: 'تابي',
    tender_tamara: 'تمارا',
    tender_transfer: 'تحويل بنكي',
    tender_loyalty: 'نقاط الولاء',
  },
  hi: {
    reports_analytics: 'रिपोर्ट और विश्लेषण',
    back_to_dashboard: 'डैशबोर्ड पर वापस',
    period: 'अवधि',
    daily: 'दैनिक',
    weekly: 'साप्ताहिक',
    monthly: 'मासिक',
    total_revenue: 'कुल राजस्व',
    total_transactions: 'कुल लेनदेन',
    avg_order_value: 'औसत ऑर्डर मूल्य',
    sales_chart: 'बिक्री अवलोकन',
    top_products: 'शीर्ष उत्पाद',
    rank: 'रैंक',
    product_name: 'उत्पाद का नाम',
    qty_sold: 'बेची गई मात्रा',
    revenue: 'राजस्व',
    export_csv: 'CSV निर्यात',
    loading: 'लोड हो रहा है...',
    no_data: 'कोई डेटा उपलब्ध नहीं',
    sar: 'SAR',
    payment_breakdown: 'भुगतान विवरण',
    method: 'विधि',
    collected: 'एकत्रित',
    refunds: 'रिफंड',
    net: 'शुद्ध',
    txns: 'लेनदेन',
    total: 'कुल',
    error_loading: 'डेटा लोड नहीं हो सका। पुनः प्रयास करें।',
    tender_cash: 'नकद',
    tender_card: 'कार्ड',
    tender_mada: 'मदा',
    tender_applepay: 'ऐपल पे',
    tender_stcpay: 'STC पे',
    tender_tabby: 'टैबी',
    tender_tamara: 'तमारा',
    tender_transfer: 'बैंक ट्रांसफर',
    tender_loyalty: 'लॉयल्टी',
  },
  ur: {
    reports_analytics: 'رپورٹس اور تجزیات',
    back_to_dashboard: 'ڈیش بورڈ پر واپس',
    period: 'مدت',
    daily: 'روزانہ',
    weekly: 'ہفتہ وار',
    monthly: 'ماہانہ',
    total_revenue: 'کل آمدنی',
    total_transactions: 'کل لین دین',
    avg_order_value: 'اوسط آرڈر ویلیو',
    sales_chart: 'فروخت کا جائزہ',
    top_products: 'سرفہرست مصنوعات',
    rank: 'درجہ',
    product_name: 'مصنوعات کا نام',
    qty_sold: 'فروخت شدہ مقدار',
    revenue: 'آمدنی',
    export_csv: 'CSV برآمد',
    loading: 'لوڈ ہو رہا ہے...',
    no_data: 'کوئی ڈیٹا دستیاب نہیں',
    sar: 'SAR',
    payment_breakdown: 'ادائیگی کی تفصیل',
    method: 'طریقہ',
    collected: 'وصول شدہ',
    refunds: 'ری فنڈز',
    net: 'خالص',
    txns: 'لین دین',
    total: 'کل',
    error_loading: 'ڈیٹا لوڈ نہیں ہو سکا۔ دوبارہ کوشش کریں۔',
    tender_cash: 'نقد',
    tender_card: 'کارڈ',
    tender_mada: 'مدیٰ',
    tender_applepay: 'ایپل پے',
    tender_stcpay: 'STC پے',
    tender_tabby: 'ٹیبی',
    tender_tamara: 'تمارا',
    tender_transfer: 'بینک منتقلی',
    tender_loyalty: 'وفاداری',
  },
};

export default function ReportsAnalytics() {
  const navigate = useNavigate();
  const { language, setLanguage, isRTL } = useLanguage();
  const [period, setPeriod] = useState<string>('daily');
  const [salesData, setSalesData] = useState<SalesDataPoint[]>([]);
  const [topProducts, setTopProducts] = useState<TopProduct[]>([]);
  const [paymentTenders, setPaymentTenders] = useState<PaymentTender[]>([]);
  const [loadingSales, setLoadingSales] = useState(true);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [loadingPayments, setLoadingPayments] = useState(true);
  const [paymentError, setPaymentError] = useState(false);
  const [exporting, setExporting] = useState(false);

  const tr = useCallback(
    (key: string): string => {
      return reportTranslations[language]?.[key] || reportTranslations.en[key] || key;
    },
    [language]
  );

  useEffect(() => {
    fetchSalesData();
  }, [period]);

  useEffect(() => {
    fetchTopProducts();
    fetchPaymentBreakdown();
  }, []);

  async function fetchSalesData() {
    setLoadingSales(true);
    try {
      const result = await getSalesSummary(period);
      setSalesData(result?.data || []);
    } catch {
      setSalesData([]);
    } finally {
      setLoadingSales(false);
    }
  }

  async function fetchTopProducts() {
    setLoadingProducts(true);
    try {
      const result = await getTopProducts(10);
      setTopProducts(result?.products || []);
    } catch {
      setTopProducts([]);
    } finally {
      setLoadingProducts(false);
    }
  }

  async function fetchPaymentBreakdown() {
    setLoadingPayments(true);
    setPaymentError(false);
    try {
      const result = await getPaymentBreakdown(30);
      setPaymentTenders(result?.tenders || []);
    } catch {
      // RPT-03: surface a real error distinct from "no data" so a failed fetch
      // doesn't masquerade as an empty period (the broader page-wide offline/
      // error states are F-051).
      setPaymentError(true);
      setPaymentTenders([]);
    } finally {
      setLoadingPayments(false);
    }
  }

  // Localize a tender_type to its display label; fall back to the raw type for
  // any tender the UI doesn't yet have a label for.
  function tenderLabel(type: string): string {
    const key = `tender_${type}`;
    const label = reportTranslations[language]?.[key] || reportTranslations.en[key];
    return label || type;
  }

  async function handleExportCSV() {
    setExporting(true);
    try {
      const result = await exportCSV();
      if (result?.csv_content) {
        const blob = new Blob([result.csv_content], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'sales_report.csv';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
    } catch {
      // silently handle error
    } finally {
      setExporting(false);
    }
  }

  const totalRevenue = salesData.reduce((sum, d) => sum + d.total_sales, 0);
  const totalTransactions = salesData.reduce((sum, d) => sum + d.transaction_count, 0);
  const avgOrderValue = totalTransactions > 0 ? totalRevenue / totalTransactions : 0;
  const maxSales = Math.max(...salesData.map((d) => d.total_sales), 1);

  const rankBadge = (rank: number) => {
    if (rank === 1)
      return (
        <Badge className="bg-yellow-500 text-black hover:bg-yellow-400">🥇 #1</Badge>
      );
    if (rank === 2)
      return (
        <Badge className="bg-gray-300 text-black hover:bg-gray-200">🥈 #2</Badge>
      );
    if (rank === 3)
      return (
        <Badge className="bg-amber-700 text-white hover:bg-amber-600">🥉 #3</Badge>
      );
    return <span className="text-slate-400 text-sm">#{rank}</span>;
  };

  return (
    <div
      className="min-h-screen bg-slate-900 text-white p-4 md:p-8"
      dir={isRTL ? 'rtl' : 'ltr'}
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
        <div className="flex items-center gap-4">
          <Button
            variant="outline"
            className="border-slate-700 text-slate-300 hover:bg-slate-800"
            onClick={() => navigate('/client')}
          >
            ← {tr('back_to_dashboard')}
          </Button>
          <h1 className="text-2xl font-bold">{tr('reports_analytics')}</h1>
        </div>
        <div className="flex items-center gap-3">
          <Select value={language} onValueChange={(val) => setLanguage(val as Language)}>
            <SelectTrigger className="w-[130px] bg-slate-800 border-slate-700 text-white">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-800 border-slate-700">
              {languageOptions.map((opt) => (
                <SelectItem
                  key={opt.value}
                  value={opt.value}
                  className="text-white hover:bg-slate-700"
                >
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            onClick={handleExportCSV}
            disabled={exporting}
            className="bg-blue-600 hover:bg-blue-700 text-white"
          >
            {exporting ? '...' : tr('export_csv')}
          </Button>
        </div>
      </div>

      {/* Period Selector */}
      <div className="flex gap-2 mb-6">
        {(['daily', 'weekly', 'monthly'] as const).map((p) => (
          <Button
            key={p}
            variant={period === p ? 'default' : 'outline'}
            className={
              period === p
                ? 'bg-blue-600 hover:bg-blue-700 text-white'
                : 'border-slate-700 text-slate-300 hover:bg-slate-800'
            }
            onClick={() => setPeriod(p)}
          >
            {tr(p)}
          </Button>
        ))}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <Card className="bg-slate-800 border-slate-700">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-slate-400">{tr('total_revenue')}</CardTitle>
          </CardHeader>
          <CardContent>
            {loadingSales ? (
              <div className="h-8 bg-slate-700 rounded animate-pulse" />
            ) : (
              <p className="text-2xl font-bold text-white">
                {tr('sar')} {totalRevenue.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </p>
            )}
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-slate-400">
              {tr('total_transactions')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loadingSales ? (
              <div className="h-8 bg-slate-700 rounded animate-pulse" />
            ) : (
              <p className="text-2xl font-bold text-white">{totalTransactions}</p>
            )}
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-slate-400">{tr('avg_order_value')}</CardTitle>
          </CardHeader>
          <CardContent>
            {loadingSales ? (
              <div className="h-8 bg-slate-700 rounded animate-pulse" />
            ) : (
              <p className="text-2xl font-bold text-white">
                {tr('sar')} {avgOrderValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Sales Chart */}
      <Card className="bg-slate-800 border-slate-700 mb-8">
        <CardHeader>
          <CardTitle className="text-white">{tr('sales_chart')}</CardTitle>
        </CardHeader>
        <CardContent>
          {loadingSales ? (
            <div className="space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-8 bg-slate-700 rounded animate-pulse" />
              ))}
            </div>
          ) : salesData.length === 0 ? (
            <p className="text-slate-400 text-center py-8">{tr('no_data')}</p>
          ) : (
            <div className="space-y-3">
              {salesData.map((point) => {
                const barWidth = (point.total_sales / maxSales) * 100;
                return (
                  <div key={point.date} className="flex items-center gap-3">
                    <span className="text-xs text-slate-400 w-24 shrink-0 truncate">
                      {point.date}
                    </span>
                    <div className="flex-1 bg-slate-700 rounded-full h-7 relative overflow-hidden">
                      <div
                        className="bg-blue-600 h-full rounded-full transition-all duration-500 flex items-center justify-end px-2"
                        style={{ width: `${Math.max(barWidth, 5)}%` }}
                      >
                        <span className="text-xs text-white font-medium whitespace-nowrap">
                          {tr('sar')} {point.total_sales.toLocaleString()}
                        </span>
                      </div>
                    </div>
                    <span className="text-xs text-slate-500 w-16 text-end shrink-0">
                      {point.transaction_count} txn
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Payment Breakdown (RPT-03) */}
      <Card className="bg-slate-800 border-slate-700 mb-8">
        <CardHeader>
          <CardTitle className="text-white">{tr('payment_breakdown')}</CardTitle>
        </CardHeader>
        <CardContent>
          {loadingPayments ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 bg-slate-700 rounded animate-pulse" />
              ))}
            </div>
          ) : paymentError ? (
            <p className="text-red-400 text-center py-8">{tr('error_loading')}</p>
          ) : paymentTenders.length === 0 ? (
            <p className="text-slate-400 text-center py-8">{tr('no_data')}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-slate-700 hover:bg-slate-800">
                  <TableHead className="text-slate-400">{tr('method')}</TableHead>
                  <TableHead className="text-slate-400 text-end">{tr('collected')}</TableHead>
                  <TableHead className="text-slate-400 text-end">{tr('refunds')}</TableHead>
                  <TableHead className="text-slate-400 text-end">{tr('net')}</TableHead>
                  <TableHead className="text-slate-400 text-end">{tr('txns')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paymentTenders.map((t) => (
                  <TableRow
                    key={t.tender_type}
                    className="border-slate-700 hover:bg-slate-750"
                  >
                    <TableCell className="text-white font-medium">
                      {tenderLabel(t.tender_type)}
                    </TableCell>
                    <TableCell className="text-slate-300 text-end">
                      {tr('sar')} {t.collected.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </TableCell>
                    <TableCell className="text-slate-300 text-end">
                      {t.refunds > 0
                        ? `- ${tr('sar')} ${t.refunds.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                        : '—'}
                    </TableCell>
                    <TableCell className="text-white text-end font-medium">
                      {tr('sar')} {t.net.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </TableCell>
                    <TableCell className="text-slate-400 text-end">{t.count}</TableCell>
                  </TableRow>
                ))}
                <TableRow className="border-slate-700 bg-slate-850 font-semibold">
                  <TableCell className="text-white">{tr('total')}</TableCell>
                  <TableCell className="text-white text-end">
                    {tr('sar')} {paymentTenders
                      .reduce((s, t) => s + t.collected, 0)
                      .toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </TableCell>
                  <TableCell className="text-white text-end">
                    {tr('sar')} {paymentTenders
                      .reduce((s, t) => s + t.refunds, 0)
                      .toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </TableCell>
                  <TableCell className="text-white text-end">
                    {tr('sar')} {paymentTenders
                      .reduce((s, t) => s + t.net, 0)
                      .toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </TableCell>
                  <TableCell className="text-slate-400 text-end">
                    {paymentTenders.reduce((s, t) => s + t.count, 0)}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Top Products */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader>
          <CardTitle className="text-white">{tr('top_products')}</CardTitle>
        </CardHeader>
        <CardContent>
          {loadingProducts ? (
            <div className="space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-10 bg-slate-700 rounded animate-pulse" />
              ))}
            </div>
          ) : topProducts.length === 0 ? (
            <p className="text-slate-400 text-center py-8">{tr('no_data')}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-slate-700 hover:bg-slate-800">
                  <TableHead className="text-slate-400">{tr('rank')}</TableHead>
                  <TableHead className="text-slate-400">{tr('product_name')}</TableHead>
                  <TableHead className="text-slate-400 text-end">{tr('qty_sold')}</TableHead>
                  <TableHead className="text-slate-400 text-end">{tr('revenue')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {topProducts.map((product, idx) => (
                  <TableRow
                    key={product.product_id}
                    className="border-slate-700 hover:bg-slate-750"
                  >
                    <TableCell>{rankBadge(idx + 1)}</TableCell>
                    <TableCell className="text-white font-medium">{product.name}</TableCell>
                    <TableCell className="text-slate-300 text-end">
                      {product.total_quantity}
                    </TableCell>
                    <TableCell className="text-slate-300 text-end">
                      {tr('sar')} {product.total_revenue.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}