import { describe, it, expect, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LanguageProvider } from '@/lib/i18n';
import { CUSTOMER_DISPLAY_KEY } from '@/lib/customerDisplay';
import CustomerDisplay from './CustomerDisplay';

// ISSUE-091 — re-skin + i18n/RTL for CustomerDisplay. The second-screen chrome
// must go through t() in the *selected* language (no hardcoded bilingual copy)
// and flip direction with the language, mirroring the established pattern.
// The per-line product name stays bilingual (name_ar primary / name secondary) —
// that is the HW-05 localStorage data contract, not chrome.

function setDisplay(payload: Record<string, unknown>) {
  localStorage.setItem(CUSTOMER_DISPLAY_KEY, JSON.stringify(payload));
}

function renderPage() {
  return render(
    <LanguageProvider>
      <CustomerDisplay />
    </LanguageProvider>
  );
}

afterEach(() => {
  localStorage.clear();
});

describe('CustomerDisplay re-skin (i18n/RTL)', () => {
  it('renders the idle/empty state in English only with LTR direction', () => {
    localStorage.setItem('pos-language', 'en');
    setDisplay({ items: [], subtotal: 0, vat: 0, total: 0, status: 'idle' });

    const { container } = renderPage();

    // English chrome via t().
    expect(screen.getByText('Welcome')).toBeInTheDocument();
    expect(screen.getByText(/waiting for items/i)).toBeInTheDocument();
    // No hardcoded Arabic chrome leaking into the English view.
    expect(screen.queryByText('في انتظار المنتجات')).not.toBeInTheDocument();
    // Direction follows the language (was hardcoded rtl before).
    expect(container.querySelector('[dir="ltr"]')).toBeInTheDocument();
    expect(container.querySelector('[dir="rtl"]')).not.toBeInTheDocument();
  });

  it('renders the active cart with translated totals and a bilingual product line', () => {
    localStorage.setItem('pos-language', 'en');
    setDisplay({
      items: [{ name: 'Latte', name_ar: 'لاتيه', quantity: 2, price: 10 }],
      subtotal: 20,
      vat: 3,
      total: 23,
      status: 'active',
    });

    renderPage();

    // Totals chrome via reused keys.
    expect(screen.getByText('Subtotal')).toBeInTheDocument();
    expect(screen.getByText('VAT (15%)')).toBeInTheDocument();
    expect(screen.getByText('Total')).toBeInTheDocument();
    // The product line keeps the bilingual data (Arabic name primary, English secondary).
    expect(screen.getByText('لاتيه')).toBeInTheDocument();
    expect(screen.getByText('Latte')).toBeInTheDocument();
    // Line amount renders.
    expect(screen.getByText('20.00')).toBeInTheDocument();
  });

  it('renders the paid/thank-you state in English only', () => {
    localStorage.setItem('pos-language', 'en');
    setDisplay({ items: [], subtotal: 0, vat: 0, total: 0, status: 'paid' });

    renderPage();

    expect(screen.getByText(/thank you/i)).toBeInTheDocument();
    // No hardcoded Arabic copy in the English view.
    expect(screen.queryByText('شكراً لك!')).not.toBeInTheDocument();
  });

  it('renders translated and RTL in Arabic', () => {
    localStorage.setItem('pos-language', 'ar');
    setDisplay({ items: [], subtotal: 0, vat: 0, total: 0, status: 'idle' });

    const { container } = renderPage();

    expect(screen.getByText('في انتظار المنتجات')).toBeInTheDocument();
    expect(container.querySelector('[dir="rtl"]')).toBeInTheDocument();
  });
});
