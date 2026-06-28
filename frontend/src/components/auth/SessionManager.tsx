import { useCallback, useEffect, useState } from 'react';
import { Loader2, Monitor, Smartphone, ShieldOff } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import LoadingState from '@/components/states/LoadingState';
import ErrorState from '@/components/states/ErrorState';
import EmptyState from '@/components/states/EmptyState';
import {
  getActiveSessions,
  revokeSession,
  revokeOtherSessions,
  type SessionInfo,
} from '@/lib/api';
import { notifyError } from '@/lib/notify';
import { useLanguage } from '@/lib/i18n';
import { formatDateTime } from '@/lib/format';

/** A coarse, dependency-free label from a user-agent string for the row title. */
function deviceLabel(ua: string | null, fallback: string): string {
  if (!ua) return fallback;
  const os =
    /Windows/i.test(ua) ? 'Windows' :
    /iPhone|iPad|iOS/i.test(ua) ? 'iOS' :
    /Android/i.test(ua) ? 'Android' :
    /Mac OS X|Macintosh/i.test(ua) ? 'macOS' :
    /Linux/i.test(ua) ? 'Linux' : '';
  const browser =
    /Edg\//i.test(ua) ? 'Edge' :
    /OPR\/|Opera/i.test(ua) ? 'Opera' :
    /Chrome\//i.test(ua) ? 'Chrome' :
    /Firefox\//i.test(ua) ? 'Firefox' :
    /Safari\//i.test(ua) ? 'Safari' : '';
  const label = [browser, os].filter(Boolean).join(' · ');
  return label || fallback;
}

function isMobile(ua: string | null): boolean {
  return !!ua && /Mobi|Android|iPhone|iPad/i.test(ua);
}

/**
 * Active-session list + revoke (ISSUE-202, backend #83). Replaces the static
 * "Current Session — Active now" placeholder that always claimed one live session
 * regardless of reality: this lists the caller's real sessions, flags the current
 * one, and lets them revoke a single session or every other one.
 */
export default function SessionManager() {
  const { t, tt, language } = useLanguage();
  const [sessions, setSessions] = useState<SessionInfo[] | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  // The session id pending single-revoke confirmation, or 'others' for the bulk
  // action; null when no dialog is open.
  const [pending, setPending] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setSessions(await getActiveSessions());
    } catch (err) {
      setError(true);
      notifyError(err, tt('sessions_load_failed', 'Could not load your active sessions.'));
    } finally {
      setLoading(false);
    }
  }, [tt]);

  useEffect(() => {
    void load();
  }, [load]);

  async function confirmRevoke() {
    if (!pending) return;
    setBusy(true);
    try {
      if (pending === 'others') {
        const revoked = await revokeOtherSessions();
        toast.success(
          tt('sessions_others_revoked', 'Signed out other sessions') + ` (${revoked})`
        );
      } else {
        await revokeSession(pending);
        toast.success(tt('session_revoked', 'Session signed out'));
      }
      setPending(null);
      await load();
    } catch (err) {
      notifyError(err, tt('session_revoke_failed', 'Could not sign out that session.'));
    } finally {
      setBusy(false);
    }
  }

  const otherCount = sessions ? sessions.filter((s) => !s.current).length : 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-foreground text-sm font-medium">
            {tt('active_sessions', 'Active sessions')}
          </p>
          <p className="text-muted-foreground text-xs">
            {tt('active_sessions_desc', 'Devices currently signed in to your account.')}
          </p>
        </div>
        {otherCount > 0 && (
          <Button
            variant="outline"
            size="sm"
            className="text-danger"
            onClick={() => setPending('others')}
          >
            <ShieldOff className="h-4 w-4 me-2" />
            {tt('sign_out_others', 'Sign out others')}
          </Button>
        )}
      </div>

      {loading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState
          message={tt('sessions_load_failed', 'Could not load your active sessions.')}
          onRetry={() => void load()}
        />
      ) : !sessions || sessions.length === 0 ? (
        <EmptyState
          icon={Monitor}
          message={tt('no_active_sessions', 'No other active sessions')}
        />
      ) : (
        <ul className="divide-y divide-border">
          {sessions.map((s) => {
            const Icon = isMobile(s.user_agent) ? Smartphone : Monitor;
            return (
              <li key={s.id} className="flex items-center justify-between gap-3 py-3">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="dxr-sw dxr-sw-brand h-9 w-9 shrink-0">
                    <Icon className="h-[18px] w-[18px]" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">
                      {deviceLabel(s.user_agent, tt('unknown_device', 'Unknown device'))}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {[
                        s.ip_address,
                        s.last_used_at
                          ? `${tt('last_active', 'Last active')} ${formatDateTime(s.last_used_at, language)}`
                          : null,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </p>
                  </div>
                </div>
                {s.current ? (
                  <Badge className="pill-success shrink-0">{tt('this_device', 'This device')}</Badge>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="shrink-0 text-danger hover:text-danger"
                    onClick={() => setPending(s.id)}
                  >
                    {tt('revoke', 'Revoke')}
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pending === 'others'
                ? tt('sign_out_others', 'Sign out others')
                : tt('revoke_session', 'Revoke session')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pending === 'others'
                ? tt(
                    'sign_out_others_confirm',
                    'This signs out every session except this one. Those devices will need to sign in again.'
                  )
                : tt(
                    'revoke_session_confirm',
                    'This signs out the selected device. It will need to sign in again.'
                  )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                void confirmRevoke();
              }}
              disabled={busy}
              className="bg-danger text-danger-foreground hover:bg-danger/90"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : tt('sign_out', 'Sign out')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
