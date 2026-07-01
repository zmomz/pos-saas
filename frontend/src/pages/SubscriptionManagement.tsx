import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
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
import PageHeading from '@/components/dashboard/rx/PageHeading';
import LoadingState from '@/components/states/LoadingState';
import ErrorState from '@/components/states/ErrorState';
import CardOnFileDialog, { type CardOnFileToken } from '@/components/billing/CardOnFileDialog';
import AgentMoyasarBanner from '@/components/billing/AgentMoyasarBanner';
import { usePageChrome } from '@/contexts/PageChromeContext';
import { useLanguage } from '@/lib/i18n';
import { notifyError } from '@/lib/notify';
import { formatMoney, formatDate } from '@/lib/format';
import { cn } from '@/lib/utils';
import {
  getClientSubscription,
  getRenewalPreview,
  payClientSubscription,
  pauseSubscription,
  resumeSubscription,
  cancelSubscription,
  refundSubscriptionPayment,
  saveSubscriptionCard,
  downloadSubscriptionInvoice,
  type SubscriptionStatus,
  type SubscriptionPayment,
  type RenewalPreview,
} from '@/lib/api';
import {
  Wallet, CreditCard, Pause, Play, Ban, Download, Undo2, Receipt, Ticket,
} from 'lucide-react';

// Lifecycle status → pill class + label key. Paused/cancelled are the self-serve
// states (#206); the rest are the billing-engine states.
function statusPill(status: string): { cls: string; key: string } {
  switch (status) {
    case 'active':
      return { cls: 'pill-success', key: 'active' };
    case 'paused':
      return { cls: 'pill-warning', key: 'pause_billing' };
    case 'cancelled':
      return { cls: 'pill-muted', key: 'cancel_subscription' };
    case 'trialing':
      return { cls: 'pill-sky', key: 'subscription' };
    case 'suspended':
      return { cls: 'pill-danger', key: 'subscription_suspended_notice' };
    default:
      return { cls: 'pill-warning', key: 'payment_overdue_notice' };
  }
}

type PendingAction = 'pause' | 'cancel' | null;

