import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { LanguageProvider } from '@/lib/i18n';

// M11 · FE-Platform a11y (#226) — screen-reader + keyboard pass on the
// first-run OnboardingTour.
//
// The tour paints a full-screen backdrop (z-[9999]) with a focused tooltip
// card on top — structurally a modal dialog. But it was a bare <div>: a
// screen-reader user got no dialog role, no announced name, and no way to
// dismiss it from the keyboard (the only escape hatch was *clicking* the
// backdrop — a mouse-only affordance). WCAG 2.1.1 (keyboard) / 4.1.2 (name,
// role, value). This slice gives the card `role="dialog"` + `aria-modal`,
// labels it by its step heading, and wires Escape to the same finish path as
// the backdrop click.

// The tour reads the current user/role and business type from context; mock
// both so we can drive a deterministic master tour.
let authState = { user: { role: 'master' } };
let businessState = { businessType: 'retail', ready: true };
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => authState }));
vi.mock('@/contexts/BusinessProfileContext', () => ({
  useBusinessProfile: () => businessState,
}));

import OnboardingTour from './OnboardingTour';

function renderTour() {
  return render(
    <LanguageProvider>
      <OnboardingTour />
    </LanguageProvider>,
  );
}

// The tour arms an 800ms timer before it becomes visible; drive fake timers
// past it, then hand control back to real timers so userEvent works.
function showTour() {
  renderTour();
  act(() => {
    vi.advanceTimersByTime(1000);
  });
  // The dialog is rendered synchronously once the arming timer fires and the
  // act() flush commits the state update.
  return screen.getByRole('dialog');
}

beforeEach(() => {
  authState = { user: { role: 'master' } };
  businessState = { businessType: 'retail', ready: true };
  localStorage.clear();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  localStorage.clear();
});

describe('OnboardingTour a11y (#226)', () => {
  it('exposes the tour card as a modal dialog', async () => {
    showTour();
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('gives the dialog an accessible name from the current step heading', async () => {
    showTour();
    // The master tour's first step is the welcome heading.
    const dialog = screen.getByRole('dialog', { name: 'Welcome, Master Admin!' });
    expect(dialog).toBeInTheDocument();
  });

  it('dismisses the tour when Escape is pressed', async () => {
    showTour();

    act(() => {
      fireEvent.keyDown(document, { key: 'Escape' });
    });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    // Dismissal is a completion: the flag is persisted so it does not re-arm.
    expect(localStorage.getItem('onboarding_completed_master')).toBe('true');
  });

  // ISSUE-226 (a11y · RTL) — the "Skip" affordance leads with a SkipForward
  // glyph: a play-head skipping *forward*, i.e. toward the end of the reading
  // direction. Under RTL "forward" is leftward, so an unmirrored glyph points
  // the wrong way. Its sibling "Next" chevron already flips (`rtl:rotate-180`);
  // this brings the skip glyph to the same idiom so the pair reads coherently.
  it('leaves the Skip glyph upright in LTR', () => {
    const dialog = showTour();
    const glyph = dialog.querySelector('.lucide-skip-forward');
    expect(glyph).not.toBeNull();
    expect(glyph?.classList.contains('rotate-180')).toBe(false);
  });

  it('mirrors the Skip glyph under RTL', () => {
    localStorage.setItem('pos-language', 'ar');
    const dialog = showTour();
    const glyph = dialog.querySelector('.lucide-skip-forward');
    expect(glyph).not.toBeNull();
    expect(glyph?.classList.contains('rotate-180')).toBe(true);
  });
});
