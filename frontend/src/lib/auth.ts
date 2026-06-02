import axios, { AxiosInstance } from 'axios';
import { getAPIBaseURL } from './config';
import { setToken, clearToken, getToken } from './atomsClient';

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

function setRefreshToken(token?: string) {
  if (token) localStorage.setItem(REFRESH_TOKEN_KEY, token);
}

function clearRefreshToken() {
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

class LocalAuthApi {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      headers: { 'Content-Type': 'application/json' },
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
      setRefreshToken(response.data.refresh_token);
      return response.data.user;
    } catch (error) {
      throw new Error(
        (axios.isAxiosError(error) && error.response?.data?.detail) || 'Invalid email or password'
      );
    }
  }

  /** Exchange the stored refresh token for a new access token. */
  async refreshAccessToken(): Promise<boolean> {
    const refresh = getRefreshToken();
    if (!refresh) return false;
    try {
      const response = await this.client.post<{ token: string }>(
        `${this.getBaseURL()}/api/v1/auth/refresh`,
        { refresh_token: refresh }
      );
      setToken(response.data.token);
      return true;
    } catch {
      clearRefreshToken();
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
      setRefreshToken(response.data.refresh_token);
      return response.data.user;
    } catch (error) {
      throw new Error(
        (axios.isAxiosError(error) && error.response?.data?.detail) || 'Registration failed'
      );
    }
  }

  /** Discard the local session. */
  async logout(): Promise<void> {
    const token = getToken();
    try {
      await this.client.post(
        `${this.getBaseURL()}/api/v1/auth/logout`,
        {},
        token ? { headers: { Authorization: `Bearer ${token}` } } : undefined
      );
    } catch {
      /* logout is best-effort */
    }
    clearToken();
    clearRefreshToken();
  }
}

export const authApi = new LocalAuthApi();
