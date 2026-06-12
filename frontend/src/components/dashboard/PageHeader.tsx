import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Right-aligned controls (buttons, language switcher, etc.). */
  actions?: ReactNode;
  className?: string;
}

/**
 * Consistent page title block shown at the top of each dashboard. A thin brand
 * accent bar to the start of the title ties the four surfaces together.
 */
export function PageHeader({ title, subtitle, actions, className }: PageHeaderProps) {
  return (
    <div className={cn('flex flex-wrap items-end justify-between gap-4', className)}>
      <div className="flex items-center gap-3">
        <span className="h-9 w-1.5 rounded-full brand-gradient" aria-hidden />
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">{title}</h1>
          {subtitle ? <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p> : null}
        </div>
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

interface SectionHeadingProps {
  title: ReactNode;
  actions?: ReactNode;
  className?: string;
}

/** Lighter heading for sections within a dashboard. */
export function SectionHeading({ title, actions, className }: SectionHeadingProps) {
  return (
    <div className={cn('mb-4 flex flex-wrap items-center justify-between gap-3', className)}>
      <h2 className="text-lg font-semibold tracking-tight text-foreground">{title}</h2>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export default PageHeader;
