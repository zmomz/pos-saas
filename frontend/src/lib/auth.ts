import axios, { AxiosInstance } from 'axios';
import { getAPIBaseURL } from './config';
import { setToken, clearToken, getToken } from './apiClient';

export interface AuthUser {
  id: string;
  email: string;
  name?: string;
  role: string;
  // True for freshly-provisioned accounts that must reset their temp password.
  must_change_password?: boolean;
  last_login?: string;
}

interface LoginResponse {
  token: string;
  token_type: string;
  expires_at: number;
  refresh_token?: string;
  user: AuthUser;
}

// /auth/login answers with tokens when the account has no second factor, or with
// a short-lived MFA ticket when it does (ISSUE-202, backend #81). The caller must
// branch on `mfaRequired` and, when set, exchange the ticket + a code at
// `/auth/login/mfa`.
interface MfaChallenge {
  mfa_required: true;
  mfa_token: string;
}

// Flat result rather than a discriminated union: this codebase compiles with
// `strict: false`, where union narrowing on a boolean discriminant doesn't apply,
// so callers read the optional field that matches `mfaRequired`.
export interface LoginResult {
  mfaRequired: boolean;
  /** Set when `mfaRequired` is false — the signed-in user. */
  user?: AuthUser;
  /** Set when `mfaRequired` is true — ticket to exchange at completeMfaLogin. */
  mfaToken?: string;
}

function isMfaChallenge(data: LoginResponse | MfaChallenge): data is MfaChallenge {
  return (data as MfaChallenge).mfa_required === true;
}

const REFRESH_TOKEN_KEY = 'pos_refresh_token';

// FE-01: the refresh token now lives ONLY in an HttpOnly cookie the backend sets
// on every token-minting endpoint (scoped to /api/v1/auth) — never in
// localStorage, where any XSS could read it. Older builds did persist it here, so
// purge any leftover copy whenever we touch the session.
function purgeLegacyRefreshToken() {
  try {
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    /* ignore storage errors */
  }
}

class LocalAuthApi {
  private client: AxiosInstance;

  constructor() {
    // withCredentials so the HttpOnly refresh cookie round-trips on the auth
    // endpoints (Set-Cookie on login/register/refresh, sent back on
    // refresh/logout). Requires same-origin in prod, or ALLOWED_ORIGINS set.
    this.client = axios.create({
      headers: { 'Content-Type': 'application/json' },
      withCredentials: true,
    });
  }

  private getBaseURL() {
    return getAPIBaseURL();
  }

  /** GET /auth/me with an explicit bearer token. Throws on any non-2xx. */
  private async fetchMe(token: string): Promise<AuthUser> {
    const response = await this.client.get(`${this.getBaseURL()}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  }

  /**
   * Return the current user, or null if not authenticated.
   *
   * This drives the app bootstrap (`AuthContext.checkAuthStatus`) and runs on a
   * client with no response interceptor, so it must handle the expired-token
   * case itself. ISSUE-192: on a fresh load past the access-token boundary the
   * stored access token is stale but the HttpOnly refresh cookie is still valid;
   * a bare 401 → clearToken would log the user out without ever trying the one
   * path FE-01 added to rescue them. So on a 401 we attempt a single
   * cookie-driven refresh and replay /auth/me before clearing the session.
   */
  async getCurrentUser(): Promise<AuthUser | null> {
    const token = getToken();
    if (!token) return null;
    try {
      return await this.fetchMe(token);
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        // One refresh attempt; the cookie carries the refresh token.
        if (await this.refreshAccessToken()) {
          const refreshed = getToken();
          if (refreshed) {
            try {
              return await this.fetchMe(refreshed);
            } catch (retryError) {
              if (axios.isAxiosError(retryError) && retryError.response?.status === 401) {
                clearToken();
                return null;
              }
              throw new Error(
                (axios.isAxiosError(retryError) && retryError.response?.data?.detail) ||
                  'Failed to get user info'
              );
            }
          }
        }
        clearToken();
        return null;
      }
      throw new Error(
        (axios.isAxiosError(error) && error.response?.data?.detail) || 'Failed to get user info'
      );
    }
  }

  /**
   * Email/password login. On success stores the JWT and returns the user; if the
   * account has two-step verification enabled the backend returns a challenge
   * instead of tokens, which we surface as `{ mfaRequired: true, mfaToken }` so
   * the caller can prompt for a code (ISSUE-202). No token is stored until the
   * second factor is verified at `completeMfaLogin`.
   */
  async login(email: string, password: string): Promise<LoginResult> {
    try {
      const response = await this.client.post<LoginResponse | MfaChallenge>(
        `${this.getBaseURL()}/api/v1/auth/login`,
        { email, password }
      );
      if (isMfaChallenge(response.data)) {
        return { mfaRequired: true, mfaToken: response.data.mfa_token };
      }
      setToken(response.data.token);
      purgeLegacyRefreshToken();
      return { mfaRequired: false, user: response.data.user };
    } catch (error) {
      throw new Error(
        (axios.isAxiosError(error) && error.response?.data?.detail) || 'Invalid email or password'
      );
    }
  }

  /**
   * Complete a two-step login: exchange the challenge ticket + a code (a current
   * TOTP code or a single-use recovery code) for tokens. Stores the JWT and
   * returns the user (ISSUE-202).
   */
  async completeMfaLogin(mfaToken: string, code: string): Promise<AuthUser> {
    try {
      const response = await this.client.post<LoginResponse>(
        `${this.getBaseURL()}/api/v1/auth/login/mfa`,
        { mfa_token: mfaToken, code }
      );
      setToken(response.data.token);
      purgeLegacyRefreshToken();
      return response.data.user;
    } catch (error) {
      throw new Error(
        (axios.isAxiosError(error) && error.response?.data?.detail) || 'Invalid verification code'
      );
    }
  }

  /**
   * Mint a fresh access token. The refresh token is no longer held in JS — it
   * rides the HttpOnly cookie, so we send an empty body with credentials and let
   * the backend read it from there. Gated on an existing access token so a
   * logged-out app makes no needless call.
   */
  async refreshAccessToken(): Promise<boolean> {
    if (!getToken()) return false;
    try {
      const response = await this.client.post<{ token: string }>(
        `${this.getBaseURL()}/api/v1/auth/refresh`,
        {}
      );
      setToken(response.data.token);
      return true;
    } catch {
      return false;
    }
  }

  /** Register a new account. Stores the JWT and returns the user. */
  async register(email: string, password: string, name?: string): Promise<AuthUser> {
    try {
      const response = await this.client.post<LoginResponse>(
        `${this.getBaseURL()}/api/v1/auth/register`,
        { email, password, name }
      );
      setToken(response.data.token);
      purgeLegacyRefreshToken();
      return response.data.user;
    } catch (error) {
      throw new Error(
        (axios.isAxiosError(error) && error.response?.data?.detail) || 'Registration failed'
      );
    }
  }

  /** Discard the local session and revoke the tokens server-side. */
  async logout(): Promise<void> {
    const token = getToken();
    try {
      await this.client.post(
        `${this.getBaseURL()}/api/v1/auth/logout`,
        // The refresh token rides the HttpOnly cookie (sent via withCredentials);
        // the server revokes it and expires the cookie. Without revocation the
        // session could be resurrected via /auth/refresh after logout.
        {},
        token ? { headers: { Authorization: `Bearer ${token}` } } : undefined
      );
    } catch {
      /* logout is best-effort */
    }
    clearToken();
    purgeLegacyRefreshToken();
  }
}

export const authApi = new LocalAuthApi();
