// FE-09 — `ProtectedAdminRoute` was an unused route guard that gated on a
// non-existent `'user'` role (see its `user.role === 'user'` branch). It had
// zero importers anywhere in `src/`, so it was dead residue. These guards keep
// it deleted: the component file must be gone, and no source file may resurrect
// it by importing the identifier.
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const SRC_DIR = path.resolve(__dirname, '..');
const SELF = path.resolve(__dirname, 'ProtectedAdminRoute.removed.test.ts');

/** Every `.ts`/`.tsx` file under `src/`, excluding this guard test itself. */
function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...sourceFiles(full));
    } else if (/\.tsx?$/.test(entry.name) && full !== SELF) {
      out.push(full);
    }
  }
  return out;
}

describe('FE-09 dead ProtectedAdminRoute removal', () => {
  it('deletes the component file', () => {
    expect(existsSync(path.join(SRC_DIR, 'components/ProtectedAdminRoute.tsx'))).toBe(false);
  });

  it('leaves no source file referencing ProtectedAdminRoute', () => {
    const offenders = sourceFiles(SRC_DIR).filter((f) =>
      readFileSync(f, 'utf8').includes('ProtectedAdminRoute'),
    );
    expect(offenders).toEqual([]);
  });
});
