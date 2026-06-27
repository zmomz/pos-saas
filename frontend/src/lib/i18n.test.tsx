import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LanguageProvider, useLanguage } from './i18n';

function Probe() {
  const { t, language, setLanguage, isRTL } = useLanguage();
  return (
    <div>
      <span data-testid="lang">{language}</span>
      <span data-testid="rtl">{String(isRTL)}</span>
      <span data-testid="label">{t('cart')}</span>
      <button onClick={() => setLanguage('ar')}>to-ar</button>
      <button onClick={() => setLanguage('en')}>to-en</button>
    </div>
  );
}

describe('LanguageProvider (i18n instant toggle)', () => {
  it('changes language app-wide and flips RTL/document.dir instantly', () => {
    render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>
    );

    // Defaults to English (LTR).
    expect(screen.getByTestId('lang').textContent).toBe('en');
    expect(screen.getByTestId('rtl').textContent).toBe('false');
    const enLabel = screen.getByTestId('label').textContent;

    // Switching to Arabic re-renders the consumer immediately.
    fireEvent.click(screen.getByText('to-ar'));
    expect(screen.getByTestId('lang').textContent).toBe('ar');
    expect(screen.getByTestId('rtl').textContent).toBe('true');
    expect(document.documentElement.dir).toBe('rtl');
    expect(screen.getByTestId('label').textContent).not.toBe(enLabel);
    expect(localStorage.getItem('pos-language')).toBe('ar');

    // And back to English (LTR).
    fireEvent.click(screen.getByText('to-en'));
    expect(document.documentElement.dir).toBe('ltr');
  });

  it('falls back safely with no provider (non-reactive)', () => {
    function Solo() {
      const { t, language } = useLanguage();
      return <span data-testid="solo">{language}:{t('cart')}</span>;
    }
    render(<Solo />);
    expect(screen.getByTestId('solo').textContent).toContain('en:');
  });

  it('exposes a shared tt(key, fallback) helper: real translation when present, fallback when missing', () => {
    function TtProbe() {
      const { tt } = useLanguage();
      return (
        <div>
          <span data-testid="tt-present">{tt('cart', 'FALLBACK')}</span>
          <span data-testid="tt-missing">{tt('__no_such_key__', 'FALLBACK')}</span>
        </div>
      );
    }
    render(
      <LanguageProvider>
        <TtProbe />
      </LanguageProvider>
    );
    // Known key resolves to its translation, not the fallback.
    expect(screen.getByTestId('tt-present').textContent).toBe('Cart');
    // Unknown key (t() echoes the key) yields the inline fallback.
    expect(screen.getByTestId('tt-missing').textContent).toBe('FALLBACK');
  });

  it('exposes tt even with no provider (non-reactive fallback)', () => {
    function SoloTt() {
      const { tt } = useLanguage();
      return <span data-testid="solo-tt">{tt('__no_such_key__', 'FALLBACK')}</span>;
    }
    render(<SoloTt />);
    expect(screen.getByTestId('solo-tt').textContent).toBe('FALLBACK');
  });
});
