import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';

/**
 * Shared MSW server for component tests that exercise the API layer. Tests add
 * per-case handlers with `server.use(...)`. Import `http`/`HttpResponse` from
 * here for convenience.
 */
export const server = setupServer();

export { http, HttpResponse };
