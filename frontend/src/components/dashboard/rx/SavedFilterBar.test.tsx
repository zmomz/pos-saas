import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SavedFilterBar from './SavedFilterBar';

// #231 (Productivity — saved filters). Presentational bar: renders the saved
// presets as apply/remove chips and a name-and-save affordance. The persistence
// (localStorage upsert) lives in useSavedFilters; here we only assert the wiring.
interface F {
  search: string;
}
const saved = [
  { name: 'Dairy', value: { search: 'milk' } },
  { name: 'Bakery', value: { search: 'bread' } },
];

const labels = {
  saveLabel: 'Save view',
  namePlaceholder: 'Name this view…',
  applyTitle: (n: string) => `Apply ${n}`,
  removeLabel: (n: string) => `Remove ${n}`,
};

describe('SavedFilterBar (#231)', () => {
  it('renders a button per preset and applies its value on click', async () => {
    const onApply = vi.fn();
    render(<SavedFilterBar saved={saved} onApply={onApply} onSave={vi.fn()} onRemove={vi.fn()} {...labels} />);

    await userEvent.click(screen.getByRole('button', { name: 'Apply Dairy' }));

    expect(onApply).toHaveBeenCalledWith({ search: 'milk' });
  });

  it('saves the typed (trimmed) name and clears the input', async () => {
    const onSave = vi.fn();
    render(<SavedFilterBar saved={[]} onApply={vi.fn()} onSave={onSave} onRemove={vi.fn()} {...labels} />);

    const input = screen.getByPlaceholderText('Name this view…');
    await userEvent.type(input, '  Low stock  ');
    await userEvent.click(screen.getByRole('button', { name: 'Save view' }));

    expect(onSave).toHaveBeenCalledWith('Low stock');
    expect(input).toHaveValue('');
  });

  it('does not save a blank name', async () => {
    const onSave = vi.fn();
    render(<SavedFilterBar saved={[]} onApply={vi.fn()} onSave={onSave} onRemove={vi.fn()} {...labels} />);

    await userEvent.click(screen.getByRole('button', { name: 'Save view' }));

    expect(onSave).not.toHaveBeenCalled();
  });

  it('removes a preset by name', async () => {
    const onRemove = vi.fn();
    render(<SavedFilterBar saved={saved} onApply={vi.fn()} onSave={vi.fn()} onRemove={onRemove} {...labels} />);

    await userEvent.click(screen.getByRole('button', { name: 'Remove Bakery' }));

    expect(onRemove).toHaveBeenCalledWith('Bakery');
  });
});
