import { useMemo, useRef, useState, useId } from 'react';

interface SpotChartProps {
  /** keyed series, e.g. { '12M': number[], '6M': number[] } */
  series: Record<string, number[]>;
  labels: Record<string, string[]>;
  xticks?: Record<string, string[]>;
  ranges: string[];
  initial?: string;
  format: (n: number) => string;
  height?: number;
  /** line colour (defaults to bright cyan for ink tiles) */
  stroke?: string;
  /** segmented control styling for dark spotlight tiles */
  ink?: boolean;
}

function buildPath(vals: number[], W: number, H: number, pad: number) {
  const max = Math.max(...vals) * 1.08;
  const min = Math.min(...vals) * 0.96;
  const span = max - min || 1;
  const innerW = W - pad * 2;
  const innerH = H - pad * 2;
  const pts = vals.map((v, i) => {
    const x = pad + (innerW * i) / (vals.length - 1 || 1);
    const y = pad + innerH * (1 - (v - min) / span);
    return [x, y] as [number, number];
  });
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const cx = (x0 + x1) / 2;
    d += ` C${cx},${y0} ${cx},${y1} ${x1},${y1}`;
  }
  return { d, pts };
}

/**
 * Interactive area+line chart. Hovering shows a crosshair + value tooltip;
 * the segmented control re-draws the series. Pure SVG, no chart lib.
 */
export default function SpotChart({
  series,
  labels,
  xticks,
  ranges,
  initial,
  format,
  height = 170,
  stroke = 'var(--cyan)',
  ink = true,
}: SpotChartProps) {
  const W = 640;
  const H = height;
  const pad = 14;
  const [range, setRange] = useState(initial || ranges[0]);
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const gid = useId();

  const vals = series[range] || [];
  const { d, pts } = useMemo(() => buildPath(vals, W, H, pad), [vals, H]);
  const areaD =
    pts.length > 0
      ? `${d} L${pts[pts.length - 1][0]},${H} L${pts[0][0]},${H} Z`
      : '';

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    let idx = 0;
    let best = Infinity;
    pts.forEach((p, i) => {
      const dd = Math.abs(p[0] - x);
      if (dd < best) {
        best = dd;
        idx = i;
      }
    });
    setHover(idx);
  }

  const hp = hover != null ? pts[hover] : null;
  const ticks = xticks?.[range];
  const segCls = ink ? 'dxr-seg dxr-seg-ink' : 'dxr-seg';

  return (
    <div className="mt-3">
      <div className="mb-1 flex justify-end">
        <div className={segCls}>
          {ranges.map((rk) => (
            <button
              key={rk}
              data-active={rk === range}
              onClick={() => {
                setRange(rk);
                setHover(null);
              }}
            >
              {rk}
            </button>
          ))}
        </div>
      </div>

      {/* overflow-x-clip: the hover tooltip is translated -50% on x, so at the
          chart edges it would otherwise overflow and trigger a phantom scrollbar. */}
      <div className="relative overflow-x-clip">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          style={{ width: '100%', height: 'auto', display: 'block', cursor: 'crosshair' }}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        >
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor={stroke} stopOpacity="0.28" />
              <stop offset="1" stopColor={stroke} stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0.28, 0.55, 0.82].map((f, i) => (
            <line
              key={i}
              x1={pad}
              x2={W - pad}
              y1={H * f}
              y2={H * f}
              stroke={ink ? 'rgba(255,255,255,0.10)' : 'hsl(var(--border))'}
              strokeWidth={1}
            />
          ))}
          {areaD && <path d={areaD} fill={`url(#${gid})`} />}
          {d && (
            <path
              d={d}
              fill="none"
              stroke={stroke}
              strokeWidth={2.6}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}
          {pts.length > 0 && (
            <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r={4.5} fill={stroke} stroke="#fff" strokeWidth={2} />
          )}
          {hp && (
            <>
              <line x1={hp[0]} x2={hp[0]} y1={pad} y2={H - pad} stroke={stroke} strokeWidth={1} strokeDasharray="3 3" opacity={0.7} />
              <circle cx={hp[0]} cy={hp[1]} r={4} fill={stroke} stroke="#fff" strokeWidth={2} />
            </>
          )}
        </svg>

        {hp && hover != null && (
          <div
            className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-[118%] whitespace-nowrap rounded-[10px] border border-border bg-popover px-2.5 py-1.5 text-popover-foreground shadow-md"
            style={{ left: `${(hp[0] / W) * 100}%`, top: `${(hp[1] / H) * 100}%` }}
          >
            <div className="font-mono text-[10.5px] text-muted-foreground">
              {labels[range]?.[hover] || ''}
            </div>
            <div className="text-[12px] font-extrabold tabular-nums">{format(vals[hover])}</div>
          </div>
        )}
      </div>

      {ticks && (
        <div className={`mt-2 flex justify-between font-mono text-[10px] ${ink ? 'text-white/55' : 'text-muted-foreground'}`}>
          {ticks.map((t, i) => (
            <span key={i}>{t}</span>
          ))}
        </div>
      )}
    </div>
  );
}
