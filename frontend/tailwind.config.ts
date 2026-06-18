import type { Config } from 'tailwindcss';
import tailwindcssAnimate from 'tailwindcss-animate';
import tailwindcssAspectRatio from '@tailwindcss/aspect-ratio';
import tailwindcssTypography from '@tailwindcss/typography';

export default {
  darkMode: ['class'],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  prefix: '',
  theme: {
    container: {
      center: true,
      padding: '2rem',
      screens: {
        '2xl': '1400px',
      },
    },
    extend: {
      // 'Saudi Riyal' leads every stack so the U+20C1 currency glyph resolves to
      // the bundled webfont (scoped to that codepoint via unicode-range in
      // index.css); all other characters fall through to the real family. This
      // matters for `font-mono` prices too — JetBrains Mono lacks the glyph.
      fontFamily: {
        sans: ['Saudi Riyal', 'Hanken Grotesk', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['Saudi Riyal', 'JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
        arabic: ['Saudi Riyal', 'IBM Plex Sans Arabic', 'Hanken Grotesk', 'system-ui', 'sans-serif'],
      },
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        // Brand petrol teal-blue scale — the single primary across all surfaces.
        brand: {
          50: '#eaf5f8',
          100: '#d7ebf1',
          200: '#b3d9e5',
          300: '#84c2d4',
          400: '#45a6bf',
          500: '#1488a6',
          600: '#0e7693',
          700: '#0d6079',
          800: '#143c4c',
          900: '#0e2c38',
          DEFAULT: '#1488a6',
        },
        // Warm gold accent (fixed across themes). `900` is the dark gold "ink"
        // used for text/badges on gold fills (e.g. landing "Most popular" pills).
        gold: {
          50: '#faf1df',
          600: '#cd9a40',
          900: '#5a4410',
          DEFAULT: '#e6b45c',
        },
        // Bright cyan accent (dark-tile spark lines / gauges). CSS-var driven
        // so raw SVG/inline styles can share the one source (`--cyan`).
        cyan: 'var(--cyan)',
        // Semantic stat colors (fixed across themes). The three that back solid
        // action buttons carry an explicit foreground tuned for contrast — gold
        // `warning` needs dark ink, not white (avoids the contrast failure).
        success: { DEFAULT: '#23a06b', foreground: '#ffffff' },
        warning: { DEFAULT: '#d6a33a', foreground: '#3a2c10' },
        // `700` shades back the leaderboard avatar gradients (and any other
        // two-tone fills) without raw hex. DEFAULT keeps `text-violet`/`bg-sky` working.
        violet: { DEFAULT: '#7b57c9', 700: '#5b3fa8' },
        sky: { DEFAULT: '#3d9ad1', 700: '#2a72a0' },
        danger: { DEFAULT: '#d14a3a', foreground: '#ffffff', 700: '#a8392c' },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        sidebar: {
          DEFAULT: 'hsl(var(--sidebar-background))',
          foreground: 'hsl(var(--sidebar-foreground))',
          primary: 'hsl(var(--sidebar-primary))',
          'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
          accent: 'hsl(var(--sidebar-accent))',
          'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
          border: 'hsl(var(--sidebar-border))',
          ring: 'hsl(var(--sidebar-ring))',
        },
      },
      borderRadius: {
        '2xl': 'calc(var(--radius) + 6px)',
        xl: 'calc(var(--radius) + 2px)',
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      boxShadow: {
        brand: '0 18px 40px -18px hsl(194 80% 30% / 0.45)',
        card: '0 1px 2px hsl(214 40% 18% / 0.05), 0 8px 24px -12px hsl(214 40% 18% / 0.10)',
      },
      keyframes: {
        'accordion-down': {
          from: {
            height: '0',
          },
          to: {
            height: 'var(--radix-accordion-content-height)',
          },
        },
        'accordion-up': {
          from: {
            height: 'var(--radix-accordion-content-height)',
          },
          to: {
            height: '0',
          },
        },
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        'fade-up': 'fade-up 0.5s ease-out both',
        float: 'float 6s ease-in-out infinite',
      },
    },
  },
  plugins: [tailwindcssAnimate, tailwindcssAspectRatio, tailwindcssTypography],
} satisfies Config;
