/**
 * Agent 3 Session Adapter Tests
 *
 * Tests for secure session adapter and token management.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getAgent3Session, hasValidAgent3Session, SessionError } from '../auth/agent3Session';

// Mock Supabase client
vi.mock('../../../services/supabaseClient', () => ({
  supabase: {
    auth: {
      getSession: vi.fn()
    }
  }
}));

import { supabase } from '../../../services/supabaseClient';

describe('Agent 3 Session Adapter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getAgent3Session', () => {
    it('should return session data when valid session exists', async () => {
      const mockSession = {
        access_token: 'test-token',
        refresh_token: 'refresh-token',
        expires_in: 3600,
        token_type: 'bearer' as const,
        user: {
          id: '00000000-0000-0000-0000-000000000001',
          app_metadata: {
            tenant_id: '00000000-0000-0000-0000-000000000002'
          }
        }
      } as any;

      vi.mocked(supabase.auth.getSession).mockResolvedValue({
        data: { session: mockSession },
        error: null
      });

      const sessionData = await getAgent3Session();

      expect(sessionData.requesterId).toBe('00000000-0000-0000-0000-000000000001');
      expect(sessionData.tenantId).toBe('00000000-0000-0000-0000-000000000002');
      expect(sessionData.accessToken).toBe('test-token');
    });

    it('should fail when no session exists', async () => {
      vi.mocked(supabase.auth.getSession).mockResolvedValue({
        data: { session: null },
        error: null
      });

      await expect(getAgent3Session()).rejects.toThrow(SessionError);
      await expect(getAgent3Session()).rejects.toThrow('No authenticated session exists');
    });

    it('should fail when access token is missing', async () => {
      const mockSession = {
        access_token: null,
        user: {
          id: '00000000-0000-0000-0000-000000000001',
          app_metadata: {
            tenant_id: '00000000-0000-0000-0000-000000000002'
          }
        }
      } as any;

      vi.mocked(supabase.auth.getSession).mockResolvedValue({
        data: { session: mockSession },
        error: null
      });

      await expect(getAgent3Session()).rejects.toThrow('Access token is missing from session');
    });

    it('should fail when user data is missing', async () => {
      const mockSession = {
        access_token: 'test-token',
        user: null
      } as any;

      vi.mocked(supabase.auth.getSession).mockResolvedValue({
        data: { session: mockSession },
        error: null
      });

      await expect(getAgent3Session()).rejects.toThrow('User data is missing from session');
    });

    it('should fail when requester ID is invalid', async () => {
      const mockSession = {
        access_token: 'test-token',
        user: {
          id: 'invalid-uuid',
          app_metadata: {
            tenant_id: '00000000-0000-0000-0000-000000000002'
          }
        }
      } as any;

      vi.mocked(supabase.auth.getSession).mockResolvedValue({
        data: { session: mockSession },
        error: null
      });

      await expect(getAgent3Session()).rejects.toThrow('Invalid requester ID in session');
    });

    it('should fail when tenant ID is missing from app_metadata', async () => {
      const mockSession = {
        access_token: 'test-token',
        user: {
          id: '00000000-0000-0000-0000-000000000001',
          app_metadata: {}
        }
      } as any;

      vi.mocked(supabase.auth.getSession).mockResolvedValue({
        data: { session: mockSession },
        error: null
      });

      await expect(getAgent3Session()).rejects.toThrow('Invalid or missing tenant ID in session app_metadata');
    });

    it('should fail when tenant ID is invalid', async () => {
      const mockSession = {
        access_token: 'test-token',
        user: {
          id: '00000000-0000-0000-0000-000000000001',
          app_metadata: {
            tenant_id: 'invalid-uuid'
          }
        }
      } as any;

      vi.mocked(supabase.auth.getSession).mockResolvedValue({
        data: { session: mockSession },
        error: null
      });

      await expect(getAgent3Session()).rejects.toThrow('Invalid or missing tenant ID in session app_metadata');
    });

    it('should ignore user_metadata.tenant_id and only use app_metadata.tenant_id', async () => {
      const mockSession = {
        access_token: 'test-token',
        user: {
          id: '00000000-0000-0000-0000-000000000001',
          user_metadata: {
            tenant_id: '00000000-0000-0000-0000-000000000999' // Should be ignored
          },
          app_metadata: {
            tenant_id: '00000000-0000-0000-0000-000000000002' // Should be used
          }
        }
      } as any;

      vi.mocked(supabase.auth.getSession).mockResolvedValue({
        data: { session: mockSession },
        error: null
      });

      const sessionData = await getAgent3Session();

      expect(sessionData.tenantId).toBe('00000000-0000-0000-0000-000000000002');
    });

    it('should provide a fresh complete snapshot on each adapter call', async () => {
      const mockSession = {
        access_token: 'test-token-v1',
        user: {
          id: '00000000-0000-0000-0000-000000000001',
          app_metadata: {
            tenant_id: '00000000-0000-0000-0000-000000000002'
          }
        }
      } as any;

      vi.mocked(supabase.auth.getSession).mockResolvedValue({
        data: { session: mockSession },
        error: null
      });

      const firstSnapshot = await getAgent3Session();
      mockSession.access_token = 'test-token-v2';
      const secondSnapshot = await getAgent3Session();

      expect(firstSnapshot.accessToken).toBe('test-token-v1');
      expect(secondSnapshot.accessToken).toBe('test-token-v2');
    });
  });

  describe('hasValidAgent3Session', () => {
    it('should return true when valid session exists', async () => {
      const mockSession = {
        access_token: 'test-token',
        user: {
          id: '00000000-0000-0000-0000-000000000001',
          app_metadata: {
            tenant_id: '00000000-0000-0000-0000-000000000002'
          }
        }
      } as any;

      vi.mocked(supabase.auth.getSession).mockResolvedValue({
        data: { session: mockSession },
        error: null
      });

      const hasSession = await hasValidAgent3Session();
      expect(hasSession).toBe(true);
    });

    it('should return false when session is invalid', async () => {
      vi.mocked(supabase.auth.getSession).mockResolvedValue({
        data: { session: null },
        error: null
      });

      const hasSession = await hasValidAgent3Session();
      expect(hasSession).toBe(false);
    });

    it('should return false when session error occurs', async () => {
      vi.mocked(supabase.auth.getSession).mockResolvedValue({
        data: { session: null },
        error: new Error('Session error') as any
      });

      const hasSession = await hasValidAgent3Session();
      expect(hasSession).toBe(false);
    });
  });
});
