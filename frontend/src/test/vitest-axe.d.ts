// ISSUE-274 (M11 · FE-Platform · a11y) — type augmentation for the axe gate.
//
// vitest-axe@0.1.0 ships its `toHaveNoViolations` type augmentation against the
// legacy `declare global { namespace Vi { interface Assertion } }` shape, which
// Vitest 2 no longer exposes — so `expect(...).toHaveNoViolations()` type-checks
// as a missing property even though the runtime matcher (registered in
// `setup.ts` via `expect.extend`) works. Re-declare the augmentation against
// Vitest 2's real matcher interface (`@vitest/expect`'s `Assertion`).
import 'vitest';
import type { AxeMatchers } from 'vitest-axe/matchers';

declare module 'vitest' {
  interface Assertion<T = any> extends AxeMatchers {}
  interface AsymmetricMatchersContaining extends AxeMatchers {}
}
