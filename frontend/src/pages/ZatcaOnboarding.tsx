import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  getZatcaStatus,
  onboardGenerateCsr,
  onboardComplianceCsid,
  onboardProductionCsid,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { CheckCircle2, KeyRound, ShieldCheck, FileSignature, Loader2 } from 'lucide-react';

// ISSUE-018: in-app ZATCA onboarding wizard. Walks the merchant through the
// three Fatoora steps against the existing per-client endpoints —
// CSR generation -> compliance CSID (CSR + portal OTP) -> production CSID —
// surfacing each step's failure rather than swallowing it. On completion it
// calls `onComplete` so the host page can refresh its onboarded/gateway state.

type Step = 'csr' | 'otp' | 'production' | 'done';

interface ZatcaOnboardingProps {
  onComplete?: () => void;
}

function errorDetail(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return detail || fallback;
}

export default function ZatcaOnboarding({ onComplete }: ZatcaOnboardingProps) {
  const { t } = useLanguage();

  const [step, setStep] = useState<Step>('csr');
  const [gatewayConfigured, setGatewayConfigured] = useState(true);
  const [otp, setOtp] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Resume at the right step: a generated CSR means step 1 is already done.
  useEffect(() => {
    let active = true;
    getZatcaStatus()
      .then((status) => {
        if (!active) return;
        setGatewayConfigured(status.gateway_configured);
        if (status.onboarded) setStep('done');
        else if (status.has_csr) setStep('otp');
      })
      .catch(() => {
        // A status failure leaves the wizard at the CSR step; the action itself
        // will surface any real error when attempted.
      });
    return () => {
      active = false;
    };
  }, []);

  const runStep = useCallback(
    async (fn: () => Promise<void>) => {
      setBusy(true);
      setError(null);
      try {
        await fn();
      } catch (err: unknown) {
        setError(errorDetail(err, t('zatca_onboarding_error')));
      } finally {
        setBusy(false);
      }
    },
    [t]
  );

  const handleGenerateCsr = () =>
    runStep(async () => {
      await onboardGenerateCsr();
      setNotice(t('zatca_csr_generated'));
      setStep('otp');
    });

  const handleSubmitOtp = () =>
    runStep(async () => {
      await onboardComplianceCsid(otp.trim());
      setNotice(t('zatca_compliance_done'));
      setStep('production');
    });

  const handleProduction = () =>
    runStep(async () => {
      await onboardProductionCsid();
      setNotice(t('zatca_onboarding_complete'));
      setStep('done');
      onComplete?.();
    });

  if (step === 'done') {
    return (
      <div className="dxr-tile p-6 flex items-center gap-3 text-success">
        <CheckCircle2 className="h-6 w-6 shrink-0" />
        <span className="text-sm">{t('zatca_onboarding_complete')}</span>
      </div>
    );
  }

  const steps: { key: Step; label: string; icon: typeof KeyRound }[] = [
    { key: 'csr', label: t('zatca_step_csr'), icon: KeyRound },
    { key: 'otp', label: t('zatca_step_otp'), icon: ShieldCheck },
    { key: 'production', label: t('zatca_step_production'), icon: FileSignature },
  ];
  const activeIndex = steps.findIndex((s) => s.key === step);

  return (
    <div className="dxr-tile p-6 space-y-5">
      <div>
          <h3 className="text-foreground font-semibold flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-brand" />
            {t('zatca_onboarding_title')}
          </h3>
          <p className="text-muted-foreground text-sm mt-1">{t('zatca_onboarding_desc')}</p>
        </div>

        {/* Step rail */}
        <ol className="flex flex-wrap gap-2 text-xs">
          {steps.map((s, i) => {
            const Icon = s.icon;
            const state =
              i < activeIndex ? 'done' : i === activeIndex ? 'active' : 'todo';
            return (
              <li
                key={s.key}
                className={
                  'flex items-center gap-1.5 rounded-full px-3 py-1 border ' +
                  (state === 'active'
                    ? 'border-brand text-brand bg-brand/10'
                    : state === 'done'
                      ? 'border-success/40 text-success bg-success/10'
                      : 'border-input text-muted-foreground')
                }
              >
                {state === 'done' ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Icon className="h-3.5 w-3.5" />}
                {s.label}
              </li>
            );
          })}
        </ol>

        {!gatewayConfigured && (
          <p className="text-warning text-sm" role="status">
            {t('zatca_gateway_required')}
          </p>
        )}

        {notice && (
          <p className="text-foreground/90 text-sm" role="status">
            {notice}
          </p>
        )}

        {error && (
          <p className="text-danger text-sm" role="alert">
            {error}
          </p>
        )}

        {/* CSR step */}
        {step === 'csr' && (
          <div className="space-y-3">
            <p className="text-muted-foreground text-sm">{t('zatca_step_csr_desc')}</p>
            <Button
              onClick={handleGenerateCsr}
              disabled={busy}
              className="shadow-brand"
            >
              {busy ? <Loader2 className="h-4 w-4 me-2 animate-spin" /> : <KeyRound className="h-4 w-4 me-2" />}
              {t('zatca_generate_csr')}
            </Button>
          </div>
        )}

        {/* OTP / compliance-CSID step */}
        {step === 'otp' && (
          <div className="space-y-3">
            <p className="text-muted-foreground text-sm">{t('zatca_step_otp_desc')}</p>
            <label className="block text-sm text-foreground/90" htmlFor="zatca-otp">
              {t('zatca_otp_label')}
            </label>
            <Input
              id="zatca-otp"
              type="text"
              inputMode="numeric"
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              placeholder={t('zatca_otp_placeholder')}
              className="max-w-xs"
            />
            <div>
              <Button
                onClick={handleSubmitOtp}
                disabled={busy || otp.trim().length === 0}
                className="shadow-brand"
              >
                {busy ? <Loader2 className="h-4 w-4 me-2 animate-spin" /> : <ShieldCheck className="h-4 w-4 me-2" />}
                {t('zatca_submit_otp')}
              </Button>
            </div>
          </div>
        )}

        {/* Production-CSID step */}
        {step === 'production' && (
          <div className="space-y-3">
            <p className="text-muted-foreground text-sm">{t('zatca_step_production_desc')}</p>
            <Button
              onClick={handleProduction}
              disabled={busy}
              className="shadow-brand"
            >
              {busy ? <Loader2 className="h-4 w-4 me-2 animate-spin" /> : <FileSignature className="h-4 w-4 me-2" />}
              {t('zatca_finish_onboarding')}
            </Button>
          </div>
        )}
    </div>
  );
}
