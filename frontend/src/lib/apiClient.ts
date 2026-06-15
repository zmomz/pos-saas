/**
 * Local HTTP client (formerly the `@metagptx/web-sdk` drop-in `atomsClient`).
 *
 * It reproduces the exact surface the app relies on:
 *   client.apiCall.invoke({ url, method, data })
 *   client.entities.<name>.{ query, queryAll, create, update, delete }
 *
 * Auth is local email/password and lives entirely in `lib/auth.ts` (`authApi`):
 * the JWT issued by the backend is stored in localStorage (token helpers below)
 * and attached as a Bearer token on every request. The old SDK `auth` shim
 * (`me`/`login`/`toLogin`) was migration cruft with no callers and is gone.
 */
import axios, { AxiosInstance, InternalAxiosRequestConfig, Method } from 'axios';
import { getAPIBaseURL } from './config';

const TOKEN_KEY = 'pos_auth_token';
const LOGIN_PATH = '/login';

// A request we've already retried once after a refresh — guards against an
// infinite refresh→replay loop when the replayed request still 401s.
type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

// Coalesce concurrent 401s onto a single in-flight refresh so a burst of
// expired requests triggers exactly one POST /auth/refresh.
let refreshPromise: Promise<boolean> | null = null;

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
  //  - 401 after token expiry → attempt one silent refresh + replay before
  //    clearing the session, so a valid refresh token keeps the user signed in
  //    past the access-token boundary (ISSUE-041). On refresh failure (or a
  //    second 401 after replay) clear the session and bounce to login. Auth
  //    probe endpoints are skipped (callers handle them) to avoid loops.
  //  - 429 rate-limited → broadcast an event the UI can toast on.
  http.interceptors.response.use(
    (response) => response,
    async (error) => {
      const status = error?.response?.status;
      const config = (error?.config ?? {}) as RetriableConfig;
      const url: string = config.url ?? '';
      if (status === 401) {
        const isAuthProbe = url.includes('/api/v1/auth/me') || url.includes('/api/v1/auth/login');
        const onLogin = typeof window !== 'undefined' && window.location.pathname === LOGIN_PATH;
        if (!isAuthProbe && !onLogin && !config._retry) {
          config._retry = true;
          // Lazy import avoids a static cycle (auth.ts imports token storage from here).
          const { authApi } = await import('./auth');
          refreshPromise = refreshPromise ?? authApi.refreshAccessToken();
          let refreshed = false;
          try {
            refreshed = await refreshPromise;
          } finally {
            refreshPromise = null;
          }
          if (refreshed) {
            // Replay the original request; the request interceptor re-attaches
            // the freshly-stored access token.
            return http.request(config);
          }
        }
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
// There is no `auth` shim on the client. All auth (login / refresh / logout /
// current-user) flows through the canonical `authApi` in lib/auth.ts, reached
// via `useAuth()`. The former SDK shims (`me`/`login`/`toLogin`/`logout`) were
// migration cruft with no callers — a divergent `logout` here POSTed no refresh
// token and left the session resurrectable (ISSUE-042); `me`/`login`/`toLogin`
// were dead (ISSUE-095). Token storage helpers (getToken/setToken/clearToken,
// above) are the only auth surface this module owns.

/** GET a binary response (e.g. a generated PDF) as a Blob, with auth attached. */
export async function getBlob(url: string): Promise<Blob> {
  const res = await http.get(url, { responseType: 'blob' });
  return res.data as Blob;
}

/** POST a multipart/form-data upload (e.g. AG-01 agent logo). Returns the body. */
export async function uploadMultipart<T = unknown>(url: string, file: File, field = 'file'): Promise<T> {
  const form = new FormData();
  form.append(field, file);
  // Let the browser set the multipart boundary; override the JSON default.
  const res = await http.post<T>(url, form, { headers: { 'Content-Type': 'multipart/form-data' } });
  return res.data;
}

export function createClient() {
  return {
    apiCall: { invoke },
    entities,
  };
}

export type LocalClient = ReturnType<typeof createClient>;
