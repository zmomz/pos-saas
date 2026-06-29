import { useState, useEffect } from 'react';
import { BarChart3, DollarSign, Receipt, TrendingUp, Loader2 } from 'lucide-react';
import { useLanguage } from '@/lib/i18n';
import { formatMoney, formatNumber } from '@/lib/format';
import { getSalesSummary, getTopProducts, exportCSV, getPaymentBreakdown, getJournalExport, getProfitMarginReport, getVatSummaryReport, getInventoryReport, getRefundVoidReport, getDiscountReport, downloadReportPdf, type JournalExport, type ProfitMarginReport, type VatSummaryReport, type InventoryReport, type RefundVoidReport, type DiscountReport } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import StatTile from '@/components/dashboard/StatTile';
import Bar from '@/components/dashboard/rx/Bar';

interface SalesDataPoint {
  period: string;
  total_sales: number;
  transaction_count: number;
}

interface TopProduct {
  product_id: number;
  name: string;
  total_quantity_sold: number;
  total_revenue: number;
}

interface PaymentTender {
  tender_type: string;
  collected: number;
  refunds: number;
  net: number;
  count: number;
}

export default function ReportsAnalytics() {
  const { t, language } = useLanguage();
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
      setSalesData(result?.items || []);
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
      setTopProducts(result?.items || []);
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
    const label = t(key);
    return label === key ? type : label;
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
        title={t('reports_analytics')}
        subtitle={t('sales_chart')}
        icon={
          <span className="dxr-sw dxr-sw-brand h-10 w-10">
            <BarChart3 className="h-[18px] w-[18px]" />
          </span>
        }
      >
        <Button onClick={handleExportCSV} disabled={exporting} className="h-11 rounded-[10px] shadow-brand">
          {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : t('export_csv')}
        </Button>
      </PageHeading>

      {/* Period Selector */}
      <div className="dxr-seg">
        {(['daily', 'weekly', 'monthly'] as const).map((p) => (
          <button key={p} data-active={period === p} onClick={() => setPeriod(p)}>
            {t(p)}
          </button>
        ))}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatTile
          icon={DollarSign}
          tone="brand"
          label={t('total_revenue')}
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
          label={t('total_transactions')}
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
          label={t('avg_order_value')}
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
          <CardTitle className="text-foreground">{t('sales_chart')}</CardTitle>
          <Button
            onClick={() => handleExportPdf('sales-summary', 'sales_summary', { period })}
            disabled={exportingPdf === 'sales-summary' || salesData.length === 0}
            variant="outline"
            className="shrink-0"
          >
            {exportingPdf === 'sales-summary' ? <Loader2 className="h-4 w-4 animate-spin" /> : t('export_pdf')}
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
            <p className="text-danger text-center py-8">{t('error_loading')}</p>
          ) : salesData.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{t('no_data')}</p>
          ) : (
            <div className="space-y-4">
              {salesData.map((point) => {
                const barWidth = (point.total_sales / maxSales) * 100;
                return (
                  <div key={point.period} className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground w-24 shrink-0 truncate">
                      {point.period}
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
          <CardTitle className="text-foreground">{t('payment_breakdown')}</CardTitle>
          <Button
            onClick={() => handleExportPdf('payment-breakdown', 'payment_breakdown')}
            disabled={exportingPdf === 'payment-breakdown' || paymentTenders.length === 0}
            variant="outline"
            className="shrink-0"
          >
            {exportingPdf === 'payment-breakdown' ? <Loader2 className="h-4 w-4 animate-spin" /> : t('export_pdf')}
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
            <p className="text-danger text-center py-8">{t('error_loading')}</p>
          ) : paymentTenders.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{t('no_data')}</p>
          ) : (
            <table className="dxr-tbl">
              <thead>
                <tr className="border-border hover:bg-card">
                  <th className="text-muted-foreground">{t('method')}</th>
                  <th className="text-muted-foreground text-end">{t('collected')}</th>
                  <th className="text-muted-foreground text-end">{t('refunds')}</th>
                  <th className="text-muted-foreground text-end">{t('net')}</th>
                  <th className="text-muted-foreground text-end">{t('txns')}</th>
                </tr>
              </thead>
              <tbody>
                {paymentTenders.map((tender) => (
                  <tr
                    key={tender.tender_type}
                    className="border-border hover:bg-muted"
                  >
                    <td className="text-foreground font-medium">
                      {tenderLabel(tender.tender_type)}
                    </td>
                    <td className="text-foreground/90 text-end tabular-nums">
                      {formatMoney(tender.collected, language)}
                    </td>
                    <td className="text-foreground/90 text-end tabular-nums">
                      {tender.refunds > 0 ? `- ${formatMoney(tender.refunds, language)}` : '—'}
                    </td>
                    <td className="text-foreground text-end font-medium tabular-nums">
                      {formatMoney(tender.net, language)}
                    </td>
                    <td className="text-muted-foreground text-end tabular-nums">{tender.count}</td>
                  </tr>
                ))}
                <tr className="border-border bg-card font-semibold">
                  <td className="text-foreground">{t('total')}</td>
                  <td className="text-foreground text-end tabular-nums">
                    {formatMoney(paymentTenders.reduce((s, t) => s + t.collected, 0), language)}
                  </td>
                  <td className="text-foreground text-end tabular-nums">
                    {formatMoney(paymentTenders.reduce((s, t) => s + t.refunds, 0), language)}
                  </td>
                  <td className="text-foreground text-end tabular-nums">
                    {formatMoney(paymentTenders.reduce((s, t) => s + t.net, 0), language)}
                  </td>
                  <td className="text-muted-foreground text-end tabular-nums">
                    {paymentTenders.reduce((s, t) => s + t.count, 0)}
                  </td>
                </tr>
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Accounting Journal / GL export (FIN-02) */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-foreground">{t('journal_export')}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{t('journal_hint')}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button
              onClick={handleExportJournal}
              disabled={exportingJournal || !journal || journal.lines.length === 0}
            >
              {exportingJournal ? <Loader2 className="h-4 w-4 animate-spin" /> : t('download_journal')}
            </Button>
            <Button
              onClick={() => handleExportPdf('journal-export', `journal_${journal?.from_date}_${journal?.to_date}`)}
              disabled={exportingPdf === 'journal-export' || !journal || journal.lines.length === 0}
              variant="outline"
            >
              {exportingPdf === 'journal-export' ? <Loader2 className="h-4 w-4 animate-spin" /> : t('export_pdf')}
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
              <p className="text-danger mb-3">{t('error_loading')}</p>
              <Button variant="outline" onClick={fetchJournal}>
                {t('retry')}
              </Button>
            </div>
          ) : !journal || journal.lines.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{t('no_data')}</p>
          ) : (
            <>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-muted-foreground">
                  {journal.from_date} → {journal.to_date}
                </span>
                <span className={journal.balanced ? 'pill-success' : 'pill-danger'}>
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                  {journal.balanced ? t('journal_balanced') : t('journal_unbalanced')}
                </span>
              </div>
              <table className="dxr-tbl">
                <thead>
                  <tr className="border-border hover:bg-card">
                    <th className="text-muted-foreground">{t('account_code')}</th>
                    <th className="text-muted-foreground">{t('gl_account')}</th>
                    <th className="text-muted-foreground">{t('description')}</th>
                    <th className="text-muted-foreground text-end">{t('debit')}</th>
                    <th className="text-muted-foreground text-end">{t('credit')}</th>
                  </tr>
                </thead>
                <tbody>
                  {journal.lines.map((line, idx) => (
                    <tr
                      key={`${line.account_code}-${idx}`}
                      className="border-border hover:bg-muted"
                    >
                      <td className="text-muted-foreground font-mono text-xs">
                        {line.account_code}
                      </td>
                      <td className="text-foreground font-medium">{line.account}</td>
                      <td className="text-muted-foreground text-xs">{line.description}</td>
                      <td className="text-foreground/90 text-end tabular-nums">
                        {line.debit > 0 ? formatMoney(line.debit, language) : '—'}
                      </td>
                      <td className="text-foreground/90 text-end tabular-nums">
                        {line.credit > 0 ? formatMoney(line.credit, language) : '—'}
                      </td>
                    </tr>
                  ))}
                  <tr className="border-border bg-card font-semibold">
                    <td className="text-foreground" colSpan={3}>
                      {t('total')}
                    </td>
                    <td className="text-foreground text-end tabular-nums">
                      {formatMoney(journal.total_debit, language)}
                    </td>
                    <td className="text-foreground text-end tabular-nums">
                      {formatMoney(journal.total_credit, language)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </>
          )}
        </CardContent>
      </Card>

      {/* Profit / COGS / Margin + Dead Stock (F-068) */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-foreground">{t('profit_margin')}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{t('profit_margin_hint')}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button
              onClick={handleExportMargin}
              disabled={exportingMargin || !margin || margin.by_item.length === 0}
            >
              {exportingMargin ? <Loader2 className="h-4 w-4 animate-spin" /> : t('download_margin')}
            </Button>
            <Button
              onClick={() => handleExportPdf('profit-margin', `profit_margin_${margin?.from_date}_${margin?.to_date}`)}
              disabled={exportingPdf === 'profit-margin' || !margin || margin.by_item.length === 0}
              variant="outline"
            >
              {exportingPdf === 'profit-margin' ? <Loader2 className="h-4 w-4 animate-spin" /> : t('export_pdf')}
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
              <p className="text-danger mb-3">{t('error_loading')}</p>
              <Button variant="outline" onClick={fetchMargin}>
                {t('retry')}
              </Button>
            </div>
          ) : !margin || margin.by_item.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{t('no_data')}</p>
          ) : (
            <>
              {/* Totals strip */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('revenue')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {formatMoney(margin.totals.revenue, language)}
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('cogs')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {formatMoney(margin.totals.cogs, language)}
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('gross_profit')}</p>
                  <p className="text-lg font-bold text-success tabular-nums">
                    {formatMoney(margin.totals.gross_profit, language)}
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('margin')}</p>
                  <p className="text-lg font-bold text-success tabular-nums">
                    {margin.totals.margin_pct.toFixed(1)}%
                  </p>
                </div>
              </div>

              {/* By item */}
              <h3 className="text-sm font-semibold text-foreground/90 mb-2">{t('by_item')}</h3>
              <table className="dxr-tbl">
                <thead>
                  <tr className="border-border hover:bg-card">
                    <th className="text-muted-foreground">{t('item')}</th>
                    <th className="text-muted-foreground text-end">{t('qty_sold')}</th>
                    <th className="text-muted-foreground text-end">{t('revenue')}</th>
                    <th className="text-muted-foreground text-end">{t('cogs')}</th>
                    <th className="text-muted-foreground text-end">{t('gross_profit')}</th>
                    <th className="text-muted-foreground text-end">{t('margin')}</th>
                  </tr>
                </thead>
                <tbody>
                  {margin.by_item.map((row) => (
                    <tr key={row.key} className="border-border hover:bg-muted">
                      <td className="text-foreground font-medium">{row.name}</td>
                      <td className="text-foreground/90 text-end tabular-nums">{row.qty_sold}</td>
                      <td className="text-foreground/90 text-end tabular-nums">
                        {formatMoney(row.revenue, language)}
                      </td>
                      <td className="text-foreground/90 text-end tabular-nums">
                        {formatMoney(row.cogs, language)}
                      </td>
                      <td className="text-success text-end tabular-nums">
                        {formatMoney(row.gross_profit, language)}
                      </td>
                      <td className="text-foreground/90 text-end tabular-nums">{row.margin_pct.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* By category */}
              {margin.by_category.length > 0 && (
                <>
                  <h3 className="text-sm font-semibold text-foreground/90 mt-6 mb-2">{t('by_category')}</h3>
                  <table className="dxr-tbl">
                    <thead>
                      <tr className="border-border hover:bg-card">
                        <th className="text-muted-foreground">{t('category')}</th>
                        <th className="text-muted-foreground text-end">{t('revenue')}</th>
                        <th className="text-muted-foreground text-end">{t('cogs')}</th>
                        <th className="text-muted-foreground text-end">{t('gross_profit')}</th>
                        <th className="text-muted-foreground text-end">{t('margin')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {margin.by_category.map((row) => (
                        <tr key={row.key} className="border-border hover:bg-muted">
                          <td className="text-foreground font-medium">{row.name}</td>
                          <td className="text-foreground/90 text-end tabular-nums">
                            {formatMoney(row.revenue, language)}
                          </td>
                          <td className="text-foreground/90 text-end tabular-nums">
                            {formatMoney(row.cogs, language)}
                          </td>
                          <td className="text-success text-end tabular-nums">
                            {formatMoney(row.gross_profit, language)}
                          </td>
                          <td className="text-foreground/90 text-end tabular-nums">{row.margin_pct.toFixed(1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}

              {/* Dead stock */}
              <h3 className="text-sm font-semibold text-foreground/90 mt-6 mb-1">{t('dead_stock')}</h3>
              <p className="text-xs text-muted-foreground mb-2">{t('dead_stock_hint')}</p>
              {margin.dead_stock.length === 0 ? (
                <p className="text-muted-foreground text-sm py-3">{t('no_dead_stock')}</p>
              ) : (
                <table className="dxr-tbl">
                  <thead>
                    <tr className="border-border hover:bg-card">
                      <th className="text-muted-foreground">{t('product_name')}</th>
                      <th className="text-muted-foreground">{t('category')}</th>
                      <th className="text-muted-foreground text-end">{t('on_hand')}</th>
                      <th className="text-muted-foreground text-end">{t('cost')}</th>
                      <th className="text-muted-foreground text-end">{t('stock_value')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {margin.dead_stock.map((row) => (
                      <tr key={row.product_id} className="border-border hover:bg-muted">
                        <td className="text-foreground font-medium">{row.name}</td>
                        <td className="text-muted-foreground text-xs">{row.category || '—'}</td>
                        <td className="text-foreground/90 text-end tabular-nums">{row.quantity}</td>
                        <td className="text-foreground/90 text-end tabular-nums">
                          {formatMoney(row.cost_price, language)}
                        </td>
                        <td className="text-foreground/90 text-end tabular-nums">
                          {formatMoney(row.stock_value, language)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* VAT / Tax Summary by rate (F-069) */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-foreground">{t('vat_summary')}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{t('vat_summary_hint')}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button onClick={handleExportVat} disabled={exportingVat || !vat}>
              {exportingVat ? <Loader2 className="h-4 w-4 animate-spin" /> : t('download_vat')}
            </Button>
            <Button
              onClick={() => handleExportPdf('vat-summary', `vat_summary_${vat?.from_date}_${vat?.to_date}`)}
              disabled={exportingPdf === 'vat-summary' || !vat}
              variant="outline"
            >
              {exportingPdf === 'vat-summary' ? <Loader2 className="h-4 w-4 animate-spin" /> : t('export_pdf')}
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
              <p className="text-danger mb-3">{t('error_loading')}</p>
              <Button variant="outline" onClick={fetchVat}>
                {t('retry')}
              </Button>
            </div>
          ) : !vat ? (
            <p className="text-muted-foreground text-center py-8">{t('no_data')}</p>
          ) : (
            <>
              {/* Net-VAT strip */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('vat_collected')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {formatMoney(vat.vat_collected, language)}
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('vat_reversed')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {formatMoney(vat.vat_reversed, language)}
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('net_vat')}</p>
                  <p className="text-lg font-bold text-success tabular-nums">
                    {formatMoney(vat.net_vat, language)}
                  </p>
                </div>
              </div>

              {/* The ZATCA VAT-return boxes */}
              <table className="dxr-tbl">
                <thead>
                  <tr className="border-border hover:bg-card">
                    <th className="text-muted-foreground">{t('tax_category')}</th>
                    <th className="text-muted-foreground text-end">{t('taxable_base')}</th>
                    <th className="text-muted-foreground text-end">{t('vat_amount')}</th>
                  </tr>
                </thead>
                <tbody>
                  {vat.buckets.map((b) => (
                    <tr key={b.key} className="border-border hover:bg-muted">
                      <td className="text-foreground font-medium">{b.label}</td>
                      <td className="text-foreground/90 text-end tabular-nums">
                        {formatMoney(b.taxable_base, language)}
                      </td>
                      <td className="text-foreground/90 text-end tabular-nums">
                        {formatMoney(b.vat_amount, language)}
                      </td>
                    </tr>
                  ))}
                  <tr className="border-border bg-muted/40">
                    <td className="text-foreground font-semibold">{t('net_vat')}</td>
                    <td className="text-foreground/90 text-end tabular-nums">
                      {formatMoney(vat.total_taxable_base, language)}
                    </td>
                    <td className="text-success text-end font-semibold tabular-nums">
                      {formatMoney(vat.net_vat, language)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </>
          )}
        </CardContent>
      </Card>

      {/* Inventory — on-hand valuation at cost + movements (F-070) */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-foreground">{t('inventory_report')}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{t('inventory_hint')}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button onClick={handleExportInventory} disabled={exportingInventory || !inventory}>
              {exportingInventory ? <Loader2 className="h-4 w-4 animate-spin" /> : t('download_inventory')}
            </Button>
            <Button
              onClick={() => handleExportPdf('inventory', `inventory_${inventory?.from_date}_${inventory?.to_date}`)}
              disabled={exportingPdf === 'inventory' || !inventory}
              variant="outline"
            >
              {exportingPdf === 'inventory' ? <Loader2 className="h-4 w-4 animate-spin" /> : t('export_pdf')}
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
              <p className="text-danger mb-3">{t('error_loading')}</p>
              <Button variant="outline" onClick={fetchInventory}>
                {t('retry')}
              </Button>
            </div>
          ) : !inventory ? (
            <p className="text-muted-foreground text-center py-8">{t('no_data')}</p>
          ) : (
            <>
              {/* Totals strip */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-5">
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('total_on_hand')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {formatNumber(inventory.total_quantity, language, 0)}
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('total_valuation')}</p>
                  <p className="text-lg font-bold text-success tabular-nums">
                    {formatMoney(inventory.total_valuation, language)}
                  </p>
                </div>
              </div>

              {/* On-hand valuation at cost, by product */}
              {inventory.by_product.length === 0 ? (
                <p className="text-muted-foreground text-sm py-3">{t('no_data')}</p>
              ) : (
                <table className="dxr-tbl">
                  <thead>
                    <tr className="border-border hover:bg-card">
                      <th className="text-muted-foreground">{t('product_name')}</th>
                      <th className="text-muted-foreground">{t('category')}</th>
                      <th className="text-muted-foreground text-end">{t('on_hand')}</th>
                      <th className="text-muted-foreground text-end">{t('cost')}</th>
                      <th className="text-muted-foreground text-end">{t('stock_value')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inventory.by_product.map((row) => (
                      <tr key={row.product_id} className="border-border hover:bg-muted">
                        <td className="text-foreground font-medium">{row.name}</td>
                        <td className="text-muted-foreground text-xs">{row.category || '—'}</td>
                        <td className="text-foreground/90 text-end tabular-nums">{row.quantity}</td>
                        <td className="text-foreground/90 text-end tabular-nums">
                          {formatMoney(row.cost_price, language)}
                        </td>
                        <td className="text-foreground/90 text-end tabular-nums">
                          {formatMoney(row.stock_value, language)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {/* Per-branch valuation */}
              {inventory.by_branch.length > 0 && (
                <div className="mt-6">
                  <h4 className="text-sm font-semibold text-foreground/90 mb-2">{t('by_branch')}</h4>
                  <table className="dxr-tbl">
                    <thead>
                      <tr className="border-border hover:bg-card">
                        <th className="text-muted-foreground">{t('branch')}</th>
                        <th className="text-muted-foreground text-end">{t('on_hand')}</th>
                        <th className="text-muted-foreground text-end">{t('stock_value')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inventory.by_branch.map((b) => (
                        <tr key={b.branch_id} className="border-border hover:bg-muted">
                          <td className="text-foreground font-medium">
                            {b.branch_name || `#${b.branch_id}`}
                          </td>
                          <td className="text-foreground/90 text-end tabular-nums">{b.quantity}</td>
                          <td className="text-foreground/90 text-end tabular-nums">
                            {formatMoney(b.stock_value, language)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Movement ledger */}
              <div className="mt-6">
                <h4 className="text-sm font-semibold text-foreground/90 mb-2">{t('movements')}</h4>
                {inventory.movements.length === 0 ? (
                  <p className="text-muted-foreground text-sm py-3">{t('no_movements')}</p>
                ) : (
                  <table className="dxr-tbl">
                    <thead>
                      <tr className="border-border hover:bg-card">
                        <th className="text-muted-foreground">{t('mv_date')}</th>
                        <th className="text-muted-foreground">{t('mv_type')}</th>
                        <th className="text-muted-foreground">{t('product_name')}</th>
                        <th className="text-muted-foreground text-end">{t('mv_qty')}</th>
                        <th className="text-muted-foreground">{t('mv_reference')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inventory.movements.map((m, idx) => (
                        <tr key={idx} className="border-border hover:bg-muted">
                          <td className="text-muted-foreground text-xs">{m.date}</td>
                          <td className="text-foreground/90 text-xs">
                            {t(`mv_${m.type}`)}
                          </td>
                          <td className="text-foreground">
                            {m.product_name || (m.product_id ? `#${m.product_id}` : '—')}
                          </td>
                          <td className="text-foreground/90 text-end tabular-nums">{m.quantity}</td>
                          <td className="text-muted-foreground text-xs">{m.reference || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
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
            <CardTitle className="text-foreground">{t('refunds_voids')}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{t('refunds_voids_hint')}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button onClick={handleExportRefundsVoids} disabled={exportingRefundsVoids || !refundsVoids}>
              {exportingRefundsVoids ? <Loader2 className="h-4 w-4 animate-spin" /> : t('download_refunds_voids')}
            </Button>
            <Button
              onClick={() => handleExportPdf('refunds-voids', `refunds_voids_${refundsVoids?.from_date}_${refundsVoids?.to_date}`)}
              disabled={exportingPdf === 'refunds-voids' || !refundsVoids}
              variant="outline"
            >
              {exportingPdf === 'refunds-voids' ? <Loader2 className="h-4 w-4 animate-spin" /> : t('export_pdf')}
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
              <p className="text-danger mb-3">{t('error_loading')}</p>
              <Button variant="outline" onClick={fetchRefundsVoids}>
                {t('retry')}
              </Button>
            </div>
          ) : !refundsVoids ? (
            <p className="text-muted-foreground text-center py-8">{t('no_data')}</p>
          ) : (
            <>
              {/* Totals strip */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-5">
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('refund_count')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {refundsVoids.refund_count}
                    <span className="text-sm text-muted-foreground ms-2">
                      {formatMoney(refundsVoids.refund_total, language)}
                    </span>
                  </p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('void_count')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">
                    {refundsVoids.void_count}
                    <span className="text-sm text-muted-foreground ms-2">
                      {formatMoney(refundsVoids.void_total, language)}
                    </span>
                  </p>
                </div>
              </div>

              {refundsVoids.rows.length === 0 ? (
                <p className="text-muted-foreground text-center py-6">{t('no_data')}</p>
              ) : (
                <table className="dxr-tbl">
                  <thead>
                    <tr className="border-border hover:bg-card">
                      <th className="text-muted-foreground">{t('rv_type')}</th>
                      <th className="text-muted-foreground">{t('invoice')}</th>
                      <th className="text-muted-foreground">{t('actor')}</th>
                      <th className="text-muted-foreground">{t('reason')}</th>
                      <th className="text-muted-foreground text-end">{t('amount')}</th>
                      <th className="text-muted-foreground">{t('when')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {refundsVoids.rows.map((r, idx) => (
                      <tr key={idx} className="border-border hover:bg-muted">
                        <td>
                          <span className={r.type === 'void' ? 'pill-danger' : 'pill-warning'}>
                            {t(`rv_${r.type}`)}
                          </span>
                        </td>
                        <td className="text-foreground text-xs">
                          {r.invoice_number || '—'}
                          {r.original_invoice ? (
                            <span className="text-muted-foreground"> ← {r.original_invoice}</span>
                          ) : null}
                        </td>
                        <td className="text-foreground/90 text-xs">{r.actor || '—'}</td>
                        <td className="text-muted-foreground text-xs">{r.reason || '—'}</td>
                        <td className="text-foreground/90 text-end tabular-nums">
                          {formatMoney(r.amount, language)}
                        </td>
                        <td className="text-muted-foreground text-xs">
                          {r.timestamp ? r.timestamp.slice(0, 10) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Discounts — actor / code / amount over a window (F-071) */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <div>
            <CardTitle className="text-foreground">{t('discounts_report')}</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">{t('discounts_hint')}</p>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button onClick={handleExportDiscounts} disabled={exportingDiscounts || !discounts}>
              {exportingDiscounts ? <Loader2 className="h-4 w-4 animate-spin" /> : t('download_discounts')}
            </Button>
            <Button
              onClick={() => handleExportPdf('discounts', `discounts_${discounts?.from_date}_${discounts?.to_date}`)}
              disabled={exportingPdf === 'discounts' || !discounts}
              variant="outline"
            >
              {exportingPdf === 'discounts' ? <Loader2 className="h-4 w-4 animate-spin" /> : t('export_pdf')}
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
              <p className="text-danger mb-3">{t('error_loading')}</p>
              <Button variant="outline" onClick={fetchDiscounts}>
                {t('retry')}
              </Button>
            </div>
          ) : !discounts ? (
            <p className="text-muted-foreground text-center py-8">{t('no_data')}</p>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-5">
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('discount_count')}</p>
                  <p className="text-lg font-bold text-foreground tabular-nums">{discounts.discount_count}</p>
                </div>
                <div className="rounded-[14px] bg-muted/40 p-3">
                  <p className="text-xs text-muted-foreground">{t('discount_total')}</p>
                  <p className="text-lg font-bold text-success tabular-nums">
                    {formatMoney(discounts.discount_total, language)}
                  </p>
                </div>
              </div>

              {discounts.rows.length === 0 ? (
                <p className="text-muted-foreground text-center py-6">{t('no_data')}</p>
              ) : (
                <table className="dxr-tbl">
                  <thead>
                    <tr className="border-border hover:bg-card">
                      <th className="text-muted-foreground">{t('invoice')}</th>
                      <th className="text-muted-foreground">{t('actor')}</th>
                      <th className="text-muted-foreground">{t('code')}</th>
                      <th className="text-muted-foreground text-end">{t('amount')}</th>
                      <th className="text-muted-foreground">{t('when')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {discounts.rows.map((r, idx) => (
                      <tr key={idx} className="border-border hover:bg-muted">
                        <td className="text-foreground text-xs">{r.invoice_number || '—'}</td>
                        <td className="text-foreground/90 text-xs">{r.actor || '—'}</td>
                        <td className="text-muted-foreground text-xs">
                          {r.is_manual ? (
                            <span className="italic text-muted-foreground">{t('manual')}</span>
                          ) : (
                            r.code
                          )}
                        </td>
                        <td className="text-foreground/90 text-end tabular-nums">
                          {formatMoney(r.discount_amount, language)}
                        </td>
                        <td className="text-muted-foreground text-xs">
                          {r.timestamp ? r.timestamp.slice(0, 10) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Top Products */}
      <Card className="bg-card border-border">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle className="text-foreground">{t('top_products')}</CardTitle>
          <Button
            onClick={() => handleExportPdf('top-products', 'top_products')}
            disabled={exportingPdf === 'top-products' || topProducts.length === 0}
            variant="outline"
            className="shrink-0"
          >
            {exportingPdf === 'top-products' ? <Loader2 className="h-4 w-4 animate-spin" /> : t('export_pdf')}
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
            <p className="text-danger text-center py-8">{t('error_loading')}</p>
          ) : topProducts.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">{t('no_data')}</p>
          ) : (
            <table className="dxr-tbl">
              <thead>
                <tr className="border-border hover:bg-card">
                  <th className="text-muted-foreground">{t('rank')}</th>
                  <th className="text-muted-foreground">{t('product_name')}</th>
                  <th className="text-muted-foreground text-end">{t('qty_sold')}</th>
                  <th className="text-muted-foreground text-end">{t('revenue')}</th>
                </tr>
              </thead>
              <tbody>
                {topProducts.map((product, idx) => (
                  <tr
                    key={product.product_id}
                    className="border-border hover:bg-muted"
                  >
                    <td>{rankBadge(idx + 1)}</td>
                    <td className="text-foreground font-medium">{product.name}</td>
                    <td className="text-foreground/90 text-end tabular-nums">
                      {product.total_quantity_sold}
                    </td>
                    <td className="text-foreground/90 text-end tabular-nums">
                      {formatMoney(product.total_revenue, language)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}