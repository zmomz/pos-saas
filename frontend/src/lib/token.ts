/**
 * JWT access-token storage (localStorage).
 *
 * Extracted from `apiClient.ts` so the auth layer (`auth.ts`) and the HTTP
 * client (`apiClient.ts`) can both depend on token storage without importing
 * each other. Previously `auth.ts` imported these helpers from `apiClient.ts`
 * while `apiClient.ts` needed `authApi` from `auth.ts`, forcing a lazy
 * `await import('./auth')` to dodge the static cycle — which in turn pinned
 * `auth.ts` into the main bundle (Vite: "dynamically imported … but also
 * statically imported … will not move module into another chunk"). With token
 * storage in its own leaf module the cycle is gone and the import can be static.
 */
const TOKEN_KEY = 'pos_auth_token';

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* ignore storage errors */
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore storage errors */
  }
}
