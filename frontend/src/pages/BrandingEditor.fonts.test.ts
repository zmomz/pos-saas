// ISSUE-233 (B1) — font-bundling truthfulness. The branding editor offers a
// font picker whose choices drive the live preview AND the runtime white-label
// theme. Any offered font that isn't actually loaded makes the preview *lie*:
// the merchant picks "Poppins", sees a system fallback, and ships that. This
// guard asserts every selectable font is declared in the bundled font <link>
// so the preview can never offer a font the page doesn't load.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';
import { fontOptions } from './BrandingEditor';

const INDEX_HTML = path.resolve(__dirname, '../../index.html');
const html = readFileSync(INDEX_HTML, 'utf8');

describe('BrandingEditor font bundling (B1)', () => {
  it('every selectable font is bundled in index.html so the preview never lies', () => {
    const missing = fontOptions
      .map((o) => o.value)
      .filter((family) => {
        // Google Fonts encodes spaces as '+': "Noto Sans" -> "Noto+Sans".
        const token = `family=${family.replace(/ /g, '+')}`;
        return !html.includes(token);
      });
    expect(missing).toEqual([]);
  });
});
