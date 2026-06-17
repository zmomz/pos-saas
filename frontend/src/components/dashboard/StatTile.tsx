import type { ElementType, ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * Handoff-faithful KPI tile (design_handoff_cloud_pos · dashboard.css `.stat`).
 *
 * Layout matches the mockup exactly: a top row with the muted label on the start
 * side and a tinted icon swatch on the end, a large 28px tabular value, and an
 * optional footer line (delta, progress bar, or status dot). Used by the master
 * and agent dashboards so their stat rows are pixel-aligned with the handoff.
 */
export type TileTone = 'brand' | 'success' | 'violet' | 'sky' | 'gold' | 'warning';

const TONES: Record<TileTone, string> = {
  brand: 'bg-brand-50 text-brand-700',
  success: 'bg-success/10 text-success',
  violet: 'bg-violet/10 text-violet',
  sky: 'bg-sky/10 text-sky',
  gold: 'bg-gold-50 text-gold-600',
  warning: 'bg-warning/10 text-warning',
};

interface StatTileProps {
  icon: ElementType;
  label: ReactNode;
  value: ReactNode;
  /** Rendered smaller + muted next to the value (e.g. " / 18 slots filled"). */
  valueSmall?: ReactNode;
  tone?: TileTone;
  /** Delta / progress bar / status line under the value. */
  footer?: ReactNode;
  className?: string;
}

export default function StatTile({
  icon: Icon,
  label,
  value,
  valueSmall,
  tone = 'brand',
  footer,
  className,
}: StatTileProps) {
  return (
    <div
      className={cn(
        'flex flex-col gap-3.5 rounded-[20px] border border-border bg-card p-[18px] shadow-sm transition-transform duration-200 hover:-translate-y-0.5',
        className
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-medium text-muted-foreground">{label}</span>
        <span className={cn('flex h-[42px] w-[42px] items-center justify-center rounded-[11px]', TONES[tone])}>
          <Icon className="h-[21px] w-[21px]" />
        </span>
      </div>
      <div className="text-[28px] font-extrabold leading-none tracking-tight tabular-nums text-foreground">
        {value}
        {valueSmall ? <small className="text-[15px] font-semibold text-muted-foreground"> {valueSmall}</small> : null}
      </div>
      {footer ? <div className="text-[12.5px] font-semibold">{footer}</div> : null}
    </div>
  );
}

/** Up/down delta line (green / red) as in the handoff stat footer. */
export function StatDelta({ dir = 'up', children }: { dir?: 'up' | 'down'; children: ReactNode }) {
  return (
    <span className={cn('inline-flex items-center gap-1', dir === 'up' ? 'text-success' : 'text-danger')}>
      {children}
    </span>
  );
}

/** Thin progress bar (brand fill on a brand-100 track) used in stat footers. */
export function StatBar({ pct }: { pct: number }) {
  return (
    <div className="h-[7px] overflow-hidden rounded bg-brand-100">
      <i className="block h-full rounded bg-brand" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  );
}
