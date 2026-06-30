import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';

// #243 AC1 — the marketing LandingPage must position with logical (start/end)
// props, not physical left/right, so the layout mirrors correctly in RTL
// (ar/ur). Physical `left-1/2` / `right-1/2` absolute positioning silently
// breaks the "how it works" connector line and the "most popular" badge in RTL.
const src = readFileSync(path.resolve(__dirname, './LandingPage.tsx'), 'utf8');

describe('LandingPage RTL positioning (#243 AC1)', () => {
  it('uses no physical left-1/2 positioning class', () => {
    expect(src).not.toMatch(/\bleft-1\/2\b/);
  });

  it('uses no physical right-1/2 positioning class', () => {
    expect(src).not.toMatch(/\bright-1\/2\b/);
  });
});
