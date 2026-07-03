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
          // Function form (not the object form): the object form let Rollup fold
          // the small `react-vendor`/`form-vendor` groups into `ui-vendor` and
          // leave 33-byte facade re-export stubs behind. Assigning every
          // node_modules module to a group by path keeps each vendor in its own
          // chunk. Order matters: match `react-router` and the scoped `@radix-ui`
          // packages before the bare `react`/`react-dom` rule so their own code
          // isn't swept into react-vendor.
          manualChunks(id: string) {
            if (!id.includes('node_modules')) return undefined;
            const m = id.replace(/\\/g, '/');
            if (/\/node_modules\/react-router(-dom)?\//.test(m)) return 'router-vendor';
            if (/\/node_modules\/@radix-ui\//.test(m)) return 'ui-vendor';
            if (/\/node_modules\/(react-hook-form|@hookform\/resolvers|zod)\//.test(m))
              return 'form-vendor';
            if (/\/node_modules\/@tanstack\//.test(m)) return 'query-vendor';
            if (
              /\/node_modules\/(react|react-dom|scheduler|use-sync-external-store|react-is)\//.test(m)
            )
              return 'react-vendor';
            if (
              /\/node_modules\/(axios|clsx|tailwind-merge|class-variance-authority|date-fns|lucide-react)\//.test(
                m
              )
            )
              return 'utils-vendor';
            return 'vendor';
          },
        },
      },
      chunkSizeWarningLimit: 1000,
    },
  };
});
