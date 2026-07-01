import * as React from 'react';
import { Search } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/input';

/**
 * Accessible search box (M11 · FE-Platform a11y, #226).
 *
 * List/table pages pair a magnifier glyph with a bare <Input> whose only text
 * is a `placeholder`. A placeholder is not an accessible name — a screen-reader
 * user hears "edit text, blank" and loses the hint the instant they type. This
 * component bundles the icon-plus-input pattern and always exposes the control
 * as a named `searchbox` (WCAG 4.1.2), deriving the accessible name from an
 * explicit `label` and falling back to the visible `placeholder`.
 *
 * The magnifier is decorative (the name lives on the input), so it is marked
 * `aria-hidden`. Logical spacing props (`start-3`, `ps-10`) keep the layout
 * correct under RTL.
 */
export interface SearchFieldProps
  extends Omit<React.ComponentProps<'input'>, 'type'> {
  /** Accessible name for the field. Falls back to `placeholder` when omitted. */
  label?: string;
  /** Extra classes for the wrapping element (the input keeps its own class). */
  containerClassName?: string;
}

const SearchField = React.forwardRef<HTMLInputElement, SearchFieldProps>(
  ({ label, placeholder, containerClassName, className, ...props }, ref) => {
    const accessibleName = label ?? (typeof placeholder === 'string' ? placeholder : undefined);
    return (
      <div className={cn('relative flex-1', containerClassName)}>
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          ref={ref}
          type="search"
          aria-label={accessibleName}
          placeholder={placeholder}
          className={cn('ps-10', className)}
          {...props}
        />
      </div>
    );
  }
);
SearchField.displayName = 'SearchField';

export { SearchField };
