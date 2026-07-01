import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LanguageProvider } from '@/lib/i18n';

// #208 (M11 FE-Platform) — states adoption. The workforce dialog's secondary
// section loaders (attendance / schedule tabs) must use the shared
// `LoadingState` (aria-live status region), not a bespoke `animate-pulse` text
// block. Both list calls stay in flight so the loaders render.

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

vi.mock('@/lib/api', () => ({
  // Never resolve — keeps `attLoading` / `shiftsLoading` true so the section
  // loaders render.
  getStaffAttendance: vi.fn().mockReturnValue(new Promise(() => {})),
  getStaffShifts: vi.fn().mockReturnValue(new Promise(() => {})),
  assignStaffShift: vi.fn(),
  cancelStaffShift: vi.fn(),
  clearStaffPin: vi.fn(),
  clockInStaff: vi.fn(),
  clockOutStaff: vi.fn(),
  setStaffLifecycle: vi.fn(),
  setStaffPin: vi.fn(),
}));

import StaffWorkforceDialog from './StaffWorkforceDialog';

function renderDialog() {
  return render(
    <LanguageProvider>
      <StaffWorkforceDialog
        open
        onOpenChange={() => {}}
        staff={{ id: 1, name: 'Jamila', status: 'active' }}
        onChanged={() => {}}
      />
    </LanguageProvider>
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('StaffWorkforceDialog section loading adoption (#208)', () => {
  it('renders the shared LoadingState (status region) for the attendance tab, not a bespoke animate-pulse block', async () => {
    renderDialog();

    // Radix mounts only the active tabpanel — switch to attendance, whose list
    // call is in flight.
    await userEvent.click(screen.getByRole('tab', { name: /attendance/i }));

    const panel = screen.getByRole('tabpanel');
    expect(within(panel).getByRole('status')).toBeInTheDocument();
    expect(panel.querySelector('.animate-pulse')).not.toBeInTheDocument();
  });
});
