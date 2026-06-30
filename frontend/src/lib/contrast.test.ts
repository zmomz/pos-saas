import { describe, it, expect } from 'vitest';
import { luminance, readableTextColor, normalizeHex } from './contrast';

// Shared white-label contrast guard (M2 Fix; shared with the BrandingEditor and
// AgentLandingPage CTAs): a pale tenant brand must never ship white-on-pale text.

describe('luminance', () => {
  it('returns 0 for black and ~1 for white', () => {
    expect(luminance('#000000')).toBeCloseTo(0, 5);
    expect(luminance('#ffffff')).toBeCloseTo(1, 5);
  });

  it('expands 3-digit hex', () => {
    expect(luminance('#fff')).toBeCloseTo(1, 5);
  });

  it('returns null for an unparseable value', () => {
    expect(luminance('not-a-color')).toBeNull();
    expect(luminance('#12')).toBeNull();
  });
});

describe('readableTextColor', () => {
  it('picks dark ink on a pale brand', () => {
    expect(readableTextColor('#FFF8E1')).toBe('#0a0a0a');
  });

  it('picks white on a dark brand', () => {
    expect(readableTextColor('#006C35')).toBe('#ffffff');
  });

  it('falls back to white when the hex cannot be parsed', () => {
    expect(readableTextColor('rgb(1,2,3)')).toBe('#ffffff');
  });
});

describe('normalizeHex', () => {
  it('repairs a missing leading # and lowercases', () => {
    expect(normalizeHex('1488A6')).toBe('#1488a6');
  });

  it('expands a 3-digit shorthand to 6 digits', () => {
    expect(normalizeHex('#FFF')).toBe('#ffffff');
    expect(normalizeHex('0a0')).toBe('#00aa00');
  });

  it('trims surrounding whitespace', () => {
    expect(normalizeHex('  #006C35 ')).toBe('#006c35');
  });

  it('returns null for an invalid color so it cannot be saved', () => {
    expect(normalizeHex('zzz')).toBeNull();
    expect(normalizeHex('#12')).toBeNull();
    expect(normalizeHex('')).toBeNull();
    expect(normalizeHex('#1488a6ff')).toBeNull();
  });
});
