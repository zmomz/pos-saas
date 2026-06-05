import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import { getSalesSummary, getTopProducts, exportCSV, getPaymentBreakdown, getJournalExport, getProfitMarginReport, getVatSummaryReport, type JournalExport, type ProfitMarginReport, type VatSummaryReport } from '@/lib/api';
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
    journal_export: 'Accounting Journal (GL)',
    journal_hint: 'Double-entry journal for the last 30 days — import into Zoho / QuickBooks / Odoo.',
    download_journal: 'Download Journal CSV',
    account_code: 'Code',
    gl_account: 'Account',
    description: 'Description',
    debit: 'Debit',
    credit: 'Credit',
    journal_balanced: 'Balanced',
    journal_unbalanced: 'Out of balance',
    retry: 'Retry',
    profit_margin: 'Profit & Margin',
    profit_margin_hint: 'Gross profit and margin by item and category for the last 30 days — COGS uses the cost recorded at sale time.',
    download_margin: 'Download Margin CSV',
    cogs: 'COGS',
    gross_profit: 'Gross Profit',
    margin: 'Margin %',
    by_item: 'By Item',
    by_category: 'By Category',
    item: 'Item',
    category: 'Category',
    dead_stock: 'Dead Stock',
    dead_stock_hint: 'On-hand products with no sale in the last 30 days.',
    on_hand: 'On Hand',
    cost: 'Cost',
    stock_value: 'Stock Value',
    no_dead_stock: 'No dead stock — everything is selling.',
    vat_summary: 'VAT Summary',
    vat_summary_hint: 'Output VAT by rate for the last 30 days — the ZATCA VAT-return boxes. Credit notes are netted.',
    download_vat: 'Download VAT CSV',
    tax_category: 'Tax Category',
    taxable_base: 'Taxable Base',
    vat_amount: 'VAT Amount',
    vat_collected: 'VAT Collected',
    vat_reversed: 'VAT Reversed',
    net_vat: 'Net VAT Payable',
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
    journal_export: 'قيد اليومية المحاسبي (الأستاذ العام)',
    journal_hint: 'قيد مزدوج لآخر 30 يومًا — للاستيراد إلى زوهو / كويك بوكس / أودو.',
    download_journal: 'تنزيل ملف القيود CSV',
    account_code: 'الرمز',
    gl_account: 'الحساب',
    description: 'البيان',
    debit: 'مدين',
    credit: 'دائن',
    journal_balanced: 'متوازن',
    journal_unbalanced: 'غير متوازن',
    retry: 'إعادة المحاولة',
    profit_margin: 'الربح والهامش',
    profit_margin_hint: 'إجمالي الربح والهامش حسب الصنف والفئة لآخر 30 يومًا — تكلفة البضاعة المباعة تُحتسب بالتكلفة وقت البيع.',
    download_margin: 'تنزيل ملف الهامش CSV',
    cogs: 'تكلفة البضاعة',
    gross_profit: 'إجمالي الربح',
    margin: 'الهامش %',
    by_item: 'حسب الصنف',
    by_category: 'حسب الفئة',
    item: 'الصنف',
    category: 'الفئة',
    dead_stock: 'المخزون الراكد',
    dead_stock_hint: 'منتجات متوفرة في المخزون ولم تُبَع خلال آخر 30 يومًا.',
    on_hand: 'المتوفر',
    cost: 'التكلفة',
    stock_value: 'قيمة المخزون',
    no_dead_stock: 'لا يوجد مخزون راكد — كل المنتجات تُباع.',
    vat_summary: 'ملخص ضريبة القيمة المضافة',
    vat_summary_hint: 'ضريبة المخرجات حسب النسبة لآخر 30 يومًا — خانات إقرار ضريبة القيمة المضافة لهيئة الزكاة. تُخصم الإشعارات الدائنة.',
    download_vat: 'تنزيل ملف الضريبة CSV',
    tax_category: 'الفئة الضريبية',
    taxable_base: 'الوعاء الخاضع للضريبة',
    vat_amount: 'مبلغ الضريبة',
    vat_collected: 'الضريبة المحصلة',
    vat_reversed: 'الضريبة المعكوسة',
    net_vat: 'صافي الضريبة المستحقة',
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
    journal_export: 'लेखा जर्नल (GL)',
    journal_hint: 'पिछले 30 दिनों की डबल-एंट्री जर्नल — Zoho / QuickBooks / Odoo में आयात करें।',
    download_journal: 'जर्नल CSV डाउनलोड करें',
    account_code: 'कोड',
    gl_account: 'खाता',
    description: 'विवरण',
    debit: 'डेबिट',
    credit: 'क्रेडिट',
    journal_balanced: 'संतुलित',
    journal_unbalanced: 'असंतुलित',
    retry: 'पुनः प्रयास',
    profit_margin: 'लाभ और मार्जिन',
    profit_margin_hint: 'पिछले 30 दिनों के लिए वस्तु और श्रेणी के अनुसार सकल लाभ और मार्जिन — COGS बिक्री के समय की लागत का उपयोग करता है।',
    download_margin: 'मार्जिन CSV डाउनलोड करें',
    cogs: 'COGS',
    gross_profit: 'सकल लाभ',
    margin: 'मार्जिन %',
    by_item: 'वस्तु अनुसार',
    by_category: 'श्रेणी अनुसार',
    item: 'वस्तु',
    category: 'श्रेणी',
    dead_stock: 'मृत स्टॉक',
    dead_stock_hint: 'पिछले 30 दिनों में बिना बिक्री वाले उपलब्ध उत्पाद।',
    on_hand: 'उपलब्ध',
    cost: 'लागत',
    stock_value: 'स्टॉक मूल्य',
    no_dead_stock: 'कोई मृत स्टॉक नहीं — सब कुछ बिक रहा है।',
    vat_summary: 'वैट सारांश',
    vat_summary_hint: 'पिछले 30 दिनों के लिए दर के अनुसार आउटपुट वैट — ZATCA वैट-रिटर्न बॉक्स। क्रेडिट नोट घटाए जाते हैं।',
    download_vat: 'वैट CSV डाउनलोड करें',
    tax_category: 'कर श्रेणी',
    taxable_base: 'कर योग्य आधार',
    vat_amount: 'वैट राशि',
    vat_collected: 'वैट संग्रहित',
    vat_reversed: 'वैट प्रतिवर्तित',
    net_vat: 'देय शुद्ध वैट',
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
    journal_export: 'اکاؤنٹنگ جرنل (GL)',
    journal_hint: 'پچھلے 30 دن کی ڈبل اینٹری جرنل — Zoho / QuickBooks / Odoo میں درآمد کریں۔',
    download_journal: 'جرنل CSV ڈاؤن لوڈ کریں',
    account_code: 'کوڈ',
    gl_account: 'اکاؤنٹ',
    description: 'تفصیل',
    debit: 'ڈیبٹ',
    credit: 'کریڈٹ',
    journal_balanced: 'متوازن',
    journal_unbalanced: 'غیر متوازن',
    retry: 'دوبارہ کوشش',
    profit_margin: 'منافع اور مارجن',
    profit_margin_hint: 'پچھلے 30 دن کے لیے آئٹم اور زمرے کے حساب سے مجموعی منافع اور مارجن — COGS فروخت کے وقت کی لاگت استعمال کرتا ہے۔',
    download_margin: 'مارجن CSV ڈاؤن لوڈ کریں',
    cogs: 'لاگتِ فروخت',
    gross_profit: 'مجموعی منافع',
    margin: 'مارجن %',
    by_item: 'آئٹم کے حساب سے',
    by_category: 'زمرے کے حساب سے',
    item: 'آئٹم',
    category: 'زمرہ',
    dead_stock: 'غیر فعال اسٹاک',
    dead_stock_hint: 'موجودہ اسٹاک والے مصنوعات جو پچھلے 30 دن میں فروخت نہیں ہوئیں۔',
    on_hand: 'دستیاب',
    cost: 'لاگت',
    stock_value: 'اسٹاک ویلیو',
    no_dead_stock: 'کوئی غیر فعال اسٹاک نہیں — سب کچھ فروخت ہو رہا ہے۔',
    vat_summary: 'ویٹ خلاصہ',
    vat_summary_hint: 'پچھلے 30 دن کے لیے شرح کے حساب سے آؤٹ پٹ ویٹ — ZATCA ویٹ ریٹرن خانے۔ کریڈٹ نوٹس منہا کیے جاتے ہیں۔',
    download_vat: 'ویٹ CSV ڈاؤن لوڈ کریں',
    tax_category: 'ٹیکس زمرہ',
    taxable_base: 'قابل ٹیکس بنیاد',
    vat_amount: 'ویٹ رقم',
    vat_collected: 'ویٹ وصول شدہ',
    vat_reversed: 'ویٹ واپس شدہ',
    net_vat: 'قابل ادائیگی خالص ویٹ',
  },
};

