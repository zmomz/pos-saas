import { describe, it, expect, vi, beforeEach } from 'vitest';

// FE-06: resolveTenancyRole must never silently downgrade a master/agent to the
// least-privileged 'client' role on a transport error. Mock the role endpoint so
// we can drive success / transient-failure paths deterministically.
vi.mock('../lib/api', () => ({
  getRole: vi.fn(),
}));

import { resolveTenancyRole } from './AuthContext';
import { getRole } from '../lib/api';

const mockedGetRole = vi.mocked(getRole);

describe('resolveTenancyRole', () => {
  beforeEach(() => {
    mockedGetRole.mockReset();
  });

  it('returns the resolved role on success', async () => {
    mockedGetRole.mockResolvedValue({ role: 'master' });
    await expect(resolveTenancyRole(2, 0)).resolves.toBe('master');
  });

  it('defaults to client only when the backend itself reports no role', async () => {
    mockedGetRole.mockResolvedValue({});
    await expect(resolveTenancyRole(2, 0)).resolves.toBe('client');
  });

  it('throws (never downgrades to client) when every attempt fails', async () => {
    mockedGetRole.mockRejectedValue(new Error('Network Error'));
    await expect(resolveTenancyRole(2, 0)).rejects.toThrow('Network Error');
    // 1 initial attempt + 2 retries
    expect(mockedGetRole).toHaveBeenCalledTimes(3);
  });

  it('retries past a transient failure and returns the real role', async () => {
    mockedGetRole
      .mockRejectedValueOnce(new Error('Network Error'))
      .mockResolvedValueOnce({ role: 'agent' });
    await expect(resolveTenancyRole(2, 0)).resolves.toBe('agent');
    expect(mockedGetRole).toHaveBeenCalledTimes(2);
  });
});
