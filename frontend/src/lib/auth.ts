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

  /** Return the current user, or null if not authenticated. */
  async getCurrentUser(): Promise<AuthUser | null> {
    const token = getToken();
    if (!token) return null;
    try {
      const response = await this.client.get(`${this.getBaseURL()}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return response.data;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 401) {
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
