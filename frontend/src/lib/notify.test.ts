import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';
import { errorMessage, notifyError } from './notify';

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

describe('errorMessage', () => {
  it('returns the FastAPI detail string when present', () => {
    expect(
      errorMessage({ response: { data: { detail: 'Insufficient stock' } } }, 'Checkout failed')
    ).toBe('Insufficient stock');
  });

  it('falls back when the error carries no usable string detail', () => {
    // a plain Error has no response.data.detail
    expect(errorMessage(new Error('boom'), 'Checkout failed')).toBe('Checkout failed');
  });

  it('falls back when detail is a non-string (e.g. FastAPI validation array)', () => {
    expect(
      errorMessage({ response: { data: { detail: [{ msg: 'x' }] } } }, 'Checkout failed')
    ).toBe('Checkout failed');
  });
});

describe('notifyError', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows a toast with the server detail when available', () => {
    notifyError({ response: { data: { detail: 'Insufficient stock' } } }, 'Checkout failed');
    expect(toast.error).toHaveBeenCalledWith('Insufficient stock');
  });

  it('shows a toast with the fallback when no detail is present', () => {
    notifyError(new Error('boom'), 'Checkout failed');
    expect(toast.error).toHaveBeenCalledWith('Checkout failed');
  });
});
