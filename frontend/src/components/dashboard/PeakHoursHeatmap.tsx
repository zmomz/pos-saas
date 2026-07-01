import { useState, useEffect, useMemo, useCallback } from 'react';
import { Clock } from 'lucide-react';
import { useLanguage, translate } from '@/lib/i18n';
import { getPeakHours, type PeakHoursResponse } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * Peak-Hours Heatmap (#229, M9·Analytics) — the frontend surface for the
 * peak-hours slice of the advanced-analytics epic. It reads the tenant-scoped,
 * server-aggregated /reports/peak-hours endpoint (completed sales bucketed into a
 * day-of-week × hour grid) and turns it into a heatmap plus a "busiest time"
 * callout that tells a merchant when to staff up.
 *
 * Weekday names are localised via Intl (0=Sunday), so no per-day i18n key is
 * needed. The panel owns loading + error state so a failed fetch surfaces a real
 * retry error distinct from an empty heatmap (UX-02), mirroring ForecastInsights.
 */
const HOURS = Array.from({ length: 24 }, (_, h) => h);
const DAYS = [0, 1, 2, 3, 4, 5, 6];

// dow 0=Sunday..6=Saturday. Jan 1 2023 (UTC) was a Sunday, so it anchors the map.
function weekdayLabel(dow: number, locale: string): string {
  const date = new Date(Date.UTC(2023, 0, 1 + dow));
  return new Intl.DateTimeFormat(locale, { weekday: 'short', timeZone: 'UTC' }).format(date);
}

const pad = (n: number) => String(n).padStart(2, '0');

export default function PeakHoursHeatmap() {
  const { language } = useLanguage();
  const tr = useCallback((key: string): string => translate(language, key), [language]);

  const [data, setData] = useState<PeakHoursResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(false);
      try {
        setData((await getPeakHours()) || null);
      } catch {
        setError(true);
        setData(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Sparse (dow,hour)→cell lookup and the max count (for shading intensity).
  const { byCell, maxCount } = useMemo(() => {
    const byCell = new Map<string, PeakHoursResponse['cells'][number]>();
    let maxCount = 0;
    for (const c of data?.cells ?? []) {
      byCell.set(`${c.day_of_week}-${c.hour}`, c);
      if (c.order_count > maxCount) maxCount = c.order_count;
    }
    return { byCell, maxCount };
  }, [data]);

  const cellName = (dow: number, hour: number, count: number) =>
    `${weekdayLabel(dow, language)} ${pad(hour)}:00 — ${count} ${tr('orders')}`;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="h-5 w-5 text-brand-600" aria-hidden="true" />
          {tr('peak_hours')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : error ? (
          <p className="text-sm text-danger">{tr('error_loading')}</p>
        ) : data && data.total_orders > 0 ? (
          <div className="space-y-4">
            {data.busiest && (
              <p data-testid="busiest-time" className="text-sm text-muted-foreground">
                {tr('busiest_time')}:{' '}
                <span className="font-semibold text-foreground">
                  {weekdayLabel(data.busiest.day_of_week, language)} {pad(data.busiest.hour)}:00
                </span>{' '}
                — {data.busiest.order_count} {tr('orders')}
              </p>
            )}
            <div className="w-full overflow-x-auto">
              <table className="border-separate border-spacing-0.5">
                <thead>
                  <tr>
                    <th className="w-10" />
                    {HOURS.map((h) => (
                      <th
                        key={h}
                        className="px-0.5 text-[10px] font-normal text-muted-foreground tabular-nums"
                      >
                        {pad(h)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {DAYS.map((dow) => (
                    <tr key={dow}>
                      <td className="pe-1 text-xs font-medium text-muted-foreground whitespace-nowrap">
                        {weekdayLabel(dow, language)}
                      </td>
                      {HOURS.map((h) => {
                        const cell = byCell.get(`${dow}-${h}`);
                        const intensity = cell && maxCount > 0 ? cell.order_count / maxCount : 0;
                        return (
                          <td key={h} className="p-0">
                            <div
                              aria-label={cell ? cellName(dow, h, cell.order_count) : undefined}
                              aria-hidden={cell ? undefined : true}
                              title={cell ? cellName(dow, h, cell.order_count) : undefined}
                              className={cn(
                                'h-4 w-4 rounded-sm',
                                cell ? 'bg-brand-600' : 'bg-muted'
                              )}
                              style={cell ? { opacity: 0.25 + 0.75 * intensity } : undefined}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{tr('no_data')}</p>
        )}
      </CardContent>
    </Card>
  );
}
