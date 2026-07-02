import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { LanguageProvider } from '@/lib/i18n';

// M11 · FE-Platform a11y (#226) — dialog focus + description pass on the
// first-run OnboardingTour.
//
// A modal dialog must move focus *into* itself when it opens, otherwise a
// keyboard / screen-reader user's focus stays on whatever was behind the now
// inert backdrop — they cannot reach the tour's own controls without hunting,
// and a screen reader never announces the dialog (WCAG 2.4.3). The tour also
// only labelled itself by its heading; its step body was never associated, so
// the actual guidance was not announced with the dialog. This slice focuses the
// dialog on open and points `aria-describedby` at the step body.

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

function showTour() {
  renderTour();
  act(() => {
    vi.advanceTimersByTime(1000);
  });
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

describe('OnboardingTour dialog focus + description (#226)', () => {
  it('moves focus into the dialog when the tour opens', () => {
    const dialog = showTour();
    // Focus lands on the dialog itself (or a control inside it), never on the
    // page behind the inert backdrop.
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it('describes the dialog by its step body text', () => {
    const dialog = showTour();
    const describedById = dialog.getAttribute('aria-describedby');
    expect(describedById).toBeTruthy();
    const desc = document.getElementById(describedById as string);
    expect(desc).not.toBeNull();
    // The description element carries the step's guidance copy, not an empty node.
    expect(desc?.textContent?.trim().length).toBeGreaterThan(0);
  });
});
