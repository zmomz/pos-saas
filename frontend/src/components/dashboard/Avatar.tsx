import { cn } from '@/lib/utils';

/** Initials avatar — brand gradient disc, matching the handoff `.avatar`. */
export function Avatar({
  name,
  size = 36,
  className,
}: {
  name?: string | null;
  size?: number;
  className?: string;
}) {
  const initials = (name || '?')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join('') || '?';
  return (
    <span
      className={cn(
        'flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand to-brand-700 font-bold text-white',
        className
      )}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.36) }}
    >
      {initials}
    </span>
  );
}

export default Avatar;