export default function SubscriptionManagement() {
  const { t, language, isRTL } = useLanguage();
  const [sub, setSub] = useState<SubscriptionStatus | null>(null);
  const [preview, setPreview] = useState<RenewalPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [paying, setPaying] = useState(false);
  const [cardOpen, setCardOpen] = useState(false);
  const [confirm, setConfirm] = useState<PendingAction>(null);
  const [refundTarget, setRefundTarget] = useState<SubscriptionPayment | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const [s, p] = await Promise.all([
        getClientSubscription(),
        getRenewalPreview().catch(() => null),
      ]);
      setSub(s);
      setPreview(p);
    } catch (err) {
      console.error('Failed to load subscription', err);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Re-fetch the renewal preview alongside the subscription after any mutation so
  // the hero's amount/state never drifts from the lifecycle state.
  async function refresh(next: SubscriptionStatus) {
    setSub(next);
    setPreview(await getRenewalPreview().catch(() => null));
  }

  async function handlePay() {
    // Pre-flight (#235): never fire a charge the provider can't settle. Without
    // the agent's Moyasar key every attempt 402s, so block + explain instead.
    if (!sub?.moyasar_publishable_key) {
      toast.error(t('moyasar_preflight_blocked') || 'Payment is unavailable until your provider connects Moyasar.');
      return;
    }
    setPaying(true);
    try {
      await refresh(await payClientSubscription());
      toast.success(t('dunning_done') || 'Payment complete');
    } catch (err) {
      notifyError(err, t('subscription_payment_failed') || 'Subscription payment failed.');
    } finally {
      setPaying(false);
    }
  }

  async function runLifecycle(fn: () => Promise<SubscriptionStatus>, okMsg: string) {
    setBusy(true);
    try {
      await refresh(await fn());
      toast.success(okMsg);
    } catch (err) {
      notifyError(err, t('action_failed') || 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  }

  async function handleSaveCard(token: CardOnFileToken) {
    await saveSubscriptionCard({ token: token.token, last4: token.last4, brand: token.brand });
    await refresh(await getClientSubscription());
    toast.success(t('save_card') || 'Card saved');
  }

  async function handleRefund() {
    if (!refundTarget) return;
    setBusy(true);
    try {
      await refresh(await refundSubscriptionPayment(refundTarget.id));
      toast.success(t('refund_done') || 'Payment refunded');
    } catch (err) {
      notifyError(err, t('refund_failed') || 'Refund failed.');
    } finally {
      setBusy(false);
      setRefundTarget(null);
    }
  }

  usePageChrome(
    {
      subtitle: t('billing_subtitle'),
      // Hide the charge CTA when the provider hasn't connected Moyasar — the
      // fail-closed banner takes over and a 402 cascade is pre-empted (#235).
      primaryAction: preview?.will_charge && sub?.moyasar_publishable_key ? (
        <Button onClick={handlePay} disabled={paying} className="h-11 rounded-[10px] shadow-brand">
          <Wallet className="h-4 w-4" /> {t('pay_now') || 'Pay now'}
        </Button>
      ) : undefined,
    },
    [preview?.will_charge, sub?.moyasar_publishable_key, paying, language]
  );

  if (loading) return <LoadingState message={t('loading')} />;
  if (error || !sub) return <ErrorState message={t('load_error')} onRetry={load} />;

  const status = sub.subscription_status || 'active';
  const pill = statusPill(status);
  const isPaused = status === 'paused';
  const isCancelled = status === 'cancelled';
  // Refundable rows: a real positive gateway charge (proration/refund/reservation
  // rows carry no gateway reference and are excluded).
  const isRefundable = (p: SubscriptionPayment) =>
    p.amount > 0 && p.method !== 'proration' && p.method !== 'refund' && p.method !== 'reserving';

  return (
    <div className="animate-fade-up space-y-6" dir={isRTL ? 'rtl' : 'ltr'}>
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><Wallet className="h-[18px] w-[18px]" /></span>}
        title={t('billing')}
        subtitle={t('billing_subtitle')}
      />

      {/* Fail-closed: the owning agent hasn't connected Moyasar (#235). */}
      <AgentMoyasarBanner connected={!!sub.moyasar_publishable_key} audience="merchant" />

      {/* Renewal hero — the next charge framed as the focal moment (dark ink tile). */}
      <div className="dxr-ink relative grid gap-6 rounded-[20px] p-6 sm:grid-cols-[1.4fr_1fr]">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="dxr-eyebrow">{t('upcoming_renewal')}</span>
            <span className={cn(pill.cls, 'rounded-full px-2.5 py-0.5 text-[11px] font-bold')}>
              {t(pill.key) || status}
            </span>
          </div>
          <div className="mt-3 flex items-end gap-2.5">
            <span className="text-4xl font-extrabold tracking-tight tabular-nums text-gold">
              {preview ? formatMoney(preview.net_amount, language) : formatMoney(sub.subscription_fee, language)}
            </span>
            <span className="pb-1 text-sm text-white/60">
              / {t(sub.billing_cycle) || sub.billing_cycle}
            </span>
          </div>
          {preview?.coupon_active && preview.discount_amount > 0 && (
            <div className="mt-2 inline-flex items-center gap-1.5 text-[12.5px] text-white/70">
              <Ticket className="h-3.5 w-3.5" />
              {t('coupon_applied')} · {t('bill_discount')} {formatMoney(preview.discount_amount, language)}
            </div>
          )}
        </div>
        <div className="flex flex-col justify-center gap-1 border-white/10 sm:border-s sm:ps-6">
          <span className="dxr-eyebrow">
            {isCancelled ? t('cancelled_on') : isPaused ? t('paused_on') : t('renews_on')}
          </span>
          <span className="text-lg font-bold tabular-nums">
            {isCancelled && sub.subscription_cancelled_at
              ? formatDate(sub.subscription_cancelled_at, language)
              : isPaused && sub.subscription_paused_at
                ? formatDate(sub.subscription_paused_at, language)
                : sub.next_billing_date
                  ? formatDate(sub.next_billing_date, language)
                  : '—'}
          </span>
          <p className="mt-1 text-[12.5px] leading-snug text-white/65">
            {isPaused
              ? t('billing_paused_note')
              : isCancelled
                ? t('billing_cancelled_note')
                : preview?.in_trial
                  ? t('billing_trial_note')
                  : !preview?.will_charge
                    ? t('no_upcoming_charge')
                    : ''}
          </p>
        </div>
      </div>

      {/* Lifecycle controls */}
      <div className="flex flex-wrap items-center gap-2.5">
        {isPaused || isCancelled ? (
          <Button
            variant="default"
            disabled={busy}
            onClick={() =>
              runLifecycle(
                resumeSubscription,
                isCancelled
                  ? t('reactivate_subscription') || 'Reactivated'
                  : t('resume_billing') || 'Resumed'
              )
            }
          >
            <Play className="h-4 w-4 me-1.5" />
            {isCancelled ? t('reactivate_subscription') : t('resume_billing')}
          </Button>
        ) : (
          <Button variant="outline" disabled={busy} onClick={() => setConfirm('pause')}>
            <Pause className="h-4 w-4 me-1.5" /> {t('pause_billing')}
          </Button>
        )}
        {!isCancelled && (
          <Button variant="ghost" className="text-danger hover:text-danger" disabled={busy} onClick={() => setConfirm('cancel')}>
            <Ban className="h-4 w-4 me-1.5" /> {t('cancel_subscription')}
          </Button>
        )}
      </div>

      {/* Plan + payment method */}
      <div className="grid gap-[18px] lg:grid-cols-2">
        <div className="dxr-tile">
          <div className="dxr-eyebrow mb-3">{t('subscription')}</div>
          <div className="flex items-end justify-between">
            <div>
              <div className="text-xs text-muted-foreground">{t('subscription_fee')}</div>
              <div className="mt-1 text-2xl font-extrabold tabular-nums">{formatMoney(sub.subscription_fee, language)}</div>
              <div className="text-[11.5px] text-muted-foreground">/ {t(sub.billing_cycle) || sub.billing_cycle}</div>
            </div>
            <div className="text-end">
              <div className="text-xs text-muted-foreground">{t('billing_cycle')}</div>
              <div className="mt-1 font-semibold capitalize">{t(sub.billing_cycle) || sub.billing_cycle}</div>
            </div>
          </div>
        </div>

        <div className="dxr-tile">
          <div className="dxr-eyebrow mb-3">{t('payment_method')}</div>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <span className="dxr-sw dxr-sw-gold h-10 w-10"><CreditCard className="h-5 w-5" /></span>
              <div>
                {sub.has_card && sub.card_last4 ? (
                  <div className="font-semibold tabular-nums">
                    •••• {sub.card_last4}
                    {sub.card_brand ? <span className="text-muted-foreground"> · {sub.card_brand}</span> : null}
                  </div>
                ) : (
                  <div className="text-[13px] text-muted-foreground">{t('no_card_on_file')}</div>
                )}
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => setCardOpen(true)}>
              {sub.has_card ? t('replace_card') : t('add_card')}
            </Button>
          </div>
        </div>
      </div>

      {/* Billing history */}
      <div className="dxr-tile p-0">
        <div className="flex items-center gap-2 px-5 pb-1 pt-5">
          <Receipt className="h-[18px] w-[18px] text-brand-600" />
          <h2 className="text-[15px] font-extrabold tracking-tight">{t('billing_history')}</h2>
        </div>
        <div className="overflow-x-auto px-3 pb-3 pt-2">
          {sub.payments.length === 0 ? (
            <p className="px-2 py-10 text-center text-sm text-muted-foreground">{t('no_invoices_yet')}</p>
          ) : (
            <table className="dxr-tbl">
              <thead>
                <tr>
                  <th>{t('invoice_period')}</th>
                  <th>{t('invoice_amount')}</th>
                  <th>{t('invoice_method')}</th>
                  <th className="text-end">{t('actions') || ''}</th>
                </tr>
              </thead>
              <tbody>
                {sub.payments.map((p) => {
                  const refund = p.method === 'refund';
                  return (
                    <tr key={p.id}>
                      <td className="text-muted-foreground">
                        {p.period_start
                          ? formatDate(p.period_start, language)
                          : p.created_at
                            ? formatDate(p.created_at, language)
                            : '—'}
                      </td>
                      <td className={cn('font-semibold tabular-nums', refund && 'text-danger')}>
                        {formatMoney(p.amount, language)}
                      </td>
                      <td className="text-muted-foreground">{p.method || '—'}</td>
                      <td>
                        <div className="flex items-center justify-end gap-1.5">
                          {!refund && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 gap-1 px-2"
                              onClick={() => downloadSubscriptionInvoice(p.id)}
                              aria-label={t('download_invoice')}
                              title={t('download_invoice')}
                            >
                              <Download className="h-4 w-4" />
                              <span className="hidden sm:inline">{t('download_invoice')}</span>
                            </Button>
                          )}
                          {isRefundable(p) && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 gap-1 px-2 text-danger hover:text-danger"
                              disabled={busy}
                              onClick={() => setRefundTarget(p)}
                              aria-label={t('refund_action')}
                              title={t('refund_action')}
                            >
                              <Undo2 className="h-4 w-4" />
                              <span className="hidden sm:inline">{t('refund_action')}</span>
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <CardOnFileDialog
        open={cardOpen}
        onOpenChange={setCardOpen}
        publishableKey={sub.moyasar_publishable_key}
        onSave={handleSaveCard}
        titleKey="replace_card"
      />

      {/* Pause / cancel confirmation */}
      <AlertDialog open={confirm !== null} onOpenChange={(o) => !o && setConfirm(null)}>
        <AlertDialogContent dir={isRTL ? 'rtl' : 'ltr'}>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirm === 'cancel' ? t('cancel_confirm_title') : t('pause_confirm_title')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === 'cancel' ? t('cancel_confirm_body') : t('pause_confirm_body')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('keep_subscription')}</AlertDialogCancel>
            <AlertDialogAction
              className={confirm === 'cancel' ? 'bg-danger text-danger-foreground hover:bg-danger/90' : ''}
              onClick={() =>
                confirm === 'cancel'
                  ? runLifecycle(cancelSubscription, t('cancel_subscription') || 'Subscription cancelled')
                  : runLifecycle(pauseSubscription, t('pause_billing') || 'Billing paused')
              }
            >
              {confirm === 'cancel' ? t('cancel_subscription') : t('pause_billing')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Refund confirmation */}
      <AlertDialog open={refundTarget !== null} onOpenChange={(o) => !o && setRefundTarget(null)}>
        <AlertDialogContent dir={isRTL ? 'rtl' : 'ltr'}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('refund_confirm_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('refund_confirm_body')}
              {refundTarget ? ` (${formatMoney(refundTarget.amount, language)})` : ''}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-danger text-danger-foreground hover:bg-danger/90"
              onClick={handleRefund}
            >
              {t('refund_action')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
