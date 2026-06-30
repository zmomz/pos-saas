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

  /** Email/password login. Stores the JWT and returns the user. */
  async login(email: string, password: string): Promise<AuthUser> {
    try {
      const response = await this.client.post<LoginResponse>(
        `${this.getBaseURL()}/api/v1/auth/login`,
        { email, password }
      );
      setToken(response.data.token);
      purgeLegacyRefreshToken();
      return response.data.user;
    } catch (error) {
      throw new Error(
        (axios.isAxiosError(error) && error.response?.data?.detail) || 'Invalid email or password'
      );
    }
  }

  /**
   * On-terminal staff PIN login (#216). The PIN is scoped to a merchant by the
   * merchant's own login email; a match mints tokens for the staff member's own
   * login, so their permissions/tenancy resolve exactly as a password login.
   */
  async loginWithPin(merchantEmail: string, pin: string): Promise<AuthUser> {
    try {
      const response = await this.client.post<LoginResponse>(
        `${this.getBaseURL()}/api/v1/auth/login/pin`,
        { merchant_email: merchantEmail, pin }
      );
      setToken(response.data.token);
      purgeLegacyRefreshToken();
      return response.data.user;
    } catch (error) {
      throw new Error(
        (axios.isAxiosError(error) && error.response?.data?.detail) || 'Invalid PIN'
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
