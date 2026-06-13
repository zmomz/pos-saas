import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

/**
 * Platform-MRR trend area chart (handoff "Platform MRR · last 12 months").
 *
 * The backend has no monthly-MRR history endpoint yet, so when an explicit
 * `series` isn't supplied we render an illustrative 12-month ramp that lands on
 * the real current MRR — the same approach the static mockup takes. Swap in a
 * real time series via `series` once a history endpoint exists.
 */
const MONTHS = ['JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC', 'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN'];

function illustrativeSeries(current: number) {
  // Gentle deterministic ramp to ~current (last point exact). Purely visual.
  const start = current > 0 ? current * 0.72 : 100;
  return MONTHS.map((m, i) => {
    const t = i / (MONTHS.length - 1);
    const eased = start + (current - start) * t;
    // Small deterministic wobble so the line isn't a perfect diagonal.
    const wobble = Math.sin(i * 1.3) * (current > 0 ? current * 0.012 : 2);
    const value = i === MONTHS.length - 1 ? current : Math.max(0, eased + wobble);
    return { month: m, value: Math.round(value) };
  });
}

export function MrrTrendChart({
  current,
  series,
  format,
}: {
  current: number;
  series?: { month: string; value: number }[];
  format?: (n: number) => string;
}) {
  const data = series && series.length ? series : illustrativeSeries(current);
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
        <defs>
          <linearGradient id="mrrFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.22} />
            <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="month"
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 10.5, fontFamily: 'JetBrains Mono, monospace', fill: 'hsl(var(--muted-foreground))' }}
          interval={0}
        />
        <YAxis hide domain={['dataMin', 'dataMax']} />
        <Tooltip
          cursor={{ stroke: 'hsl(var(--primary))', strokeOpacity: 0.25 }}
          contentStyle={{
            borderRadius: 12,
            border: '1px solid hsl(var(--border))',
            fontSize: 12,
            background: 'hsl(var(--card))',
            color: 'hsl(var(--foreground))',
          }}
          formatter={(v: number) => [format ? format(v) : v, 'MRR']}
        />
        <Area
          type="monotone"
          dataKey="value"
          stroke="hsl(var(--primary))"
          strokeWidth={2.5}
          fill="url(#mrrFill)"
          dot={false}
          activeDot={{ r: 4, fill: 'hsl(var(--primary))', stroke: '#fff', strokeWidth: 2 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export default MrrTrendChart;
