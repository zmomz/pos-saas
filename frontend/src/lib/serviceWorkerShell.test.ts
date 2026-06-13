// ISSUE-101 (U0.3 dead binding): `public/sw.js` precaches an app SHELL via
// `cache.addAll(SHELL)`. addAll is atomic — if a single listed resource 404s,
// the whole precache rejects and NOTHING is cached (the app shell included).
// The SHELL listed `/manifest.webmanifest`, a file that does not exist and is
// not referenced by index.html, voiding the entire offline shell. This test
// guards that every SHELL entry resolves to a real, precachable resource.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const PUBLIC_DIR = path.resolve(__dirname, '../../public');

/** Extract the `SHELL = [ ... ]` string-literal entries from sw.js source. */
function readShell(): string[] {
  const src = readFileSync(path.join(PUBLIC_DIR, 'sw.js'), 'utf8');
  const match = src.match(/const\s+SHELL\s*=\s*\[([^\]]*)\]/);
  if (!match) throw new Error('SHELL array not found in sw.js');
  return Array.from(match[1].matchAll(/['"]([^'"]+)['"]/g)).map((m) => m[1]);
}

/** Routes served by the SPA fallback (index.html) rather than a static file. */
const SPA_ROUTES = new Set(['/', '/index.html']);

function fileExists(p: string): boolean {
  try {
    readFileSync(p);
    return true;
  } catch {
    return false;
  }
}

describe('service-worker app-shell precache', () => {
  it('lists only resources that actually exist', () => {
    const missing = readShell().filter((entry) => {
      if (SPA_ROUTES.has(entry)) return false;
      return !fileExists(path.join(PUBLIC_DIR, entry.replace(/^\//, '')));
    });
    expect(missing).toEqual([]);
  });
});
