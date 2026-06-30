import { AlertTriangle } from 'lucide-react';
import { useLanguage } from '@/lib/i18n';
import { cn } from '@/lib/utils';

interface AgentMoyasarBannerProps {
  // Whether the owning agent's Moyasar account is connected. Pass
  // `!!sub.moyasar_publishable_key` (merchant surfaces) or
  // `!!quota.has_moyasar_account` (the agent's own dashboard).
  connected: boolean;
  // 'merchant' frames it as an honest "payments unavailable" notice; 'agent'
  // frames it as a self-directed call to connect (it blocks their whole book).
  audience: 'merchant' | 'agent';
  className?: string;
}

// #235 — fail-closed banner. When the parent agent hasn't connected Moyasar,
// every merchant charge 402s and dunning stalls silently. This banner makes
// that revenue stall impossible to miss across every billing surface.
export default function AgentMoyasarBanner({ connected, audience, className }: AgentMoyasarBannerProps) {
  const { t, isRTL } = useLanguage();
  if (connected) return null;

  const title =
    audience === 'agent'
      ? t('moyasar_unconnected_agent_title') || 'Connect Moyasar to bill your merchants'
      : t('moyasar_unconnected_title') || 'Payments temporarily unavailable';
  const body =
    audience === 'agent'
      ? t('moyasar_unconnected_agent_body') ||
        'No merchant can be charged until you connect your Moyasar account — subscriptions and dunning are paused for your whole book.'
      : t('moyasar_unconnected_body') ||
        "Card charges can't be processed yet because your provider hasn't finished payment setup. No action is needed from you — billing resumes once it's connected.";

  return (
    <div
      role="alert"
      dir={isRTL ? 'rtl' : 'ltr'}
      data-testid="agent-moyasar-banner"
      className={cn('dxr-tile flex items-start gap-4 border-danger/45', className)}
    >
      <span className="dxr-sw dxr-sw-danger h-10 w-10 shrink-0"><AlertTriangle className="h-5 w-5" /></span>
      <div className="min-w-0">
        <div className="font-bold text-danger">{title}</div>
        <p className="mt-0.5 text-sm text-muted-foreground">{body}</p>
      </div>
    </div>
  );
}
