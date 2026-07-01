import { useEffect, useRef, useState } from 'react';
import { formatMoney } from '@/lib/format';
import type { Language } from '@/lib/i18n';

interface CountUpProps {
  value: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  duration?: number;
  className?: string;
  /**
   * ISSUE-208: render the animated value through `formatMoney` (trailing riyal
   * sign, locale-aware) instead of a bespoke `prefix="⃁ "`. Prefer this so
   * currency has a single formatting path across the app.
   */
  money?: boolean;
  lang?: Language;
}

const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

/**
 * Animated number that counts up from 0 to `value` on mount / value change.
 * Respects prefers-reduced-motion (renders the final value immediately).
 */
export default function CountUp({
  value,
  prefix = '',
  suffix = '',
  decimals = 0,
  duration = 1100,
  className,
  money = false,
  lang = 'en',
}: CountUpProps) {
  const [display, setDisplay] = useState(value);
  const rafRef = useRef<number>();

  useEffect(() => {
    let reduce = false;
    try {
      reduce =
        typeof window !== 'undefined' &&
        typeof window.matchMedia === 'function' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch {
      reduce = false;
    }
    if (reduce) {
      setDisplay(value);
      return;
    }
    const t0 = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / duration);
      setDisplay(value * easeOutCubic(p));
      if (p < 1) rafRef.current = requestAnimationFrame(tick);
      else setDisplay(value);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [value, duration]);

  const text = money
    ? formatMoney(display, lang, decimals)
    : prefix +
      display.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }) +
      suffix;

  return <span className={className}>{text}</span>;
}
