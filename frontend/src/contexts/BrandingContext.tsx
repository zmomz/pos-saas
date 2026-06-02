import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  ReactNode,
} from 'react';
import { useAuth } from './AuthContext';
import { getAgentBranding, getClientBranding } from '../lib/api';

export interface Branding {
  logo_url?: string | null;
  primary_color: string;
  secondary_color: string;
  font_family: string;
  button_radius: string;
}

interface BrandingContextType {
  branding: Branding | null;
  logoUrl: string | null;
  refreshBranding: () => Promise<void>;
}

const BrandingContext = createContext<BrandingContextType | null>(null);

export const useBranding = () => {
  const context = useContext(BrandingContext);
  if (!context) {
    throw new Error('useBranding must be used within a BrandingProvider');
  }
  return context;
};

/**
 * Convert a hex color (#RRGGBB / #RGB) to a shadcn-style HSL triple string
 * ("H S% L%") so it can be assigned to the `--primary` CSS variable, which the
 * design system consumes via `hsl(var(--primary))`.
 */
export function hexToHslTriple(hex: string): string | null {
  if (!hex) return null;
  let h = hex.trim().replace('#', '');
  if (h.length === 3) {
    h = h.split('').map((c) => c + c).join('');
  }
  if (h.length !== 6 || /[^0-9a-fA-F]/.test(h)) return null;

  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let hue = 0;
  let sat = 0;
  const light = (max + min) / 2;

  if (max !== min) {
    const d = max - min;
    sat = light > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r:
        hue = (g - b) / d + (g < b ? 6 : 0);
        break;
      case g:
        hue = (b - r) / d + 2;
        break;
      default:
        hue = (r - g) / d + 4;
    }
    hue /= 6;
  }

  const H = Math.round(hue * 360);
  const S = Math.round(sat * 100);
  const L = Math.round(light * 100);
  return `${H} ${S}% ${L}%`;
}

/** Relative luminance to pick a readable foreground for the primary color. */
function readableForeground(hex: string): string {
  let h = hex.trim().replace('#', '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  if (h.length !== 6) return '0 0% 100%';
  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return lum > 0.6 ? '222.2 47.4% 11.2%' : '0 0% 100%';
}

/** Apply branding to the document root so the whole UI is white-labeled. */
export function applyBranding(branding: Branding): void {
  const root = document.documentElement;

  const hsl = hexToHslTriple(branding.primary_color);
  if (hsl) {
    root.style.setProperty('--primary', hsl);
    root.style.setProperty('--ring', hsl);
    root.style.setProperty('--primary-foreground', readableForeground(branding.primary_color));
  }
  const secondaryHsl = hexToHslTriple(branding.secondary_color);
  if (secondaryHsl) {
    root.style.setProperty('--accent', secondaryHsl);
  }
  if (branding.button_radius) {
    root.style.setProperty('--radius', branding.button_radius);
  }
  if (branding.font_family) {
    document.body.style.fontFamily = `${branding.font_family}, system-ui, sans-serif`;
  }
}

/** Remove branding overrides (e.g. on logout) so defaults from index.css apply. */
function clearBranding(): void {
  const root = document.documentElement;
  ['--primary', '--ring', '--primary-foreground', '--accent', '--radius'].forEach((v) =>
    root.style.removeProperty(v)
  );
  document.body.style.removeProperty('font-family');
}

export const BrandingProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { user } = useAuth();
  const [branding, setBranding] = useState<Branding | null>(null);

  const refreshBranding = useCallback(async () => {
    if (!user) {
      clearBranding();
      setBranding(null);
      return;
    }
    try {
      let data: Branding | null = null;
      if (user.role === 'agent') {
        data = (await getAgentBranding()) as Branding;
      } else if (user.role === 'client') {
        data = (await getClientBranding()) as Branding;
      }
      if (data && data.primary_color) {
        applyBranding(data);
        setBranding(data);
      }
    } catch {
      // Branding is best-effort; fall back to default theme silently.
    }
  }, [user]);

  useEffect(() => {
    refreshBranding();
  }, [refreshBranding]);

  return (
    <BrandingContext.Provider
      value={{ branding, logoUrl: branding?.logo_url || null, refreshBranding }}
    >
      {children}
    </BrandingContext.Provider>
  );
};
