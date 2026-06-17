import type { ReactNode } from 'react';

interface PageHeadingProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** optional leading icon/swatch, rendered beside (not inside) the title */
  icon?: ReactNode;
  /** right-aligned actions (buttons, filters) */
  children?: ReactNode;
}

/**
 * Shared command-bar style page heading used across the redesigned dashboards
 * and back-office pages. The icon is kept OUTSIDE the <h1> so the title stays a
 * text-only node (keeps getByText/findByText assertions working).
 */
export default function PageHeading({ title, subtitle, icon, children }: PageHeadingProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex min-w-0 items-center gap-2.5">
        {icon}
        <div className="min-w-0">
          <h1 className="text-[21px] font-extrabold tracking-tight">{title}</h1>
          {subtitle ? <p className="text-[13px] text-muted-foreground">{subtitle}</p> : null}
        </div>
      </div>
      {children ? (
        <>
          <div className="flex-1" />
          <div className="flex flex-wrap items-center gap-2.5">{children}</div>
        </>
      ) : null}
    </div>
  );
}
