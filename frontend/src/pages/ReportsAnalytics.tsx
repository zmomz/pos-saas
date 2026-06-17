import { useState, useEffect, useCallback } from 'react';
import { BarChart3, DollarSign, Receipt, TrendingUp, Loader2 } from 'lucide-react';
import { useLanguage } from '@/lib/i18n';
import { formatMoney, formatNumber } from '@/lib/format';
import { getSalesSummary, getTopProducts, exportCSV, getPaymentBreakdown, getJournalExport, getProfitMarginReport, getVatSummaryReport, getInventoryReport, getRefundVoidReport, getDiscountReport, downloadReportPdf, type JournalExport, type ProfitMarginReport, type VatSummaryReport, type InventoryReport, type RefundVoidReport, type DiscountReport } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import StatTile from '@/components/dashboard/StatTile';
import Bar from '@/components/dashboard/rx/Bar';

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
    export_pdf: 'PDF',
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
    inventory_report: 'Inventory (at Cost)',
    inventory_hint: 'On-hand stock valued at cost — per product and per branch — plus a movement ledger for the last 30 days.',
    download_inventory: 'Download Inventory CSV',
    total_valuation: 'Total Stock Value',
    total_on_hand: 'Total On Hand',
    branch: 'Branch',
    by_branch: 'By Branch',
    movements: 'Stock Movements',
    no_movements: 'No stock movements in this period.',
    mv_type: 'Type',
    mv_date: 'Date',
    mv_reference: 'Reference',
    mv_qty: 'Qty',
    mv_receipt: 'Receipt',
    mv_transfer: 'Transfer',
    mv_adjustment: 'Adjustment',
    refunds_voids: 'Refunds & Voids',
    refunds_voids_hint: 'Every refund and void in the last 30 days — who did it, why, and how much.',
    download_refunds_voids: 'Download Refunds/Voids CSV',
    discounts_report: 'Discounts',
    discounts_hint: 'Every discounted sale in the last 30 days — who applied it, the code, and how much.',
    download_discounts: 'Download Discounts CSV',
    rv_type: 'Type',
    rv_refund: 'Refund',
    rv_void: 'Void',
    actor: 'Actor',
    reason: 'Reason',
    amount: 'Amount',
    when: 'When',
    invoice: 'Invoice',
    original_invoice: 'Original Invoice',
    code: 'Code',
    manual: 'Manual',
    refund_count: 'Refunds',
    void_count: 'Voids',
    discount_count: 'Discounts',
    discount_total: 'Total Discount',
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
    export_pdf: 'PDF',
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
    inventory_report: 'المخزون (بالتكلفة)',
    inventory_hint: 'قيمة المخزون المتوفر بالتكلفة — لكل منتج ولكل فرع — مع سجل الحركات لآخر 30 يومًا.',
    download_inventory: 'تنزيل ملف المخزون CSV',
    total_valuation: 'إجمالي قيمة المخزون',
    total_on_hand: 'إجمالي المتوفر',
    branch: 'الفرع',
    by_branch: 'حسب الفرع',
    movements: 'حركات المخزون',
    no_movements: 'لا توجد حركات مخزون في هذه الفترة.',
    mv_type: 'النوع',
    mv_date: 'التاريخ',
    mv_reference: 'المرجع',
    mv_qty: 'الكمية',
    mv_receipt: 'استلام',
    mv_transfer: 'تحويل',
    mv_adjustment: 'تسوية',
    refunds_voids: 'المبالغ المستردة والملغاة',
    refunds_voids_hint: 'كل عملية استرداد وإلغاء خلال آخر 30 يومًا — من قام بها ولماذا وبكم.',
    download_refunds_voids: 'تنزيل ملف المستردات/الملغاة CSV',
    discounts_report: 'الخصومات',
    discounts_hint: 'كل عملية بيع عليها خصم خلال آخر 30 يومًا — من طبّقها والرمز والمبلغ.',
    download_discounts: 'تنزيل ملف الخصومات CSV',
    rv_type: 'النوع',
    rv_refund: 'استرداد',
    rv_void: 'إلغاء',
    actor: 'المستخدم',
    reason: 'السبب',
    amount: 'المبلغ',
    when: 'التاريخ',
    invoice: 'الفاتورة',
    original_invoice: 'الفاتورة الأصلية',
    code: 'الرمز',
    manual: 'يدوي',
    refund_count: 'المستردات',
    void_count: 'الملغاة',
    discount_count: 'الخصومات',
    discount_total: 'إجمالي الخصم',
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
    export_pdf: 'PDF',
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
    inventory_report: 'इन्वेंटरी (लागत पर)',
    inventory_hint: 'उपलब्ध स्टॉक का मूल्य लागत पर — प्रति उत्पाद और प्रति शाखा — पिछले 30 दिनों के मूवमेंट लेजर के साथ।',
    download_inventory: 'इन्वेंटरी CSV डाउनलोड करें',
    total_valuation: 'कुल स्टॉक मूल्य',
    total_on_hand: 'कुल उपलब्ध',
    branch: 'शाखा',
    by_branch: 'शाखा के अनुसार',
    movements: 'स्टॉक मूवमेंट',
    no_movements: 'इस अवधि में कोई स्टॉक मूवमेंट नहीं।',
    mv_type: 'प्रकार',
    mv_date: 'तारीख',
    mv_reference: 'संदर्भ',
    mv_qty: 'मात्रा',
    mv_receipt: 'प्राप्ति',
    mv_transfer: 'स्थानांतरण',
    mv_adjustment: 'समायोजन',
    refunds_voids: 'रिफंड और रद्दीकरण',
    refunds_voids_hint: 'पिछले 30 दिनों की हर रिफंड और रद्दीकरण — किसने की, क्यों, और कितनी।',
    download_refunds_voids: 'रिफंड/रद्दीकरण CSV डाउनलोड करें',
    discounts_report: 'छूट',
    discounts_hint: 'पिछले 30 दिनों की हर छूट वाली बिक्री — किसने लगाई, कोड, और कितनी।',
    download_discounts: 'छूट CSV डाउनलोड करें',
    rv_type: 'प्रकार',
    rv_refund: 'रिफंड',
    rv_void: 'रद्द',
    actor: 'उपयोगकर्ता',
    reason: 'कारण',
    amount: 'राशि',
    when: 'कब',
    invoice: 'चालान',
    original_invoice: 'मूल चालान',
    code: 'कोड',
    manual: 'मैनुअल',
    refund_count: 'रिफंड',
    void_count: 'रद्दीकरण',
    discount_count: 'छूट',
    discount_total: 'कुल छूट',
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
    export_pdf: 'PDF',
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
    inventory_report: 'انوینٹری (لاگت پر)',
    inventory_hint: 'دستیاب اسٹاک کی قیمت لاگت پر — فی پروڈکٹ اور فی برانچ — پچھلے 30 دن کے موومنٹ لیجر کے ساتھ۔',
    download_inventory: 'انوینٹری CSV ڈاؤن لوڈ کریں',
    total_valuation: 'کل اسٹاک قیمت',
    total_on_hand: 'کل دستیاب',
    branch: 'برانچ',
    by_branch: 'برانچ کے لحاظ سے',
    movements: 'اسٹاک موومنٹس',
    no_movements: 'اس مدت میں کوئی اسٹاک موومنٹ نہیں۔',
    mv_type: 'قسم',
    mv_date: 'تاریخ',
    mv_reference: 'حوالہ',
    mv_qty: 'مقدار',
    mv_receipt: 'وصولی',
    mv_transfer: 'منتقلی',
    mv_adjustment: 'ایڈجسٹمنٹ',
    refunds_voids: 'ری فنڈز اور منسوخیاں',
    refunds_voids_hint: 'پچھلے 30 دن کی ہر ری فنڈ اور منسوخی — کس نے کی، کیوں، اور کتنی۔',
    download_refunds_voids: 'ری فنڈز/منسوخیاں CSV ڈاؤن لوڈ کریں',
    discounts_report: 'رعایتیں',
    discounts_hint: 'پچھلے 30 دن کی ہر رعایتی فروخت — کس نے لگائی، کوڈ، اور کتنی۔',
    download_discounts: 'رعایتیں CSV ڈاؤن لوڈ کریں',
    rv_type: 'قسم',
    rv_refund: 'ری فنڈ',
    rv_void: 'منسوخ',
    actor: 'صارف',
    reason: 'وجہ',
    amount: 'رقم',
    when: 'کب',
    invoice: 'انوائس',
    original_invoice: 'اصل انوائس',
    code: 'کوڈ',
    manual: 'دستی',
    refund_count: 'ری فنڈز',
    void_count: 'منسوخیاں',
    discount_count: 'رعایتیں',
    discount_total: 'کل رعایت',
  },
};

