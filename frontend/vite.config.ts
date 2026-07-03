import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';
import path from 'path';
import { createHash } from 'crypto';
import { readFileSync, writeFileSync } from 'fs';
import Sitemap from 'vite-plugin-sitemap';

/**
 * ISSUE-2: stamp a per-build hash into the emitted service worker so its cache
 * name (`pos-shell-<hash>`) changes whenever the bundle changes. The SW's
 * `activate` handler evicts every cache whose name != the current one, so a new
 * deploy is guaranteed to drop the previous build's caches instead of pinning
 * returning users to a stale shell. `public/sw.js` ships a `__BUILD_HASH__`
 * placeholder that this plugin replaces in `dist/sw.js` post-build.
 */
function serviceWorkerBuildHash() {
  return {
    name: 'service-worker-build-hash',
    apply: 'build' as const,
    writeBundle(options: { dir?: string }, bundle: Record<string, unknown>) {
      const outDir = options.dir || path.resolve(__dirname, 'dist');
      const swPath = path.join(outDir, 'sw.js');
      let src: string;
      try {
        src = readFileSync(swPath, 'utf8');
      } catch {
        return; // no sw.js in this build — nothing to stamp
      }
      // Derive a stable hash from the emitted (content-hashed) asset file names.
      const hash = createHash('sha256')
        .update(Object.keys(bundle).sort().join('\n'))
        .digest('hex')
        .slice(0, 12);
      writeFileSync(swPath, src.replace(/__BUILD_HASH__/g, hash));
    },
  };
}

function escapeHtmlAttr(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

process.env.VITE_APP_TITLE ??= process.env.OVERVIEW_TITLE ?? 'POS System';
process.env.VITE_APP_DESCRIPTION ??= process.env.OVERVIEW_DESCRIPTION ?? 'Multi-tenant POS System';
process.env.VITE_APP_TITLE = escapeHtmlAttr(process.env.VITE_APP_TITLE);
process.env.VITE_APP_DESCRIPTION = escapeHtmlAttr(process.env.VITE_APP_DESCRIPTION);
process.env.VITE_APP_LOGO_URL ??= process.env.OVERVIEW_LOGO_URL ?? '/favicon.ico';

// https://vitejs.dev/config/
export default defineConfig(() => {
  return {
    plugins: [
      react(),
      Sitemap({
        hostname: process.env.SITE_URL || 'http://localhost:3000',
        readable: true,
        generateRobotsTxt: true,
      }),
      serviceWorkerBuildHash(),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      host: '0.0.0.0', // Listen on all network interfaces.
      port: parseInt(process.env.VITE_PORT || '3000'),
      proxy: {
        '/api': {
          target: `http://localhost:${process.env.BACKEND_PORT || '8000'}`,
          changeOrigin: true,
        },
      },
      watch: { usePolling: true, interval: 600 },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            // Vendor chunks
            'react-vendor': ['react', 'react-dom'],
            'router-vendor': ['react-router-dom'],
            'ui-vendor': [
              '@radix-ui/react-accordion',
              '@radix-ui/react-alert-dialog',
              '@radix-ui/react-aspect-ratio',
              '@radix-ui/react-avatar',
              '@radix-ui/react-checkbox',
              '@radix-ui/react-collapsible',
              '@radix-ui/react-context-menu',
              '@radix-ui/react-dialog',
              '@radix-ui/react-dropdown-menu',
              '@radix-ui/react-hover-card',
              '@radix-ui/react-label',
              '@radix-ui/react-menubar',
              '@radix-ui/react-navigation-menu',
              '@radix-ui/react-popover',
              '@radix-ui/react-progress',
              '@radix-ui/react-radio-group',
              '@radix-ui/react-scroll-area',
              '@radix-ui/react-select',
              '@radix-ui/react-separator',
              '@radix-ui/react-slider',
              '@radix-ui/react-slot',
              '@radix-ui/react-switch',
              '@radix-ui/react-tabs',
              '@radix-ui/react-toast',
              '@radix-ui/react-toggle',
              '@radix-ui/react-toggle-group',
              '@radix-ui/react-tooltip',
            ],
            'form-vendor': ['react-hook-form', '@hookform/resolvers', 'zod'],
            'utils-vendor': [
              'axios',
              'clsx',
              'tailwind-merge',
              'class-variance-authority',
              'date-fns',
              'lucide-react',
            ],
            'query-vendor': ['@tanstack/react-query'],
          },
        },
      },
      chunkSizeWarningLimit: 1000,
    },
  };
});
