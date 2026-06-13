import type { ReactNode } from 'react';
import { Users, Package, Bell, Shield, DollarSign, LogIn, Pencil, Trash2, ScrollText } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface ActivityItem {
  id: string;
  action: string;
  text: ReactNode;
  at?: string;
}

// Map an audit action to a tinted icon, matching the handoff activity swatches.
const ACTION_ICON: Record<string, { icon: typeof Users; tone: string }> = {
  create: { icon: Users, tone: 'bg-success/10 text-success' },
  update: { icon: Pencil, tone: 'bg-brand-50 text-brand-700' },
  delete: { icon: Trash2, tone: 'bg-danger/10 text-danger' },
  login: { icon: LogIn, tone: 'bg-sky/10 text-sky' },
  logout: { icon: LogIn, tone: 'bg-muted text-muted-foreground' },
  sale: { icon: DollarSign, tone: 'bg-violet/10 text-violet' },
  export: { icon: ScrollText, tone: 'bg-gold-50 text-gold-600' },
  suspend: { icon: Shield, tone: 'bg-danger/10 text-danger' },
  package: { icon: Package, tone: 'bg-brand-50 text-brand-700' },
  notify: { icon: Bell, tone: 'bg-warning/10 text-warning' },
};

function iconFor(action: string) {
  return ACTION_ICON[action] || { icon: ScrollText, tone: 'bg-muted text-muted-foreground' };
}

// Compact relative time ("12 MIN AGO", "3 HOURS AGO", "YESTERDAY").
export function relativeTime(iso?: string): string {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const diff = Math.max(0, Date.now() - then);
  const min = Math.round(diff / 60000);
  if (min < 1) return 'JUST NOW';
  if (min < 60) return `${min} MIN AGO`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr} HOUR${hr > 1 ? 'S' : ''} AGO`;
  const day = Math.round(hr / 24);
  if (day === 1) return 'YESTERDAY';
  if (day < 7) return `${day} DAYS AGO`;
  return new Date(iso).toLocaleDateString().toUpperCase();
}

/** Dashed-divided activity list driven by audit/event rows. */
export function ActivityFeed({ items, empty }: { items: ActivityItem[]; empty?: ReactNode }) {
  if (!items.length) {
    return <p className="py-6 text-center text-sm text-muted-foreground">{empty || 'No recent activity.'}</p>;
  }
  return (
    <div>
      {items.map((it) => {
        const { icon: Icon, tone } = iconFor(it.action);
        return (
          <div
            key={it.id}
            className="flex gap-3.5 border-b border-dashed border-border py-3.5 last:border-b-0"
          >
            <span className={cn('flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[9px]', tone)}>
              <Icon className="h-[17px] w-[17px]" />
            </span>
            <div className="min-w-0">
              <p className="text-[13.5px] leading-snug text-foreground">{it.text}</p>
              <div className="mt-0.5 font-mono text-[11.5px] text-muted-foreground">{relativeTime(it.at)}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default ActivityFeed;