export default function ReportsAnalytics() {
  const { language } = useLanguage();
  const [period, setPeriod] = useState<string>('daily');
  const [salesData, setSalesData] = useState<SalesDataPoint[]>([]);
  const [topProducts, setTopProducts] = useState<TopProduct[]>([]);
  const [paymentTenders, setPaymentTenders] = useState<PaymentTender[]>([]);
  const [journal, setJournal] = useState<JournalExport | null>(null);
  const [margin, setMargin] = useState<ProfitMarginReport | null>(null);
  const [vat, setVat] = useState<VatSummaryReport | null>(null);
  const [inventory, setInventory] = useState<InventoryReport | null>(null);
  const [refundsVoids, setRefundsVoids] = useState<RefundVoidReport | null>(null);
  const [discounts, setDiscounts] = useState<DiscountReport | null>(null);
  const [loadingSales, setLoadingSales] = useState(true);
  const [loadingProducts, setLoadingProducts] = useState(true);
  const [loadingPayments, setLoadingPayments] = useState(true);
  const [loadingJournal, setLoadingJournal] = useState(true);
  const [loadingMargin, setLoadingMargin] = useState(true);
  const [loadingVat, setLoadingVat] = useState(true);
  const [loadingInventory, setLoadingInventory] = useState(true);
  const [loadingRefundsVoids, setLoadingRefundsVoids] = useState(true);
  const [loadingDiscounts, setLoadingDiscounts] = useState(true);
  // UX-02 (F-051): a failed fetch on any panel must surface a real error state
  // distinct from "no data" — generalizing the RPT-03 payment-panel pattern.
  const [salesError, setSalesError] = useState(false);
  const [productsError, setProductsError] = useState(false);
  const [paymentError, setPaymentError] = useState(false);
  const [journalError, setJournalError] = useState(false);
  const [marginError, setMarginError] = useState(false);
  const [vatError, setVatError] = useState(false);
  const [inventoryError, setInventoryError] = useState(false);
  const [refundsVoidsError, setRefundsVoidsError] = useState(false);
  const [discountsError, setDiscountsError] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportingJournal, setExportingJournal] = useState(false);
  const [exportingMargin, setExportingMargin] = useState(false);
  const [exportingVat, setExportingVat] = useState(false);
  const [exportingInventory, setExportingInventory] = useState(false);
  const [exportingRefundsVoids, setExportingRefundsVoids] = useState(false);
  const [exportingDiscounts, setExportingDiscounts] = useState(false);
  // F-072: which report's PDF is currently downloading (its path), else null.
  const [exportingPdf, setExportingPdf] = useState<string | null>(null);

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
    fetchInventory();
    fetchRefundsVoids();
    fetchDiscounts();
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

  async function fetchInventory() {
    setLoadingInventory(true);
    setInventoryError(false);
    try {
      const result = await getInventoryReport(30);
      setInventory(result || null);
    } catch {
      // F-070: a failed fetch must surface a real error distinct from "no stock"
      // — never silently render an empty inventory valuation (UX-02).
      setInventoryError(true);
      setInventory(null);
    } finally {
      setLoadingInventory(false);
    }
  }

  async function handleExportInventory() {
    if (!inventory?.csv_content) return;
    setExportingInventory(true);
    try {
      const blob = new Blob([inventory.csv_content], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `inventory_${inventory.from_date}_${inventory.to_date}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } finally {
      setExportingInventory(false);
    }
  }

  async function fetchRefundsVoids() {
    setLoadingRefundsVoids(true);
    setRefundsVoidsError(false);
    try {
      const result = await getRefundVoidReport(30);
      setRefundsVoids(result || null);
    } catch {
      // F-071: a failed fetch must surface a real error distinct from "no refunds"
      // — never silently render an empty audit (UX-02).
      setRefundsVoidsError(true);
      setRefundsVoids(null);
    } finally {
      setLoadingRefundsVoids(false);
    }
  }

  async function handleExportRefundsVoids() {
    if (!refundsVoids?.csv_content) return;
    setExportingRefundsVoids(true);
    try {
      const blob = new Blob([refundsVoids.csv_content], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `refunds_voids_${refundsVoids.from_date}_${refundsVoids.to_date}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } finally {
      setExportingRefundsVoids(false);
    }
  }

  async function fetchDiscounts() {
    setLoadingDiscounts(true);
    setDiscountsError(false);
    try {
      const result = await getDiscountReport(30);
      setDiscounts(result || null);
    } catch {
      // F-071: a failed fetch must surface a real error distinct from "no discounts"
      // — never silently render an empty audit (UX-02).
      setDiscountsError(true);
      setDiscounts(null);
    } finally {
      setLoadingDiscounts(false);
    }
  }

  async function handleExportDiscounts() {
    if (!discounts?.csv_content) return;
    setExportingDiscounts(true);
    try {
      const blob = new Blob([discounts.csv_content], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `discounts_${discounts.from_date}_${discounts.to_date}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } finally {
      setExportingDiscounts(false);
    }
  }

  // F-072 / RPT-10: download any report as a real (always-Arabic, RTL) PDF via
  // the shared server renderer. ``path`` keys the in-flight spinner so only the
  // clicked report's button shows the loading state.
  async function handleExportPdf(
    path: string,
    filename: string,
    params: Record<string, string | number> = {},
  ) {
    setExportingPdf(path);
    try {
      await downloadReportPdf(path, filename, params);
    } catch {
      // best-effort download — the report data is already on screen.
    } finally {
      setExportingPdf(null);
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
    if (rank === 1) return <span className="pill-gold tabular-nums">#1</span>;
    if (rank === 2) return <span className="pill-muted tabular-nums">#2</span>;
    if (rank === 3)
      return (
        <span className="dxr-sw dxr-sw-warning inline-flex h-7 min-w-7 px-2 text-[12.5px] font-semibold tabular-nums">
          #3
        </span>
      );
    return <span className="text-muted-foreground text-sm tabular-nums">#{rank}</span>;
  };

  return (
    <div className="animate-fade-up space-y-6">
      {/* Header */}
      <PageHeading
        title={tr('reports_analytics')}
        subtitle={tr('sales_chart')}
        icon={
          <span className="dxr-sw dxr-sw-brand h-10 w-10">
            <BarChart3 className="h-[18px] w-[18px]" />
          </span>
        }
      >
        <Button onClick={handleExportCSV} disabled={exporting} className="h-11 rounded-[10px] shadow-brand">
          {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('export_csv')}
        </Button>
      </PageHeading>

      {/* Period Selector */}
      <div className="dxr-seg">
        {(['daily', 'weekly', 'monthly'] as const).map((p) => (
          <button key={p} data-active={period === p} onClick={() => setPeriod(p)}>
            {tr(p)}
          </button>
        ))}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatTile
          icon={DollarSign}
          tone="brand"
          label={tr('total_revenue')}
          value={
            loadingSales ? (
              <span className="inline-block h-7 w-24 animate-pulse rounded bg-muted align-middle" />
            ) : (
              formatMoney(totalRevenue, language)
            )
          }
        />
        <StatTile
          icon={Receipt}
          tone="sky"
          label={tr('total_transactions')}
          value={
            loadingSales ? (
              <span className="inline-block h-7 w-16 animate-pulse rounded bg-muted align-middle" />
            ) : (
              totalTransactions
            )
          }
        />
        <StatTile
          icon={TrendingUp}
          tone="success"
          label={tr('avg_order_value')}
          value={
            loadingSales ? (
              <span className="inline-block h-7 w-24 animate-pulse rounded bg-muted align-middle" />
            ) : (
              formatMoney(avgOrderValue, language)
            )
          }
        />
      </div>

      {/* Sales Chart */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle className="text-foreground">{tr('sales_chart')}</CardTitle>
          <Button
            onClick={() => handleExportPdf('sales-summary', 'sales_summary', { period })}
            disabled={exportingPdf === 'sales-summary' || salesData.length === 0}
            variant="outline"
            className="shrink-0"
          >
            {exportingPdf === 'sales-summary' ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('export_pdf')}
          </Button>
        </CardHeader>
        <CardContent>
          {loadingSales ? (
            <div className="space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-8 bg-muted rounded animate-pulse" />
              ))}
            </div>
          ) : salesError ? (
            <p className="text-danger text-center py-8">{tr('error_loading')}</p>
          ) : salesData.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{tr('no_data')}</p>
          ) : (
            <div className="space-y-4">
              {salesData.map((point) => {
                const barWidth = (point.total_sales / maxSales) * 100;
                return (
                  <div key={point.date} className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground w-24 shrink-0 truncate">
                      {point.date}
                    </span>
                    <Bar pct={barWidth} className="flex-1" />
                    <span className="text-xs text-foreground font-medium whitespace-nowrap tabular-nums w-28 text-end shrink-0">
                      {formatMoney(point.total_sales, language)}
                    </span>
                    <span className="text-xs text-muted-foreground w-16 text-end shrink-0 tabular-nums">
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
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle className="text-foreground">{tr('payment_breakdown')}</CardTitle>
          <Button
            onClick={() => handleExportPdf('payment-breakdown', 'payment_breakdown')}
            disabled={exportingPdf === 'payment-breakdown' || paymentTenders.length === 0}
            variant="outline"
            className="shrink-0"
          >
            {exportingPdf === 'payment-breakdown' ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('export_pdf')}
          </Button>
        </CardHeader>
        <CardContent>
          {loadingPayments ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 bg-muted rounded animate-pulse" />
              ))}
            </div>
          ) : paymentError ? (
            <p className="text-danger text-center py-8">{tr('error_loading')}</p>
          ) : paymentTenders.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{tr('no_data')}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-card">
                  <TableHead className="text-muted-foreground">{tr('method')}</TableHead>
                  <TableHead className="text-muted-foreground text-end">{tr('collected')}</TableHead>
                  <TableHead className="text-muted-foreground text-end">{tr('refunds')}</TableHead>
                  <TableHead className="text-muted-foreground text-end">{tr('net')}</TableHead>
                  <TableHead className="text-muted-foreground text-end">{tr('txns')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paymentTenders.map((t) => (
                  <TableRow
                    key={t.tender_type}
                    className="border-border hover:bg-muted"
                  >
                    <TableCell className="text-foreground font-medium">
                      {tenderLabel(t.tender_type)}
                    </TableCell>
                    <TableCell className="text-foreground/90 text-end tabular-nums">
                      {formatMoney(t.collected, language)}
                    </TableCell>
                    <TableCell className="text-foreground/90 text-end tabular-nums">
                      {t.refunds > 0 ? `- ${formatMoney(t.refunds, language)}` : '—'}
                    </TableCell>
                    <TableCell className="text-foreground text-end font-medium tabular-nums">
                      {formatMoney(t.net, language)}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-end tabular-nums">{t.count}</TableCell>
                  </TableRow>
                ))}
                <TableRow className="border-border bg-card font-semibold">
                  <TableCell className="text-foreground">{tr('total')}</TableCell>
                  <TableCell className="text-foreground text-end tabular-nums">
                    {formatMoney(paymentTenders.reduce((s, t) => s + t.collected, 0), language)}
                  </TableCell>
                  <TableCell className="text-foreground text-end tabular-nums">
                    {formatMoney(paymentTenders.reduce((s, t) => s + t.refunds, 0), language)}
                  </TableCell>
                  <TableCell className="text-foreground text-end tabular-nums">
                    {formatMoney(paymentTenders.reduce((s, t) => s + t.net, 0), language)}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-end tabular-nums">
                    {paymentTenders.reduce((s, t) => s + t.count, 0)}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Accounting Journal / GL export (FIN-02) */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-foreground">{tr('journal_export')}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{tr('journal_hint')}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button
              onClick={handleExportJournal}
              disabled={exportingJournal || !journal || journal.lines.length === 0}
            >
              {exportingJournal ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('download_journal')}
            </Button>
            <Button
              onClick={() => handleExportPdf('journal-export', `journal_${journal?.from_date}_${journal?.to_date}`)}
              disabled={exportingPdf === 'journal-export' || !journal || journal.lines.length === 0}
              variant="outline"
            >
              {exportingPdf === 'journal-export' ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('export_pdf')}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingJournal ? (
            <div className="space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-10 bg-muted rounded animate-pulse" />
              ))}
            </div>
          ) : journalError ? (
            <div className="text-center py-8" role="alert">
              <p className="text-danger mb-3">{tr('error_loading')}</p>
              <Button variant="outline" onClick={fetchJournal}>
                {tr('retry')}
              </Button>
            </div>
          ) : !journal || journal.lines.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{tr('no_data')}</p>
          ) : (
            <>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-muted-foreground">
                  {journal.from_date} → {journal.to_date}
                </span>
                <span className={journal.balanced ? 'pill-success' : 'pill-danger'}>
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  {journal.balanced ? tr('journal_balanced') : tr('journal_unbalanced')}
                </span>
              </div>
              <Table>
                <TableHeader>
                  <TableRow className="border-border hover:bg-card">
                    <TableHead className="text-muted-foreground">{tr('account_code')}</TableHead>
                    <TableHead className="text-muted-foreground">{tr('gl_account')}</TableHead>
                    <TableHead className="text-muted-foreground">{tr('description')}</TableHead>
                    <TableHead className="text-muted-foreground text-end">{tr('debit')}</TableHead>
                    <TableHead className="text-muted-foreground text-end">{tr('credit')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {journal.lines.map((line, idx) => (
                    <TableRow
                      key={`${line.account_code}-${idx}`}
                      className="border-border hover:bg-muted"
                    >
                      <TableCell className="text-muted-foreground font-mono text-xs">
                        {line.account_code}
                      </TableCell>
                      <TableCell className="text-foreground font-medium">{line.account}</TableCell>
                      <TableCell className="text-muted-foreground text-xs">{line.description}</TableCell>
                      <TableCell className="text-foreground/90 text-end tabular-nums">
                        {line.debit > 0 ? formatMoney(line.debit, language) : '—'}
                      </TableCell>
                      <TableCell className="text-foreground/90 text-end tabular-nums">
                        {line.credit > 0 ? formatMoney(line.credit, language) : '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                  <TableRow className="border-border bg-card font-semibold">
                    <TableCell className="text-foreground" colSpan={3}>
                      {tr('total')}
                    </TableCell>
                    <TableCell className="text-foreground text-end tabular-nums">
                      {formatMoney(journal.total_debit, language)}
                    </TableCell>
                    <TableCell className="text-foreground text-end tabular-nums">
                      {formatMoney(journal.total_credit, language)}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </>
          )}
        </CardContent>
      </Card>

      {/* Profit / COGS / Margin + Dead Stock (F-068) */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-foreground">{tr('profit_margin')}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{tr('profit_margin_hint')}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button
              onClick={handleExportMargin}
              disabled={exportingMargin || !margin || margin.by_item.length === 0}
            >
              {exportingMargin ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('download_margin')}
            </Button>
            <Button
              onClick={() => handleExportPdf('profit-margin', `profit_margin_${margin?.from_date}_${margin?.to_date}`)}
              disabled={exportingPdf === 'profit-margin' || !margin || margin.by_item.length === 0}
              variant="outline"
            >
              {exportingPdf === 'profit-margin' ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('export_pdf')}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingMargin ? (
            <div className="space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-10 bg-muted rounded animate-pulse" />
              ))}
            </div>
          ) : marginError ? (
            <div className="text-center py-8" role="alert">
              <p className="text-danger mb-3">{tr('error_loading')}</p>
              <Button variant="outline" onClick={fetchMargin}>
                {tr('retry')}
              </Button>
            </div>
          ) : !margin || margin.by_item.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{tr('no_data')}</p>
          ) : (
            <>
              {/* Totals strip */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{tr('revenue')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {formatMoney(margin.totals.revenue, language)}
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{tr('cogs')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {formatMoney(margin.totals.cogs, language)}
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{tr('gross_profit')}</p>
                  <p className="text-lg font-bold text-success tabular-nums">
                    {formatMoney(margin.totals.gross_profit, language)}
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{tr('margin')}</p>
                  <p className="text-lg font-bold text-success tabular-nums">
                    {margin.totals.margin_pct.toFixed(1)}%
                  </p>
                </div>
              </div>

              {/* By item */}
              <h3 className="text-sm font-semibold text-foreground/90 mb-2">{tr('by_item')}</h3>
              <Table>
                <TableHeader>
                  <TableRow className="border-border hover:bg-card">
                    <TableHead className="text-muted-foreground">{tr('item')}</TableHead>
                    <TableHead className="text-muted-foreground text-end">{tr('qty_sold')}</TableHead>
                    <TableHead className="text-muted-foreground text-end">{tr('revenue')}</TableHead>
                    <TableHead className="text-muted-foreground text-end">{tr('cogs')}</TableHead>
                    <TableHead className="text-muted-foreground text-end">{tr('gross_profit')}</TableHead>
                    <TableHead className="text-muted-foreground text-end">{tr('margin')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {margin.by_item.map((row) => (
                    <TableRow key={row.key} className="border-border hover:bg-muted">
                      <TableCell className="text-foreground font-medium">{row.name}</TableCell>
                      <TableCell className="text-foreground/90 text-end tabular-nums">{row.qty_sold}</TableCell>
                      <TableCell className="text-foreground/90 text-end tabular-nums">
                        {formatMoney(row.revenue, language)}
                      </TableCell>
                      <TableCell className="text-foreground/90 text-end tabular-nums">
                        {formatMoney(row.cogs, language)}
                      </TableCell>
                      <TableCell className="text-success text-end tabular-nums">
                        {formatMoney(row.gross_profit, language)}
                      </TableCell>
                      <TableCell className="text-foreground/90 text-end tabular-nums">{row.margin_pct.toFixed(1)}%</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* By category */}
              {margin.by_category.length > 0 && (
                <>
                  <h3 className="text-sm font-semibold text-foreground/90 mt-6 mb-2">{tr('by_category')}</h3>
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border hover:bg-card">
                        <TableHead className="text-muted-foreground">{tr('category')}</TableHead>
                        <TableHead className="text-muted-foreground text-end">{tr('revenue')}</TableHead>
                        <TableHead className="text-muted-foreground text-end">{tr('cogs')}</TableHead>
                        <TableHead className="text-muted-foreground text-end">{tr('gross_profit')}</TableHead>
                        <TableHead className="text-muted-foreground text-end">{tr('margin')}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {margin.by_category.map((row) => (
                        <TableRow key={row.key} className="border-border hover:bg-muted">
                          <TableCell className="text-foreground font-medium">{row.name}</TableCell>
                          <TableCell className="text-foreground/90 text-end tabular-nums">
                            {formatMoney(row.revenue, language)}
                          </TableCell>
                          <TableCell className="text-foreground/90 text-end tabular-nums">
                            {formatMoney(row.cogs, language)}
                          </TableCell>
                          <TableCell className="text-success text-end tabular-nums">
                            {formatMoney(row.gross_profit, language)}
                          </TableCell>
                          <TableCell className="text-foreground/90 text-end tabular-nums">{row.margin_pct.toFixed(1)}%</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </>
              )}

              {/* Dead stock */}
              <h3 className="text-sm font-semibold text-foreground/90 mt-6 mb-1">{tr('dead_stock')}</h3>
              <p className="text-xs text-muted-foreground mb-2">{tr('dead_stock_hint')}</p>
              {margin.dead_stock.length === 0 ? (
                <p className="text-muted-foreground text-sm py-3">{tr('no_dead_stock')}</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="border-border hover:bg-card">
                      <TableHead className="text-muted-foreground">{tr('product_name')}</TableHead>
                      <TableHead className="text-muted-foreground">{tr('category')}</TableHead>
                      <TableHead className="text-muted-foreground text-end">{tr('on_hand')}</TableHead>
                      <TableHead className="text-muted-foreground text-end">{tr('cost')}</TableHead>
                      <TableHead className="text-muted-foreground text-end">{tr('stock_value')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {margin.dead_stock.map((row) => (
                      <TableRow key={row.product_id} className="border-border hover:bg-muted">
                        <TableCell className="text-foreground font-medium">{row.name}</TableCell>
                        <TableCell className="text-muted-foreground text-xs">{row.category || '—'}</TableCell>
                        <TableCell className="text-foreground/90 text-end tabular-nums">{row.quantity}</TableCell>
                        <TableCell className="text-foreground/90 text-end tabular-nums">
                          {formatMoney(row.cost_price, language)}
                        </TableCell>
                        <TableCell className="text-foreground/90 text-end tabular-nums">
                          {formatMoney(row.stock_value, language)}
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
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-foreground">{tr('vat_summary')}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{tr('vat_summary_hint')}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button onClick={handleExportVat} disabled={exportingVat || !vat}>
              {exportingVat ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('download_vat')}
            </Button>
            <Button
              onClick={() => handleExportPdf('vat-summary', `vat_summary_${vat?.from_date}_${vat?.to_date}`)}
              disabled={exportingPdf === 'vat-summary' || !vat}
              variant="outline"
            >
              {exportingPdf === 'vat-summary' ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('export_pdf')}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingVat ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 bg-muted rounded animate-pulse" />
              ))}
            </div>
          ) : vatError ? (
            <div className="text-center py-8" role="alert">
              <p className="text-danger mb-3">{tr('error_loading')}</p>
              <Button variant="outline" onClick={fetchVat}>
                {tr('retry')}
              </Button>
            </div>
          ) : !vat ? (
            <p className="text-muted-foreground text-center py-8">{tr('no_data')}</p>
          ) : (
            <>
              {/* Net-VAT strip */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{tr('vat_collected')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {formatMoney(vat.vat_collected, language)}
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{tr('vat_reversed')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {formatMoney(vat.vat_reversed, language)}
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{tr('net_vat')}</p>
                  <p className="text-lg font-bold text-success tabular-nums">
                    {formatMoney(vat.net_vat, language)}
                  </p>
                </div>
              </div>

              {/* The ZATCA VAT-return boxes */}
              <Table>
                <TableHeader>
                  <TableRow className="border-border hover:bg-card">
                    <TableHead className="text-muted-foreground">{tr('tax_category')}</TableHead>
                    <TableHead className="text-muted-foreground text-end">{tr('taxable_base')}</TableHead>
                    <TableHead className="text-muted-foreground text-end">{tr('vat_amount')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {vat.buckets.map((b) => (
                    <TableRow key={b.key} className="border-border hover:bg-muted">
                      <TableCell className="text-foreground font-medium">{b.label}</TableCell>
                      <TableCell className="text-foreground/90 text-end tabular-nums">
                        {formatMoney(b.taxable_base, language)}
                      </TableCell>
                      <TableCell className="text-foreground/90 text-end tabular-nums">
                        {formatMoney(b.vat_amount, language)}
                      </TableCell>
                    </TableRow>
                  ))}
                  <TableRow className="border-border bg-muted/40">
                    <TableCell className="text-foreground font-semibold">{tr('net_vat')}</TableCell>
                    <TableCell className="text-foreground/90 text-end tabular-nums">
                      {formatMoney(vat.total_taxable_base, language)}
                    </TableCell>
                    <TableCell className="text-success text-end font-semibold tabular-nums">
                      {formatMoney(vat.net_vat, language)}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </>
          )}
        </CardContent>
      </Card>

      {/* Inventory — on-hand valuation at cost + movements (F-070) */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-foreground">{tr('inventory_report')}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{tr('inventory_hint')}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button onClick={handleExportInventory} disabled={exportingInventory || !inventory}>
              {exportingInventory ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('download_inventory')}
            </Button>
            <Button
              onClick={() => handleExportPdf('inventory', `inventory_${inventory?.from_date}_${inventory?.to_date}`)}
              disabled={exportingPdf === 'inventory' || !inventory}
              variant="outline"
            >
              {exportingPdf === 'inventory' ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('export_pdf')}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingInventory ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 bg-muted rounded animate-pulse" />
              ))}
            </div>
          ) : inventoryError ? (
            <div className="text-center py-8" role="alert">
              <p className="text-danger mb-3">{tr('error_loading')}</p>
              <Button variant="outline" onClick={fetchInventory}>
                {tr('retry')}
              </Button>
            </div>
          ) : !inventory ? (
            <p className="text-muted-foreground text-center py-8">{tr('no_data')}</p>
          ) : (
            <>
              {/* Totals strip */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-5">
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{tr('total_on_hand')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {formatNumber(inventory.total_quantity, language, 0)}
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{tr('total_valuation')}</p>
                  <p className="text-lg font-bold text-success tabular-nums">
                    {formatMoney(inventory.total_valuation, language)}
                  </p>
                </div>
              </div>

              {/* On-hand valuation at cost, by product */}
              {inventory.by_product.length === 0 ? (
                <p className="text-muted-foreground text-sm py-3">{tr('no_data')}</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="border-border hover:bg-card">
                      <TableHead className="text-muted-foreground">{tr('product_name')}</TableHead>
                      <TableHead className="text-muted-foreground">{tr('category')}</TableHead>
                      <TableHead className="text-muted-foreground text-end">{tr('on_hand')}</TableHead>
                      <TableHead className="text-muted-foreground text-end">{tr('cost')}</TableHead>
                      <TableHead className="text-muted-foreground text-end">{tr('stock_value')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {inventory.by_product.map((row) => (
                      <TableRow key={row.product_id} className="border-border hover:bg-muted">
                        <TableCell className="text-foreground font-medium">{row.name}</TableCell>
                        <TableCell className="text-muted-foreground text-xs">{row.category || '—'}</TableCell>
                        <TableCell className="text-foreground/90 text-end tabular-nums">{row.quantity}</TableCell>
                        <TableCell className="text-foreground/90 text-end tabular-nums">
                          {formatMoney(row.cost_price, language)}
                        </TableCell>
                        <TableCell className="text-foreground/90 text-end tabular-nums">
                          {formatMoney(row.stock_value, language)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}

              {/* Per-branch valuation */}
              {inventory.by_branch.length > 0 && (
                <div className="mt-6">
                  <h4 className="text-sm font-semibold text-foreground/90 mb-2">{tr('by_branch')}</h4>
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border hover:bg-card">
                        <TableHead className="text-muted-foreground">{tr('branch')}</TableHead>
                        <TableHead className="text-muted-foreground text-end">{tr('on_hand')}</TableHead>
                        <TableHead className="text-muted-foreground text-end">{tr('stock_value')}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {inventory.by_branch.map((b) => (
                        <TableRow key={b.branch_id} className="border-border hover:bg-muted">
                          <TableCell className="text-foreground font-medium">
                            {b.branch_name || `#${b.branch_id}`}
                          </TableCell>
                          <TableCell className="text-foreground/90 text-end tabular-nums">{b.quantity}</TableCell>
                          <TableCell className="text-foreground/90 text-end tabular-nums">
                            {formatMoney(b.stock_value, language)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              {/* Movement ledger */}
              <div className="mt-6">
                <h4 className="text-sm font-semibold text-foreground/90 mb-2">{tr('movements')}</h4>
                {inventory.movements.length === 0 ? (
                  <p className="text-muted-foreground text-sm py-3">{tr('no_movements')}</p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow className="border-border hover:bg-card">
                        <TableHead className="text-muted-foreground">{tr('mv_date')}</TableHead>
                        <TableHead className="text-muted-foreground">{tr('mv_type')}</TableHead>
                        <TableHead className="text-muted-foreground">{tr('product_name')}</TableHead>
                        <TableHead className="text-muted-foreground text-end">{tr('mv_qty')}</TableHead>
                        <TableHead className="text-muted-foreground">{tr('mv_reference')}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {inventory.movements.map((m, idx) => (
                        <TableRow key={idx} className="border-border hover:bg-muted">
                          <TableCell className="text-muted-foreground text-xs">{m.date}</TableCell>
                          <TableCell className="text-foreground/90 text-xs">
                            {tr(`mv_${m.type}`)}
                          </TableCell>
                          <TableCell className="text-foreground">
                            {m.product_name || (m.product_id ? `#${m.product_id}` : '—')}
                          </TableCell>
                          <TableCell className="text-foreground/90 text-end tabular-nums">{m.quantity}</TableCell>
                          <TableCell className="text-muted-foreground text-xs">{m.reference || '—'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Refunds & Voids — actor / reason / amount over a window (F-071) */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-foreground">{tr('refunds_voids')}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{tr('refunds_voids_hint')}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button onClick={handleExportRefundsVoids} disabled={exportingRefundsVoids || !refundsVoids}>
              {exportingRefundsVoids ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('download_refunds_voids')}
            </Button>
            <Button
              onClick={() => handleExportPdf('refunds-voids', `refunds_voids_${refundsVoids?.from_date}_${refundsVoids?.to_date}`)}
              disabled={exportingPdf === 'refunds-voids' || !refundsVoids}
              variant="outline"
            >
              {exportingPdf === 'refunds-voids' ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('export_pdf')}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingRefundsVoids ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 bg-muted rounded animate-pulse" />
              ))}
            </div>
          ) : refundsVoidsError ? (
            <div className="text-center py-8" role="alert">
              <p className="text-danger mb-3">{tr('error_loading')}</p>
              <Button variant="outline" onClick={fetchRefundsVoids}>
                {tr('retry')}
              </Button>
            </div>
          ) : !refundsVoids ? (
            <p className="text-muted-foreground text-center py-8">{tr('no_data')}</p>
          ) : (
            <>
              {/* Totals strip */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-5">
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{tr('refund_count')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {refundsVoids.refund_count}
                    <span className="text-sm text-muted-foreground ms-2">
                      {formatMoney(refundsVoids.refund_total, language)}
                    </span>
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{tr('void_count')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {refundsVoids.void_count}
                    <span className="text-sm text-muted-foreground ms-2">
                      {formatMoney(refundsVoids.void_total, language)}
                    </span>
                  </p>
                </div>
              </div>

              {refundsVoids.rows.length === 0 ? (
                <p className="text-muted-foreground text-center py-6">{tr('no_data')}</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="border-border hover:bg-card">
                      <TableHead className="text-muted-foreground">{tr('rv_type')}</TableHead>
                      <TableHead className="text-muted-foreground">{tr('invoice')}</TableHead>
                      <TableHead className="text-muted-foreground">{tr('actor')}</TableHead>
                      <TableHead className="text-muted-foreground">{tr('reason')}</TableHead>
                      <TableHead className="text-muted-foreground text-end">{tr('amount')}</TableHead>
                      <TableHead className="text-muted-foreground">{tr('when')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {refundsVoids.rows.map((r, idx) => (
                      <TableRow key={idx} className="border-border hover:bg-muted">
                        <TableCell>
                          <span className={r.type === 'void' ? 'pill-danger' : 'pill-warning'}>
                            {tr(`rv_${r.type}`)}
                          </span>
                        </TableCell>
                        <TableCell className="text-foreground text-xs">
                          {r.invoice_number || '—'}
                          {r.original_invoice ? (
                            <span className="text-muted-foreground"> ← {r.original_invoice}</span>
                          ) : null}
                        </TableCell>
                        <TableCell className="text-foreground/90 text-xs">{r.actor || '—'}</TableCell>
                        <TableCell className="text-muted-foreground text-xs">{r.reason || '—'}</TableCell>
                        <TableCell className="text-foreground/90 text-end tabular-nums">
                          {formatMoney(r.amount, language)}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-xs">
                          {r.timestamp ? r.timestamp.slice(0, 10) : '—'}
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

      {/* Discounts — actor / code / amount over a window (F-071) */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-foreground">{tr('discounts_report')}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{tr('discounts_hint')}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button onClick={handleExportDiscounts} disabled={exportingDiscounts || !discounts}>
              {exportingDiscounts ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('download_discounts')}
            </Button>
            <Button
              onClick={() => handleExportPdf('discounts', `discounts_${discounts?.from_date}_${discounts?.to_date}`)}
              disabled={exportingPdf === 'discounts' || !discounts}
              variant="outline"
            >
              {exportingPdf === 'discounts' ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('export_pdf')}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingDiscounts ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 bg-muted rounded animate-pulse" />
              ))}
            </div>
          ) : discountsError ? (
            <div className="text-center py-8" role="alert">
              <p className="text-danger mb-3">{tr('error_loading')}</p>
              <Button variant="outline" onClick={fetchDiscounts}>
                {tr('retry')}
              </Button>
            </div>
          ) : !discounts ? (
            <p className="text-muted-foreground text-center py-8">{tr('no_data')}</p>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-5">
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{tr('discount_count')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">{discounts.discount_count}</p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{tr('discount_total')}</p>
                  <p className="text-lg font-bold text-success tabular-nums">
                    {formatMoney(discounts.discount_total, language)}
                  </p>
                </div>
              </div>

              {discounts.rows.length === 0 ? (
                <p className="text-muted-foreground text-center py-6">{tr('no_data')}</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="border-border hover:bg-card">
                      <TableHead className="text-muted-foreground">{tr('invoice')}</TableHead>
                      <TableHead className="text-muted-foreground">{tr('actor')}</TableHead>
                      <TableHead className="text-muted-foreground">{tr('code')}</TableHead>
                      <TableHead className="text-muted-foreground text-end">{tr('amount')}</TableHead>
                      <TableHead className="text-muted-foreground">{tr('when')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {discounts.rows.map((r, idx) => (
                      <TableRow key={idx} className="border-border hover:bg-muted">
                        <TableCell className="text-foreground text-xs">{r.invoice_number || '—'}</TableCell>
                        <TableCell className="text-foreground/90 text-xs">{r.actor || '—'}</TableCell>
                        <TableCell className="text-muted-foreground text-xs">
                          {r.is_manual ? (
                            <span className="italic text-muted-foreground">{tr('manual')}</span>
                          ) : (
                            r.code
                          )}
                        </TableCell>
                        <TableCell className="text-foreground/90 text-end tabular-nums">
                          {formatMoney(r.discount_amount, language)}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-xs">
                          {r.timestamp ? r.timestamp.slice(0, 10) : '—'}
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

      {/* Top Products */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle className="text-foreground">{tr('top_products')}</CardTitle>
          <Button
            onClick={() => handleExportPdf('top-products', 'top_products')}
            disabled={exportingPdf === 'top-products' || topProducts.length === 0}
            variant="outline"
            className="shrink-0"
          >
            {exportingPdf === 'top-products' ? <Loader2 className="h-4 w-4 animate-spin" /> : tr('export_pdf')}
          </Button>
        </CardHeader>
        <CardContent>
          {loadingProducts ? (
            <div className="space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-10 bg-muted rounded animate-pulse" />
              ))}
            </div>
          ) : productsError ? (
            <p className="text-danger text-center py-8">{tr('error_loading')}</p>
          ) : topProducts.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{tr('no_data')}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-card">
                  <TableHead className="text-muted-foreground">{tr('rank')}</TableHead>
                  <TableHead className="text-muted-foreground">{tr('product_name')}</TableHead>
                  <TableHead className="text-muted-foreground text-end">{tr('qty_sold')}</TableHead>
                  <TableHead className="text-muted-foreground text-end">{tr('revenue')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {topProducts.map((product, idx) => (
                  <TableRow
                    key={product.product_id}
                    className="border-border hover:bg-muted"
                  >
                    <TableCell>{rankBadge(idx + 1)}</TableCell>
                    <TableCell className="text-foreground font-medium">{product.name}</TableCell>
                    <TableCell className="text-foreground/90 text-end tabular-nums">
                      {product.total_quantity}
                    </TableCell>
                    <TableCell className="text-foreground/90 text-end tabular-nums">
                      {formatMoney(product.total_revenue, language)}
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