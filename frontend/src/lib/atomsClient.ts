/**
 * Local drop-in replacement for the former `@metagptx/web-sdk` client.
 *
 * It reproduces the exact surface the app relies on:
 *   client.apiCall.invoke({ url, method, data })
 *   client.entities.<name>.{ query, queryAll, create, update, delete }
 *   client.auth.{ me, login, toLogin, logout }
 *
 * Auth is local email/password: the JWT issued by the backend is stored in
 * localStorage and attached as a Bearer token on every request.
 */
import axios, { AxiosInstance, Method } from 'axios';
import { getAPIBaseURL } from './config';

const TOKEN_KEY = 'pos_auth_token';
const LOGIN_PATH = '/login';

// ---------- Token storage ----------
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

// ---------- Shared axios instance ----------
function makeHttp(): AxiosInstance {
  const http = axios.create({ headers: { 'Content-Type': 'application/json' } });
  http.interceptors.request.use((config) => {
    config.baseURL = getAPIBaseURL();
    const token = getToken();
    if (token) {
      config.headers = config.headers ?? {};
      (config.headers as Record<string, string>).Authorization = `Bearer ${token}`;
    }
    return config;
  });
  // Phase 3: handle production-hardening responses gracefully.
  //  - 401 after token revocation/expiry → clear the session and bounce to login
  //    (skip auth probe endpoints, which callers handle, and avoid redirect loops).
  //  - 429 rate-limited → broadcast an event the UI can toast on.
  http.interceptors.response.use(
    (response) => response,
    (error) => {
      const status = error?.response?.status;
      const url: string = error?.config?.url ?? '';
      if (status === 401) {
        const isAuthProbe = url.includes('/api/v1/auth/me') || url.includes('/api/v1/auth/login');
        const onLogin = typeof window !== 'undefined' && window.location.pathname === LOGIN_PATH;
        if (!isAuthProbe && !onLogin) {
          clearToken();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('pos:session-expired'));
            window.location.assign(LOGIN_PATH);
          }
        }
      } else if (status === 429) {
        if (typeof window !== 'undefined') {
          const retryAfter = error?.response?.headers?.['retry-after'];
          window.dispatchEvent(
            new CustomEvent('pos:rate-limited', { detail: { retryAfter } })
          );
        }
      }
      return Promise.reject(error);
    }
  );
  return http;
}

const http = makeHttp();

type InvokeArgs = {
  url: string;
  method?: Method | string;
  data?: Record<string, unknown>;
};

type SdkResponse<T = unknown> = { data: T };

async function invoke<T = unknown>({ url, method = 'GET', data }: InvokeArgs): Promise<SdkResponse<T>> {
  const m = String(method).toUpperCase();
  const isBodyless = m === 'GET' || m === 'DELETE' || m === 'HEAD';
  const response = await http.request<T>({
    url,
    method: m as Method,
    params: isBodyless ? data : undefined,
    data: isBodyless ? undefined : data,
  });
  return { data: response.data };
}

// ---------- Entities (generic CRUD under /api/v1/entities/<name>) ----------
type QueryArgs = {
  query?: Record<string, unknown>;
  sort?: string;
  skip?: number;
  limit?: number;
  fields?: string;
};

function buildEntity(name: string) {
  const base = `/api/v1/entities/${name}`;

  function listParams(args: QueryArgs = {}) {
    const params: Record<string, unknown> = {};
    if (args.query !== undefined) params.query = JSON.stringify(args.query);
    if (args.sort !== undefined) params.sort = args.sort;
    if (args.skip !== undefined) params.skip = args.skip;
    if (args.limit !== undefined) params.limit = args.limit;
    if (args.fields !== undefined) params.fields = args.fields;
    return params;
  }

  return {
    async query<T = unknown>(args: QueryArgs = {}): Promise<SdkResponse<T>> {
      const res = await http.get<T>(base, { params: listParams(args) });
      return { data: res.data };
    },
    async queryAll<T = unknown>(args: QueryArgs = {}): Promise<SdkResponse<T>> {
      const res = await http.get<T>(`${base}/all`, { params: listParams(args) });
      return { data: res.data };
    },
    async create<T = unknown>(args: { data: Record<string, unknown> }): Promise<SdkResponse<T>> {
      const res = await http.post<T>(base, args.data);
      return { data: res.data };
    },
    async update<T = unknown>(args: { id: string | number; data: Record<string, unknown> }): Promise<SdkResponse<T>> {
      const res = await http.put<T>(`${base}/${args.id}`, args.data);
      return { data: res.data };
    },
    async delete<T = unknown>(args: { id: string | number }): Promise<SdkResponse<T>> {
      const res = await http.delete<T>(`${base}/${args.id}`);
      return { data: res.data };
    },
  };
}

type Entity = ReturnType<typeof buildEntity>;

const entities = new Proxy({} as Record<string, Entity>, {
  get(cache, name: string) {
    if (!(name in cache)) {
      cache[name] = buildEntity(name);
    }
    return cache[name];
  },
});

// ---------- Auth ----------
const auth = {
  /** Fetch the current user; returns { data: null } when unauthenticated. */
  async me<T = unknown>(): Promise<SdkResponse<T | null>> {
    if (!getToken()) return { data: null };
    try {
      const res = await http.get<T>('/api/v1/auth/me');
      return { data: res.data };
    } catch {
      return { data: null };
    }
  },

  /**
   * Post-redirect handler retained for backwards compatibility. If a token was
   * passed back in the URL fragment (#token=...), store it; then go home.
   */
  async login(): Promise<void> {
    const hash = window.location.hash?.replace(/^#/, '') ?? '';
    const params = new URLSearchParams(hash);
    const token = params.get('token');
    if (token) setToken(token);
    window.location.replace('/');
  },

  /** Send the user to the login screen. */
  toLogin(): void {
    window.location.assign(LOGIN_PATH);
  },

  /** Clear the session and return to the login screen. */
  async logout(): Promise<void> {
    try {
      await http.post('/api/v1/auth/logout');
    } catch {
      /* ignore */
    }
    clearToken();
    window.location.assign(LOGIN_PATH);
  },
};

export function createClient() {
  return {
    apiCall: { invoke },
    entities,
    auth,
  };
}

export type LocalClient = ReturnType<typeof createClient>;
