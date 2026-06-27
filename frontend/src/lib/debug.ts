// FE-10: dev-only debug logging.
//
// Debug/diagnostic `console.log` calls used to run on every app load, shipping
// noisy internal logs to end users' browser consoles in production. Route all
// such logging through this single chokepoint instead: it forwards to
// console.log only in development (`import.meta.env.DEV`). Vite statically
// replaces `import.meta.env.DEV` with `false` in a production build, so the
// branch (and its arguments) is dead-code-eliminated and never ships.
//
// Genuine warnings/errors that users or operators must see should keep using
// console.warn / console.error directly — those are not debug logging.
export function debugLog(...args: unknown[]): void {
  if (import.meta.env.DEV) {
    console.log(...args);
  }
}
