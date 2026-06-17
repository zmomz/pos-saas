import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

interface BarProps {
  /** 0–100 */
  pct: number;
  className?: string;
  barClassName?: string;
}

/** Thin progress bar whose fill animates in on mount. */
export default function Bar({ pct, className, barClassName }: BarProps) {
  const [w, setW] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() =>
      requestAnimationFrame(() => setW(Math.max(0, Math.min(100, pct))))
    );
    return () => cancelAnimationFrame(id);
  }, [pct]);
  return (
    <div className={cn('h-2 overflow-hidden rounded-full bg-brand-100 dark:bg-white/10', className)}>
      <span
        className={cn(
          'block h-full rounded-full bg-gradient-to-r from-brand to-brand-600 transition-[width] duration-1000 ease-out',
          barClassName
        )}
        style={{ width: `${w}%` }}
      />
    </div>
  );
}
