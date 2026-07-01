import { useState, useEffect, useCallback } from 'react';
import { TrendingUp, TrendingDown, Minus, PackageSearch, Tags } from 'lucide-react';
import { useLanguage, translate } from '@/lib/i18n';
import { formatMoney, formatNumber } from '@/lib/format';
import {
  getSalesForecast,
  getInventoryForecast,
  getDynamicPricing,
  type SalesForecastMethod,
  type SalesForecastResponse,
  type InventoryForecastResponse,
  type DynamicPricingResponse,
} from '@/lib/api';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * Forecast Insights (#228, M9·AI) — the frontend surface for the AI forecasting
 * epic. It reads three tenant-scoped, server-aggregated /reports/* endpoints and
 * turns them into three operator-facing panels:
 *
 *   • Sales Forecast   — a moving-average revenue projection over the horizon.
 *   • Smart Reorder    — demand-driven products that will stock out, with the
 *                        quantity that covers exactly the projected shortfall.
 *   • Dynamic Pricing  — markup (scarce) / markdown (overstock) suggestions with
 *                        the current → suggested price.
 *
 * Each panel owns loading + error state so a failed fetch surfaces a real retry
 * error distinct from an empty forecast (UX-02), mirroring ReportsAnalytics.
 */
export default function ForecastInsights() {
  const { language } = useLanguage();
  const tr = useCallback((key: string): string => translate(language, key), [language]);

  const [sales, setSales] = useState<SalesForecastResponse | null>(null);
  const [salesMethod, setSalesMethod] = useState<SalesForecastMethod>('moving_average');
  const [inventory, setInventory] = useState<InventoryForecastResponse | null>(null);
  const [pricing, setPricing] = useState<DynamicPricingResponse | null>(null);
  const [loadingSales, setLoadingSales] = useState(true);
  const [loadingInventory, setLoadingInventory] = useState(true);
  const [loadingPricing, setLoadingPricing] = useState(true);
  const [salesError, setSalesError] = useState(false);
  const [inventoryError, setInventoryError] = useState(false);
  const [pricingError, setPricingError] = useState(false);

  // The sales panel re-fetches whenever the operator switches forecast model, so
  // it is keyed on salesMethod; the demand/pricing panels load once on mount.
  useEffect(() => {
    (async () => {
      setLoadingSales(true);
      setSalesError(false);
      try {
        setSales((await getSalesForecast(30, 7, salesMethod)) || null);
      } catch {
        setSalesError(true);
        setSales(null);
      } finally {
        setLoadingSales(false);
      }
    })();
  }, [salesMethod]);

  useEffect(() => {
    (async () => {
      setLoadingInventory(true);
      setInventoryError(false);
      try {
        setInventory((await getInventoryForecast()) || null);
      } catch {
        setInventoryError(true);
        setInventory(null);
      } finally {
        setLoadingInventory(false);
      }
    })();
    (async () => {
      setLoadingPricing(true);
      setPricingError(false);
      try {
        setPricing((await getDynamicPricing()) || null);
      } catch {
        setPricingError(true);
        setPricing(null);
      } finally {
        setLoadingPricing(false);
      }
    })();
  }, []);

  const errorLine = <p className="text-sm text-danger">{tr('error_loading')}</p>;
  const skeleton = (
    <div className="space-y-2">
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
    </div>
  );

  return (
    <section className="space-y-6" aria-label={tr('forecast_insights')}>
      <h2 className="text-lg font-semibold text-foreground">{tr('forecast_insights')}</h2>

      {/* Sales revenue projection */}
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-brand-600" aria-hidden="true" />
            {tr('sales_forecast')}
          </CardTitle>
          {/* Model toggle: switch between the flat moving-average baseline and the
              direction-aware linear-trend projection served by the same endpoint. */}
          <div
            role="group"
            aria-label={tr('forecast_method')}
            className="inline-flex overflow-hidden rounded-md border border-border"
          >
            {(
              [
                ['moving_average', 'method_moving_average'],
                ['linear_trend', 'method_linear_trend'],
              ] as const
            ).map(([value, label]) => {
              const active = salesMethod === value;
              return (
                <button
                  key={value}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setSalesMethod(value)}
                  className={cn(
                    'px-3 py-1.5 text-xs font-medium transition-colors',
                    active
                      ? 'bg-brand-600 text-white'
                      : 'bg-transparent text-muted-foreground hover:bg-muted'
                  )}
                >
                  {tr(label)}
                </button>
              );
            })}
          </div>
        </CardHeader>
        <CardContent>
          {loadingSales ? (
            skeleton
          ) : salesError ? (
            errorLine
          ) : sales ? (
            <div className="flex flex-wrap gap-8">
              <div>
                <p className="text-xs uppercase tracking-wide text-muted-foreground">
                  {tr('avg_daily_sales')}
                </p>
                <p className="text-2xl font-bold tabular-nums text-foreground">
                  {formatMoney(sales.avg_daily_sales, language)}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-muted-foreground">
                  {tr('projected_demand')}
                </p>
                <p className="text-2xl font-bold tabular-nums text-foreground">
                  {formatMoney(sales.avg_daily_sales * sales.horizon_days, language)}
                </p>
                <p className="text-xs text-muted-foreground">
                  {tr('forecast_method')}: {sales.method}
                </p>
              </div>
              {/* Direction the linear model projects — only meaningful when a
                  trend model is selected (moving_average is flat, trend 0). */}
              {sales.method === 'linear_trend' && (
                <div data-testid="sales-trend">
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">
                    {tr('daily_trend')}
                  </p>
                  {(() => {
                    const t = sales.trend_per_day;
                    const rising = t > 0;
                    const falling = t < 0;
                    const Icon = rising ? TrendingUp : falling ? TrendingDown : Minus;
                    const dir = rising
                      ? tr('trend_rising')
                      : falling
                        ? tr('trend_falling')
                        : tr('trend_flat');
                    const tone = rising
                      ? 'text-success'
                      : falling
                        ? 'text-danger'
                        : 'text-muted-foreground';
                    return (
                      <p className={cn('flex items-center gap-1.5 text-2xl font-bold tabular-nums', tone)}>
                        <Icon className="h-5 w-5" aria-hidden="true" />
                        <span>{formatMoney(Math.abs(t), language)}</span>
                        <span className="text-sm font-medium">{dir}</span>
                      </p>
                    );
                  })()}
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{tr('no_data')}</p>
          )}
        </CardContent>
      </Card>

      {/* Smart reorder */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PackageSearch className="h-5 w-5 text-warning" aria-hidden="true" />
            {tr('smart_reorder')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loadingInventory ? (
            skeleton
          ) : inventoryError ? (
            errorLine
          ) : inventory && inventory.items.length > 0 ? (
            <div className="w-full overflow-x-auto">
              <table className="dxr-tbl">
                <thead>
                  <tr>
                    <th>{tr('product_name')}</th>
                    <th className="text-end">{tr('on_hand')}</th>
                    <th className="text-end">{tr('projected_demand')}</th>
                    <th className="text-end">{tr('days_of_cover')}</th>
                    <th className="text-end">{tr('suggested_reorder')}</th>
                  </tr>
                </thead>
                <tbody>
                  {inventory.items.map((it) => (
                    <tr key={it.product_id}>
                      <td className="text-foreground">{it.name}</td>
                      <td className="text-end tabular-nums">{formatNumber(it.on_hand, language, 0)}</td>
                      <td className="text-end tabular-nums">
                        {formatNumber(it.projected_demand, language, 0)}
                      </td>
                      <td className="text-end tabular-nums">
                        {it.days_of_cover == null ? '—' : formatNumber(it.days_of_cover, language, 1)}
                      </td>
                      <td className="text-end font-semibold tabular-nums text-warning">
                        {formatNumber(it.suggested_reorder_quantity, language, 0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{tr('no_reorder_needed')}</p>
          )}
        </CardContent>
      </Card>

      {/* Dynamic pricing */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Tags className="h-5 w-5 text-violet" aria-hidden="true" />
            {tr('dynamic_pricing')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loadingPricing ? (
            skeleton
          ) : pricingError ? (
            errorLine
          ) : pricing && pricing.items.length > 0 ? (
            <div className="w-full overflow-x-auto">
              <table className="dxr-tbl">
                <thead>
                  <tr>
                    <th>{tr('product_name')}</th>
                    <th>{tr('price_signal')}</th>
                    <th className="text-end">{tr('current_price')}</th>
                    <th className="text-end">{tr('suggested_price')}</th>
                  </tr>
                </thead>
                <tbody>
                  {pricing.items.map((it) => (
                    <tr key={it.product_id}>
                      <td className="text-foreground">{it.name}</td>
                      <td>
                        <span
                          className={
                            it.signal === 'markup'
                              ? 'text-success font-medium'
                              : 'text-danger font-medium'
                          }
                        >
                          {it.signal === 'markup' ? tr('signal_markup') : tr('signal_markdown')}
                        </span>
                      </td>
                      <td className="text-end tabular-nums text-muted-foreground">
                        {formatMoney(it.current_price, language)}
                      </td>
                      <td className="text-end font-semibold tabular-nums text-foreground">
                        {formatMoney(it.suggested_price, language)}
                        {it.margin_floored ? (
                          <span
                            className="ms-2 rounded bg-warning/15 px-1.5 py-0.5 text-xs font-medium text-warning"
                            title={tr('margin_at_cost')}
                          >
                            {tr('margin_at_cost')}
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{tr('no_price_changes')}</p>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
