import type { ElementType, ReactNode } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export type StatTone = 'brand' | 'emerald' | 'violet' | 'amber' | 'sky' | 'rose';

/**
 * Shared KPI card used by every dashboard (master / agent / client) so the
 * top-of-page stat rows are visually identical across roles. The `tone` only
 * tints the icon chip + a faint corner glow — the card surface itself stays the
 * neutral themed `bg-card`, which keeps a row of mixed tones looking cohesive.
 */
const TONES: Record<StatTone, { chip: string; icon: string; glow: string }> = {
  brand: {
    chip: 'bg-brand-500/15 dark:bg-brand-500/20',
    icon: 'text-brand-600 dark:text-brand-300',
    glow: 'from-brand-500/10',
  },
  emerald: {
    chip: 'bg-emerald-500/15 dark:bg-emerald-500/20',
    icon: 'text-emerald-600 dark:text-emerald-300',
    glow: 'from-emerald-500/10',
  },
  violet: {
    chip: 'bg-violet-500/15 dark:bg-violet-500/20',
    icon: 'text-violet-600 dark:text-violet-300',
    glow: 'from-violet-500/10',
  },
  amber: {
    chip: 'bg-amber-500/15 dark:bg-amber-500/20',
    icon: 'text-amber-600 dark:text-amber-300',
    glow: 'from-amber-500/10',
  },
  sky: {
    chip: 'bg-sky-500/15 dark:bg-sky-500/20',
    icon: 'text-sky-600 dark:text-sky-300',
    glow: 'from-sky-500/10',
  },
  rose: {
    chip: 'bg-rose-500/15 dark:bg-rose-500/20',
    icon: 'text-rose-600 dark:text-rose-300',
    glow: 'from-rose-500/10',
  },
};

interface StatCardProps {
  icon: ElementType;
  label: string;
  value: ReactNode;
  tone?: StatTone;
  /** Optional sub-line, e.g. a delta like "+18% vs last month". */
  hint?: ReactNode;
  className?: string;
}

export default function StatCard({
  icon: Icon,
  label,
  value,
  tone = 'brand',
  hint,
  className,
}: StatCardProps) {
  const t = TONES[tone];
  return (
    <Card
      className={cn(
        'relative overflow-hidden rounded-2xl border-border/70 shadow-card transition-all duration-300 hover:-translate-y-0.5 hover:shadow-brand',
        className
      )}
    >
      {/* Faint tonal glow in the trailing corner. */}
      <div
        className={cn(
          'pointer-events-none absolute -top-10 end-0 h-28 w-28 rounded-full bg-gradient-to-bl to-transparent blur-2xl',
          t.glow
        )}
      />
      <CardContent className="relative flex items-center gap-4 p-5">
        <div className={cn('flex h-12 w-12 shrink-0 items-center justify-center rounded-xl', t.chip)}>
          <Icon className={cn('h-6 w-6', t.icon)} />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-muted-foreground">{label}</p>
          <p className="mt-0.5 text-2xl font-bold tracking-tight text-foreground">{value}</p>
          {hint ? <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p> : null}
        </div>
      </CardContent>
    </Card>
  );
}
