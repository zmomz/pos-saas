import { useEffect, useState } from 'react';
import { Loader2, KeyRound, Copy, Check, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import OtpField from '@/components/auth/OtpField';
import LoadingState from '@/components/states/LoadingState';
import ErrorState from '@/components/states/ErrorState';
import {
  getMfaStatus,
  enrollMfa,
  activateMfa,
  type MfaStatus,
  type MfaEnrollment,
} from '@/lib/api';
import { notifyError } from '@/lib/notify';
import { useLanguage } from '@/lib/i18n';

type Step = 'idle' | 'enroll' | 'codes';

/**
 * Two-step verification enrollment + status (ISSUE-202, backend #81). Shows
 * whether MFA is on; when off, walks the user through loading the shared secret
 * into an authenticator app and confirming a code, then reveals the one-time
 * recovery codes. A QR library is intentionally not pulled in — the base32 secret
 * is shown for manual entry (every authenticator app supports it).
 */
export default function MfaSettings() {
  const { t, tt } = useLanguage();
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [loading, setLoading] = useState(true);

  const [step, setStep] = useState<Step>('idle');
  const [enrollment, setEnrollment] = useState<MfaEnrollment | null>(null);
  const [code, setCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [activateError, setActivateError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function loadStatus() {
    setLoading(true);
    setLoadError(false);
    try {
      setStatus(await getMfaStatus());
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadStatus();
  }, []);

  async function startEnroll() {
    setBusy(true);
    setActivateError(null);
    try {
      const data = await enrollMfa();
      setEnrollment(data);
      setCode('');
      setStep('enroll');
    } catch (err) {
      notifyError(err, tt('mfa_enroll_failed', 'Could not start two-step setup.'));
    } finally {
      setBusy(false);
    }
  }

  async function confirmActivate(submittedCode: string) {
    const trimmed = submittedCode.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setActivateError(null);
    try {
      const result = await activateMfa(trimmed);
      setRecoveryCodes(result.recovery_codes);
      setStep('codes');
      toast.success(tt('mfa_enabled', 'Two-step verification is on'));
    } catch (err) {
      setActivateError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          tt('mfa_invalid_code', 'That code did not match. Try the current one.')
      );
      setCode('');
    } finally {
      setBusy(false);
    }
  }

  function finishSetup() {
    setStep('idle');
    setEnrollment(null);
    setRecoveryCodes([]);
    setCode('');
    void loadStatus();
  }

  async function copySecret(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard may be unavailable; the secret is visible to type manually */
    }
  }

  if (loading) return <LoadingState />;
  if (loadError) {
    return (
      <ErrorState
        message={tt('mfa_status_failed', 'Could not load two-step status.')}
        onRetry={() => void loadStatus()}
      />
    );
  }

  // Recovery codes — shown once, after activation.
  if (step === 'codes') {
    return (
      <div className="space-y-3">
        <p className="text-foreground text-sm font-medium">
          {tt('mfa_recovery_codes', 'Save your recovery codes')}
        </p>
        <p className="text-muted-foreground text-xs">
          {tt(
            'mfa_recovery_codes_desc',
            'Store these somewhere safe. Each code works once if you lose your authenticator. They are shown only now.'
          )}
        </p>
        <ul className="grid grid-cols-2 gap-2 rounded-lg border border-border bg-muted/40 p-3 font-mono text-sm">
          {recoveryCodes.map((rc) => (
            <li key={rc} className="text-center tracking-widest text-foreground">
              {rc}
            </li>
          ))}
        </ul>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void copySecret(recoveryCodes.join('\n'))}
          >
            {copied ? <Check className="h-4 w-4 me-2" /> : <Copy className="h-4 w-4 me-2" />}
            {copied ? tt('copied', 'Copied') : t('copy')}
          </Button>
          <Button size="sm" onClick={finishSetup}>
            {tt('mfa_saved_codes', "I've saved them")}
          </Button>
        </div>
      </div>
    );
  }

  // Enrollment — load the secret, then confirm a code.
  if (step === 'enroll' && enrollment) {
    return (
      <div className="space-y-3">
        <p className="text-foreground text-sm font-medium">
          {tt('mfa_setup_title', 'Set up your authenticator')}
        </p>
        <p className="text-muted-foreground text-xs">
          {tt(
            'mfa_setup_desc',
            'Add this key to your authenticator app (Google Authenticator, 1Password, …), then enter the 6-digit code it shows.'
          )}
        </p>
        <div className="flex items-center gap-2">
          <code className="flex-1 break-all rounded-lg border border-border bg-muted/40 px-3 py-2 font-mono text-sm tracking-wider text-foreground">
            {enrollment.secret}
          </code>
          <Button
            variant="outline"
            size="icon"
            aria-label={t('copy')}
            onClick={() => void copySecret(enrollment.secret)}
          >
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          </Button>
        </div>

        <div className="space-y-2 pt-1">
          <OtpField
            value={code}
            onChange={setCode}
            onComplete={(v) => void confirmActivate(v)}
            disabled={busy}
            aria-label={tt('mfa_setup_title', 'Set up your authenticator')}
          />
          {activateError && <p className="text-center text-sm text-danger">{activateError}</p>}
        </div>

        <div className="flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setStep('idle');
              setEnrollment(null);
              setCode('');
              setActivateError(null);
            }}
            disabled={busy}
          >
            {t('cancel')}
          </Button>
          <Button
            size="sm"
            onClick={() => void confirmActivate(code)}
            disabled={busy || code.trim().length < 6}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : tt('mfa_verify', 'Verify')}
          </Button>
        </div>
      </div>
    );
  }

  // Idle — current status + the entry point.
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-3">
        <span className="dxr-sw dxr-sw-brand h-9 w-9 shrink-0">
          <KeyRound className="h-[18px] w-[18px]" />
        </span>
        <div className="min-w-0">
          <p className="text-foreground text-sm font-medium">
            {tt('mfa_title', 'Two-step verification')}
          </p>
          <p className="text-muted-foreground text-xs">
            {status?.enabled
              ? tt('mfa_on_desc', 'A code from your authenticator is required at sign in.') +
                ` · ${status.recovery_codes_remaining} ${tt('mfa_codes_left', 'recovery codes left')}`
              : tt('mfa_off_desc', 'Add a second factor to protect your account at sign in.')}
          </p>
        </div>
      </div>
      {status?.enabled ? (
        <Badge className="pill-success shrink-0">
          <ShieldCheck className="h-3.5 w-3.5 me-1" />
          {tt('mfa_on', 'On')}
        </Badge>
      ) : (
        <Button size="sm" onClick={() => void startEnroll()} disabled={busy} className="shrink-0">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : tt('mfa_setup', 'Set up')}
        </Button>
      )}
    </div>
  );
}
