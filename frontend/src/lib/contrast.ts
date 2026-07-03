/**
 * White-label contrast guard (M2 Fix).
 *
 * A tenant chooses an arbitrary brand colour; chrome that paints solid-brand
 * surfaces (CTAs, the POS pay button, the agent storefront) must not hard-code
 * `text-white`, or a pale brand ships unreadable white-on-pale. These helpers
 * pick a legible text colour for a given solid background.
 *
 * The picker compares the *actual WCAG contrast ratio* of white vs near-black
 * ink against the background and keeps whichever is higher. The earlier
 * heuristic (a raw, non-gamma-corrected luminance over a 0.6 threshold) kept
 * white on mid-tone brands like blue-500 (#3b82f6) where white-on-brand is only
 * 3.64:1 — below the 4.5:1 AA floor. `readableForeground` in BrandingContext
 * (which drives `--primary-foreground` for token-based chrome) delegates here so
 * the runtime and the BrandingEditor preview agree.
 */

/**
 * Non-gamma-corrected relative luminance of a hex colour in [0,1], or null when
 * it can't be parsed. Kept for backwards compatibility; contrast decisions use
 * the gamma-correct `contrastRatio` below (WCAG relative luminance).
 */
export function luminance(hex: string): number | null {
  const rgb = hexToRgb(hex);
  if (!rgb) return null;
  return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
}

/** Parse `#rgb`/`#rrggbb` into [r,g,b] (0-255), or null when unparseable. */
function hexToRgb(hex: string): [number, number, number] | null {
  let h = (hex ?? '').trim().replace('#', '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  if (h.length !== 6 || /[^0-9a-fA-F]/.test(h)) return null;
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

/** WCAG 2.x relative luminance (channels linearized) of an [r,g,b] triple. */
function relativeLuminance([r, g, b]: [number, number, number]): number {
  const lin = [r, g, b].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
}

/**
 * WCAG contrast ratio (1–21) between two hex colours, or null when either can't
 * be parsed. 4.5:1 is the AA floor for normal text, 3:1 for large text.
 */
export function contrastRatio(hexA: string, hexB: string): number | null {
  const a = hexToRgb(hexA);
  const b = hexToRgb(hexB);
  if (!a || !b) return null;
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Validate and normalize a hex color: trims whitespace, repairs a missing `#`,
 * expands a 3-digit shorthand, and lowercases. Returns `#rrggbb` for any valid
 * input or `null` when it can't be parsed — the BrandingEditor uses the null to
 * reject an invalid color before it can be saved.
 */
export function normalizeHex(hex: string): string | null {
  let h = (hex ?? '').trim().replace(/^#/, '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  if (h.length !== 6 || /[^0-9a-fA-F]/.test(h)) return null;
  return `#${h.toLowerCase()}`;
}

/** Near-black ink used when a pale background can't carry white text. */
export const DARK_INK = '#0a0a0a';

/**
 * Pick the more readable text colour (`#ffffff` or near-black ink) for a solid
 * hex background by comparing real WCAG contrast ratios and keeping the higher.
 * On blue-500 (#3b82f6) that flips from white (3.64:1, fails AA) to dark ink
 * (~5.4:1, passes). Unparseable input falls back to white — the historical
 * default for brand surfaces — so a malformed colour never crashes the render.
 */
export function readableTextColor(hex: string, fallback = '#ffffff'): string {
  const whiteContrast = contrastRatio(hex, '#ffffff');
  const darkContrast = contrastRatio(hex, DARK_INK);
  if (whiteContrast == null || darkContrast == null) return fallback;
  return darkContrast > whiteContrast ? DARK_INK : '#ffffff';
}
