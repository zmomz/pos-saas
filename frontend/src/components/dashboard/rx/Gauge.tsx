import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface GaugeProps {
  /** 0–100 */
  pct: number;
  size?: number;
  stroke?: number;
  center?: ReactNode;
  caption?: ReactNode;
  className?: string;
}

/**
 * Radial progress gauge with an animated brand→cyan sweep. Used for ratios like
 * slot-fill, system health, active subscriptions and the POS daily goal.
 */
export default function Gauge({
  pct,
  size = 118,
  stroke = 11,
  center,
  caption,
  className,
}: GaugeProps) {
  const r = (size - stroke) / 2 - 2;
  const C = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, pct));
  const [offset, setOffset] = useState(C);
  const gid = useId();
  const ref = useRef<number>();

  useEffect(() => {
    ref.current = requestAnimationFrame(() =>
      requestAnimationFrame(() => setOffset(C * (1 - clamped / 100)))
    );
    return () => {
      if (ref.current) cancelAnimationFrame(ref.current);
    };
  }, [clamped, C]);

  return (
    <div
      className={cn('relative mx-auto', className)}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="hsl(var(--primary))" />
            <stop offset="1" stopColor="#36c5e0" />
          </linearGradient>
        </defs>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="hsl(var(--muted))"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`url(#${gid})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={C}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 1.1s cubic-bezier(.22,1,.36,1)' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-2xl font-extrabold tracking-tight tabular-nums">{center}</div>
        {caption ? (
          <div className="mt-0.5 text-[10.5px] font-semibold text-muted-foreground">{caption}</div>
        ) : null}
      </div>
    </div>
  );
}
