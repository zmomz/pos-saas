import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react-swc';
import path from 'path';

// Standalone Vitest config (separate from vite.config.ts so the prerender /
// sitemap build plugins don't run under the test environment).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    // ISSUE-026: contract type-tests (`*.test-d.ts`) that assert the drift-prone
    // api.ts return signatures. `ignoreSourceErrors` scopes failures to the
    // type-tests themselves so the long tail of pre-existing, unrelated source
    // type errors does not gate this guard — what we enforce is that reading a
    // non-existent field off these typed responses fails the type-check.
    typecheck: {
      tsconfig: './tsconfig.app.json',
      include: ['src/**/*.test-d.{ts,tsx}'],
      ignoreSourceErrors: true,
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/lib/**', 'src/pages/**', 'src/contexts/**'],
      // TST-05: regression-ratchet floor. Set a few points below the current
      // measured coverage of the included scope (stmts/lines ≈ 67%, branches
      // ≈ 64%, funcs ≈ 39%). `pnpm run test:coverage` (CI) fails when coverage
      // drops below these. Raise them as coverage climbs; never lower them.
      thresholds: {
        statements: 65,
        branches: 60,
        functions: 35,
        lines: 65,
      },
    },
  },
});
