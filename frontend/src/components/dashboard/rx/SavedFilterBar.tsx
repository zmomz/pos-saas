import { useState } from 'react';
import { Bookmark, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { SavedFilter } from '@/hooks/useSavedFilters';

interface SavedFilterBarProps<T> {
  /** the persisted presets (from useSavedFilters) */
  saved: SavedFilter<T>[];
  /** re-apply a preset's captured filter value */
  onApply: (value: T) => void;
  /** persist the current filter under the given (already user-typed) name */
  onSave: (name: string) => void;
  /** drop a preset by name */
  onRemove: (name: string) => void;
  /** label for the save button */
  saveLabel: string;
  /** placeholder for the name input */
  namePlaceholder: string;
  /** accessible name for an apply chip (preset name passed in) */
  applyTitle: (name: string) => string;
  /** accessible name for a remove control (preset name passed in) */
  removeLabel: (name: string) => string;
}

/**
 * #231 (Productivity — saved filters/reports). Presentational strip of saved
 * view presets: each preset is an apply chip with a paired remove control, and a
 * small name-and-save affordance captures the current filter combination. All
 * persistence lives in {@link useSavedFilters}; this component is stateless
 * beyond the draft name in its input.
 */
export default function SavedFilterBar<T>({
  saved,
  onApply,
  onSave,
  onRemove,
  saveLabel,
  namePlaceholder,
  applyTitle,
  removeLabel,
}: SavedFilterBarProps<T>) {
  const [name, setName] = useState('');

  const handleSave = () => {
    if (!name.trim()) return;
    onSave(name.trim());
    setName('');
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {saved.map((f) => (
        <span
          key={f.name}
          className="inline-flex items-center rounded-full border border-border bg-muted/40 text-sm"
        >
          <button
            type="button"
            onClick={() => onApply(f.value)}
            aria-label={applyTitle(f.name)}
            className="inline-flex items-center gap-1.5 ps-3 pe-1.5 py-1 text-foreground/90 hover:text-foreground"
          >
            <Bookmark className="h-3.5 w-3.5 opacity-70" aria-hidden="true" />
            {f.name}
          </button>
          <button
            type="button"
            onClick={() => onRemove(f.name)}
            aria-label={removeLabel(f.name)}
            className="inline-flex items-center rounded-full p-1 me-0.5 text-muted-foreground hover:text-destructive"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </span>
      ))}

      <div className="flex items-center gap-1.5">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              handleSave();
            }
          }}
          placeholder={namePlaceholder}
          className="h-8 w-40 text-sm"
        />
        <Button type="button" variant="outline" size="sm" onClick={handleSave}>
          {saveLabel}
        </Button>
      </div>
    </div>
  );
}