export default function ReportsAnalytics() {
  const navigate = useNavigate();
  const { language, setLanguage, isRTL } = useLanguage();
  const [period, setPeriod] = useState<string>('daily');
  const [salesData, setSalesData] = useState<SalesDataPoint[]>([]);
  const [topProducts, setTopProducts] = useState<TopProduct[]>([]);
  const [paymentTenders, setPaymentTenders] = useState<PaymentTender[]>([]);
  const [journal, setJournal] = useState<JournalExport | null>(null);
  const [margin, setMargin] = useState<ProfitMarginReport | null>(null);
  const [vat, setVat] = useState<VatSummaryReport | null>(null);
  const [loadingSales, setLoadingSales] = useState(true);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [loadingPayments, setLoadingPayments] = useState(true);
  const [loadingJournal, setLoadingJournal] = useState(true);
  const [loadingMargin, setLoadingMargin] = useState(true);
  const [loadingVat, setLoadingVat] = useState(true);
  // UX-02 (F-051): a failed fetch on any panel must surface a real error state
  // distinct from "no data" — generalizing the RPT-03 payment-panel pattern.
  const [salesError, setSalesError] = useState(false);
  const [productsError, setProductsError] = useState(false);
  const [paymentError, setPaymentError] = useState(false);
  const [journalError, setJournalError] = useState(false);
  const [marginError, setMarginError] = useState(false);
  const [vatError, setVatError] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportingJournal, setExportingJournal] = useState(false);
  const [exportingMargin, setExportingMargin] = useState(false);
  const [exportingVat, setExportingVat] = useState(false);

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
    fetchJournal();
    fetchMargin();
    fetchVat();
  }, []);

  async function fetchSalesData() {
    setLoadingSales(true);
    setSalesError(false);
    try {
      const result = await getSalesSummary(period);
      setSalesData(result?.data || []);
    } catch {
      // A failed fetch must not look like an empty period (UX-02).
      setSalesError(true);
      setSalesData([]);
    } finally {
      setLoadingSales(false);
    }
  }

  async function fetchTopProducts() {
    setLoadingProducts(true);
    setProductsError(false);
    try {
      const result = await getTopProducts(10);
      setTopProducts(result?.products || []);
    } catch {
      // A failed fetch must not look like "no products sold" (UX-02).
      setProductsError(true);
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

  async function fetchJournal() {
    setLoadingJournal(true);
    setJournalError(false);
    try {
      const result = await getJournalExport(30);
      setJournal(result || null);
    } catch {
      // FIN-02: a failed fetch must surface a real error distinct from an empty
      // period — never silently render an empty journal (UX-02).
      setJournalError(true);
      setJournal(null);
    } finally {
      setLoadingJournal(false);
    }
  }

  async function handleExportJournal() {
    if (!journal?.csv_content) return;
    setExportingJournal(true);
    try {
      const blob = new Blob([journal.csv_content], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `journal_${journal.from_date}_${journal.to_date}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } finally {
      setExportingJournal(false);
    }
  }

  async function fetchMargin() {
    setLoadingMargin(true);
    setMarginError(false);
    try {
      const result = await getProfitMarginReport(30, 30);
      setMargin(result || null);
    } catch {
      // F-068: a failed fetch must surface a real error distinct from "no sales"
      // — never silently render an empty margin report (UX-02).
      setMarginError(true);
      setMargin(null);
    } finally {
      setLoadingMargin(false);
    }
  }

  async function handleExportMargin() {
    if (!margin?.csv_content) return;
    setExportingMargin(true);
    try {
      const blob = new Blob([margin.csv_content], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `profit_margin_${margin.from_date}_${margin.to_date}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } finally {
      setExportingMargin(false);
    }
  }

  async function fetchVat() {
    setLoadingVat(true);
    setVatError(false);
    try {
      const result = await getVatSummaryReport(30);
      setVat(result || null);
    } catch {
      // F-069: a failed fetch must surface a real error distinct from "no sales"
      // — never silently render an empty VAT return (UX-02).
      setVatError(true);
      setVat(null);
    } finally {
      setLoadingVat(false);
    }
  }

  async function handleExportVat() {
    if (!vat?.csv_content) return;
    setExportingVat(true);
    try {
      const blob = new Blob([vat.csv_content], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `vat_summary_${vat.from_date}_${vat.to_date}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } finally {
      setExportingVat(false);
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
          ) : salesError ? (
            <p className="text-red-400 text-center py-8">{tr('error_loading')}</p>
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

      {/* Accounting Journal / GL export (FIN-02) */}
      <Card className="bg-slate-800 border-slate-700 mb-8">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-white">{tr('journal_export')}</CardTitle>
            <p className="text-xs text-slate-400 mt-1">{tr('journal_hint')}</p>
          </div>
          <Button
            onClick={handleExportJournal}
            disabled={exportingJournal || !journal || journal.lines.length === 0}
            className="bg-blue-600 hover:bg-blue-700 text-white shrink-0"
          >
            {exportingJournal ? '...' : tr('download_journal')}
          </Button>
        </CardHeader>
        <CardContent>
          {loadingJournal ? (
            <div className="space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-10 bg-slate-700 rounded animate-pulse" />
              ))}
            </div>
          ) : journalError ? (
            <div className="text-center py-8" role="alert">
              <p className="text-red-400 mb-3">{tr('error_loading')}</p>
              <Button
                variant="outline"
                className="border-slate-700 text-slate-300 hover:bg-slate-800"
                onClick={fetchJournal}
              >
                {tr('retry')}
              </Button>
            </div>
          ) : !journal || journal.lines.length === 0 ? (
            <p className="text-slate-400 text-center py-8">{tr('no_data')}</p>
          ) : (
            <>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-slate-500">
                  {journal.from_date} → {journal.to_date}
                </span>
                <Badge
                  className={
                    journal.balanced
                      ? 'bg-emerald-600 text-white hover:bg-emerald-500'
                      : 'bg-red-600 text-white hover:bg-red-500'
                  }
                >
                  {journal.balanced ? tr('journal_balanced') : tr('journal_unbalanced')}
                </Badge>
              </div>
              <Table>
                <TableHeader>
                  <TableRow className="border-slate-700 hover:bg-slate-800">
                    <TableHead className="text-slate-400">{tr('account_code')}</TableHead>
                    <TableHead className="text-slate-400">{tr('gl_account')}</TableHead>
                    <TableHead className="text-slate-400">{tr('description')}</TableHead>
                    <TableHead className="text-slate-400 text-end">{tr('debit')}</TableHead>
                    <TableHead className="text-slate-400 text-end">{tr('credit')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {journal.lines.map((line, idx) => (
                    <TableRow
                      key={`${line.account_code}-${idx}`}
                      className="border-slate-700 hover:bg-slate-750"
                    >
                      <TableCell className="text-slate-400 font-mono text-xs">
                        {line.account_code}
                      </TableCell>
                      <TableCell className="text-white font-medium">{line.account}</TableCell>
                      <TableCell className="text-slate-400 text-xs">{line.description}</TableCell>
                      <TableCell className="text-slate-300 text-end">
                        {line.debit > 0
                          ? `${tr('sar')} ${line.debit.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                          : '—'}
                      </TableCell>
                      <TableCell className="text-slate-300 text-end">
                        {line.credit > 0
                          ? `${tr('sar')} ${line.credit.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                          : '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                  <TableRow className="border-slate-700 bg-slate-850 font-semibold">
                    <TableCell className="text-white" colSpan={3}>
                      {tr('total')}
                    </TableCell>
                    <TableCell className="text-white text-end">
                      {tr('sar')} {journal.total_debit.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </TableCell>
                    <TableCell className="text-white text-end">
                      {tr('sar')} {journal.total_credit.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </>
          )}
        </CardContent>
      </Card>

      {/* Profit / COGS / Margin + Dead Stock (F-068) */}
      <Card className="bg-slate-800 border-slate-700 mb-8">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-white">{tr('profit_margin')}</CardTitle>
            <p className="text-xs text-slate-400 mt-1">{tr('profit_margin_hint')}</p>
          </div>
          <Button
            onClick={handleExportMargin}
            disabled={exportingMargin || !margin || margin.by_item.length === 0}
            className="bg-blue-600 hover:bg-blue-700 text-white shrink-0"
          >
            {exportingMargin ? '...' : tr('download_margin')}
          </Button>
        </CardHeader>
        <CardContent>
          {loadingMargin ? (
            <div className="space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-10 bg-slate-700 rounded animate-pulse" />
              ))}
            </div>
          ) : marginError ? (
            <div className="text-center py-8" role="alert">
              <p className="text-red-400 mb-3">{tr('error_loading')}</p>
              <Button
                variant="outline"
                className="border-slate-700 text-slate-300 hover:bg-slate-800"
                onClick={fetchMargin}
              >
                {tr('retry')}
              </Button>
            </div>
          ) : !margin || margin.by_item.length === 0 ? (
            <p className="text-slate-400 text-center py-8">{tr('no_data')}</p>
          ) : (
            <>
              {/* Totals strip */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                <div className="bg-slate-900 rounded-lg p-3">
                  <p className="text-xs text-slate-400">{tr('revenue')}</p>
                  <p className="text-lg font-bold text-white">
                    {tr('sar')} {margin.totals.revenue.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </p>
                </div>
                <div className="bg-slate-900 rounded-lg p-3">
                  <p className="text-xs text-slate-400">{tr('cogs')}</p>
                  <p className="text-lg font-bold text-white">
                    {tr('sar')} {margin.totals.cogs.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </p>
                </div>
                <div className="bg-slate-900 rounded-lg p-3">
                  <p className="text-xs text-slate-400">{tr('gross_profit')}</p>
                  <p className="text-lg font-bold text-emerald-400">
                    {tr('sar')} {margin.totals.gross_profit.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </p>
                </div>
                <div className="bg-slate-900 rounded-lg p-3">
                  <p className="text-xs text-slate-400">{tr('margin')}</p>
                  <p className="text-lg font-bold text-emerald-400">
                    {margin.totals.margin_pct.toFixed(1)}%
                  </p>
                </div>
              </div>

              {/* By item */}
              <h3 className="text-sm font-semibold text-slate-300 mb-2">{tr('by_item')}</h3>
              <Table>
                <TableHeader>
                  <TableRow className="border-slate-700 hover:bg-slate-800">
                    <TableHead className="text-slate-400">{tr('item')}</TableHead>
                    <TableHead className="text-slate-400 text-end">{tr('qty_sold')}</TableHead>
                    <TableHead className="text-slate-400 text-end">{tr('revenue')}</TableHead>
                    <TableHead className="text-slate-400 text-end">{tr('cogs')}</TableHead>
                    <TableHead className="text-slate-400 text-end">{tr('gross_profit')}</TableHead>
                    <TableHead className="text-slate-400 text-end">{tr('margin')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {margin.by_item.map((row) => (
                    <TableRow key={row.key} className="border-slate-700 hover:bg-slate-750">
                      <TableCell className="text-white font-medium">{row.name}</TableCell>
                      <TableCell className="text-slate-300 text-end">{row.qty_sold}</TableCell>
                      <TableCell className="text-slate-300 text-end">
                        {tr('sar')} {row.revenue.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </TableCell>
                      <TableCell className="text-slate-300 text-end">
                        {tr('sar')} {row.cogs.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </TableCell>
                      <TableCell className="text-emerald-400 text-end">
                        {tr('sar')} {row.gross_profit.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </TableCell>
                      <TableCell className="text-slate-300 text-end">{row.margin_pct.toFixed(1)}%</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* By category */}
              {margin.by_category.length > 0 && (
                <>
                  <h3 className="text-sm font-semibold text-slate-300 mt-6 mb-2">{tr('by_category')}</h3>
                  <Table>
                    <TableHeader>
                      <TableRow className="border-slate-700 hover:bg-slate-800">
                        <TableHead className="text-slate-400">{tr('category')}</TableHead>
                        <TableHead className="text-slate-400 text-end">{tr('revenue')}</TableHead>
                        <TableHead className="text-slate-400 text-end">{tr('cogs')}</TableHead>
                        <TableHead className="text-slate-400 text-end">{tr('gross_profit')}</TableHead>
                        <TableHead className="text-slate-400 text-end">{tr('margin')}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {margin.by_category.map((row) => (
                        <TableRow key={row.key} className="border-slate-700 hover:bg-slate-750">
                          <TableCell className="text-white font-medium">{row.name}</TableCell>
                          <TableCell className="text-slate-300 text-end">
                            {tr('sar')} {row.revenue.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                          </TableCell>
                          <TableCell className="text-slate-300 text-end">
                            {tr('sar')} {row.cogs.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                          </TableCell>
                          <TableCell className="text-emerald-400 text-end">
                            {tr('sar')} {row.gross_profit.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                          </TableCell>
                          <TableCell className="text-slate-300 text-end">{row.margin_pct.toFixed(1)}%</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </>
              )}

              {/* Dead stock */}
              <h3 className="text-sm font-semibold text-slate-300 mt-6 mb-1">{tr('dead_stock')}</h3>
              <p className="text-xs text-slate-500 mb-2">{tr('dead_stock_hint')}</p>
              {margin.dead_stock.length === 0 ? (
                <p className="text-slate-400 text-sm py-3">{tr('no_dead_stock')}</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="border-slate-700 hover:bg-slate-800">
                      <TableHead className="text-slate-400">{tr('product_name')}</TableHead>
                      <TableHead className="text-slate-400">{tr('category')}</TableHead>
                      <TableHead className="text-slate-400 text-end">{tr('on_hand')}</TableHead>
                      <TableHead className="text-slate-400 text-end">{tr('cost')}</TableHead>
                      <TableHead className="text-slate-400 text-end">{tr('stock_value')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {margin.dead_stock.map((row) => (
                      <TableRow key={row.product_id} className="border-slate-700 hover:bg-slate-750">
                        <TableCell className="text-white font-medium">{row.name}</TableCell>
                        <TableCell className="text-slate-400 text-xs">{row.category || '—'}</TableCell>
                        <TableCell className="text-slate-300 text-end">{row.quantity}</TableCell>
                        <TableCell className="text-slate-300 text-end">
                          {tr('sar')} {row.cost_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </TableCell>
                        <TableCell className="text-slate-300 text-end">
                          {tr('sar')} {row.stock_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* VAT / Tax Summary by rate (F-069) */}
      <Card className="bg-slate-800 border-slate-700 mb-8">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-white">{tr('vat_summary')}</CardTitle>
            <p className="text-xs text-slate-400 mt-1">{tr('vat_summary_hint')}</p>
          </div>
          <Button
            onClick={handleExportVat}
            disabled={exportingVat || !vat}
            className="bg-blue-600 hover:bg-blue-700 text-white shrink-0"
          >
            {exportingVat ? '...' : tr('download_vat')}
          </Button>
        </CardHeader>
        <CardContent>
          {loadingVat ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 bg-slate-700 rounded animate-pulse" />
              ))}
            </div>
          ) : vatError ? (
            <div className="text-center py-8" role="alert">
              <p className="text-red-400 mb-3">{tr('error_loading')}</p>
              <Button
                variant="outline"
                className="border-slate-700 text-slate-300 hover:bg-slate-800"
                onClick={fetchVat}
              >
                {tr('retry')}
              </Button>
            </div>
          ) : !vat ? (
            <p className="text-slate-400 text-center py-8">{tr('no_data')}</p>
          ) : (
            <>
              {/* Net-VAT strip */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
                <div className="bg-slate-900 rounded-lg p-3">
                  <p className="text-xs text-slate-400">{tr('vat_collected')}</p>
                  <p className="text-lg font-bold text-white">
                    {tr('sar')} {vat.vat_collected.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </p>
                </div>
                <div className="bg-slate-900 rounded-lg p-3">
                  <p className="text-xs text-slate-400">{tr('vat_reversed')}</p>
                  <p className="text-lg font-bold text-white">
                    {tr('sar')} {vat.vat_reversed.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </p>
                </div>
                <div className="bg-slate-900 rounded-lg p-3">
                  <p className="text-xs text-slate-400">{tr('net_vat')}</p>
                  <p className="text-lg font-bold text-emerald-400">
                    {tr('sar')} {vat.net_vat.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </p>
                </div>
              </div>

              {/* The ZATCA VAT-return boxes */}
              <Table>
                <TableHeader>
                  <TableRow className="border-slate-700 hover:bg-slate-800">
                    <TableHead className="text-slate-400">{tr('tax_category')}</TableHead>
                    <TableHead className="text-slate-400 text-end">{tr('taxable_base')}</TableHead>
                    <TableHead className="text-slate-400 text-end">{tr('vat_amount')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {vat.buckets.map((b) => (
                    <TableRow key={b.key} className="border-slate-700 hover:bg-slate-750">
                      <TableCell className="text-white font-medium">{b.label}</TableCell>
                      <TableCell className="text-slate-300 text-end">
                        {tr('sar')} {b.taxable_base.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </TableCell>
                      <TableCell className="text-slate-300 text-end">
                        {tr('sar')} {b.vat_amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </TableCell>
                    </TableRow>
                  ))}
                  <TableRow className="border-slate-700 bg-slate-900/40">
                    <TableCell className="text-white font-semibold">{tr('net_vat')}</TableCell>
                    <TableCell className="text-slate-300 text-end">
                      {tr('sar')} {vat.total_taxable_base.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </TableCell>
                    <TableCell className="text-emerald-400 text-end font-semibold">
                      {tr('sar')} {vat.net_vat.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </>
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
          ) : productsError ? (
            <p className="text-red-400 text-center py-8">{tr('error_loading')}</p>
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