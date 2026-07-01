import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useBusinessProfile } from '@/contexts/BusinessProfileContext';
import { useLanguage } from '@/lib/i18n';
import type { BusinessType } from '@/lib/businessType';
import { X, ChevronRight, SkipForward } from 'lucide-react';

interface TourStep {
  // i18n keys, resolved at render time so the tour follows the active locale.
  titleKey: string;
  descKey: string;
  targetSelector: string;
  position: 'top' | 'bottom' | 'left' | 'right';
}

const masterSteps: TourStep[] = [
  { titleKey: 'tour_master_welcome_t', descKey: 'tour_master_welcome_d', targetSelector: '[data-tour="dashboard-title"]', position: 'bottom' },
  { titleKey: 'tour_master_nav_t', descKey: 'tour_master_nav_d', targetSelector: '[data-tour="sidebar-nav"]', position: 'right' },
  { titleKey: 'tour_master_stats_t', descKey: 'tour_master_stats_d', targetSelector: '[data-tour="stats-section"]', position: 'bottom' },
  { titleKey: 'tour_master_theme_t', descKey: 'tour_master_theme_d', targetSelector: '[data-tour="theme-toggle"]', position: 'bottom' },
];

const agentSteps: TourStep[] = [
  { titleKey: 'tour_agent_welcome_t', descKey: 'tour_agent_welcome_d', targetSelector: '[data-tour="dashboard-title"]', position: 'bottom' },
  { titleKey: 'tour_agent_clients_t', descKey: 'tour_agent_clients_d', targetSelector: '[data-tour="sidebar-nav"]', position: 'right' },
  { titleKey: 'tour_agent_revenue_t', descKey: 'tour_agent_revenue_d', targetSelector: '[data-tour="stats-section"]', position: 'bottom' },
  { titleKey: 'tour_agent_branding_t', descKey: 'tour_agent_branding_d', targetSelector: '[data-tour="quick-actions"]', position: 'bottom' },
];

// Client tour reframed per business type (issue #201) — was hardcoded retail.
// The welcome / navigation / focus steps speak to the merchant's actual vertical
// (retail catalog vs restaurant floor & kitchen vs both); the quick-actions step
// is shared.
function clientSteps(businessType: BusinessType): TourStep[] {
  const variant = businessType === 'restaurant' ? 'restaurant' : businessType === 'both' ? 'both' : 'retail';
  return [
    { titleKey: 'tour_client_welcome_t', descKey: `tour_client_welcome_${variant}`, targetSelector: '[data-tour="dashboard-title"]', position: 'bottom' },
    { titleKey: 'tour_client_nav_t', descKey: `tour_client_nav_${variant}`, targetSelector: '[data-tour="sidebar-nav"]', position: 'right' },
    { titleKey: 'tour_client_focus_t', descKey: `tour_client_focus_${variant}`, targetSelector: '[data-tour="stats-section"]', position: 'bottom' },
    { titleKey: 'tour_client_actions_t', descKey: 'tour_client_actions_d', targetSelector: '[data-tour="quick-actions"]', position: 'bottom' },
  ];
}

const OnboardingTour: React.FC = () => {
  const { user } = useAuth();
  const { businessType, ready } = useBusinessProfile();
  const { t, isRTL } = useLanguage();
  const [currentStep, setCurrentStep] = useState(0);
  const [isVisible, setIsVisible] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState({ top: 0, left: 0 });

  const role = (user?.role as 'master' | 'agent' | 'client') || 'client';
  // For a client, key the completion flag on the business type too, so the
  // change-type flow re-runs the tour for the new experience (no data deleted —
  // just a fresh walkthrough of what changed).
  const effectiveType: BusinessType = businessType ?? 'retail';
  const storageKey =
    role === 'client' ? `onboarding_completed_client_${effectiveType}` : `onboarding_completed_${role}`;

  const steps =
    role === 'master' ? masterSteps : role === 'agent' ? agentSteps : clientSteps(effectiveType);

  // Hold the client tour until the business type has resolved, otherwise the
  // first-run walkthrough could describe the wrong vertical.
  const canStart = role !== 'client' || ready;

  useEffect(() => {
    if (!canStart) return;
    const completed = localStorage.getItem(storageKey);
    if (!completed) {
      const timer = setTimeout(() => {
        setCurrentStep(0);
        setIsVisible(true);
        positionTooltip(0);
      }, 800);
      return () => clearTimeout(timer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey, canStart]);

  const positionTooltip = (stepIndex: number) => {
    const step = steps[stepIndex];
    if (!step) return;

    const target = document.querySelector(step.targetSelector);
    if (target) {
      const rect = target.getBoundingClientRect();
      let top = 0;
      let left = 0;

      // Mirror horizontal side anchoring under RTL so a tooltip meant to sit
      // beside an element (e.g. the sidebar, which moves to the right edge in
      // RTL) lands on the content-facing side instead of off-screen.
      const side =
        isRTL && step.position === 'right'
          ? 'left'
          : isRTL && step.position === 'left'
          ? 'right'
          : step.position;

      switch (side) {
        case 'bottom':
          top = rect.bottom + 12;
          left = rect.left + rect.width / 2 - 160;
          break;
        case 'top':
          top = rect.top - 180;
          left = rect.left + rect.width / 2 - 160;
          break;
        case 'right':
          top = rect.top + rect.height / 2 - 60;
          left = rect.right + 12;
          break;
        case 'left':
          top = rect.top + rect.height / 2 - 60;
          left = rect.left - 332;
          break;
      }

      // Keep within viewport
      top = Math.max(10, Math.min(top, window.innerHeight - 200));
      left = Math.max(10, Math.min(left, window.innerWidth - 340));

      setTooltipPosition({ top, left });
    } else {
      // Fallback center position
      setTooltipPosition({
        top: window.innerHeight / 2 - 80,
        left: window.innerWidth / 2 - 160,
      });
    }
  };

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      const nextStep = currentStep + 1;
      setCurrentStep(nextStep);
      positionTooltip(nextStep);
    } else {
      handleFinish();
    }
  };

  const handleSkip = () => {
    handleFinish();
  };

  const handleFinish = () => {
    localStorage.setItem(storageKey, 'true');
    setIsVisible(false);
  };

  // Keyboard parity with the click-the-backdrop dismissal (WCAG 2.1.1): while
  // the tour is open, Escape finishes it. Registered on the document so it
  // fires regardless of where focus currently sits.
  useEffect(() => {
    if (!isVisible) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        handleFinish();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isVisible]);

  if (!isVisible) return null;

  const step = steps[currentStep];
  const isLastStep = currentStep === steps.length - 1;

  return (
    <div className="fixed inset-0 z-[9999]">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={handleSkip} />

      {/* Tooltip */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="onboarding-tour-title"
        className="absolute z-[10000] w-[320px] bg-white dark:bg-card rounded-xl shadow-2xl border border-border dark:border-input p-5 animate-in fade-in duration-300"
        style={{ top: tooltipPosition.top, left: tooltipPosition.left }}
      >
        {/* Close button */}
        <button
          onClick={handleSkip}
          className="absolute top-3 end-3 text-muted-foreground hover:text-muted-foreground dark:hover:text-foreground"
          aria-label={t('skip') || 'Skip'}
        >
          <X className="h-4 w-4" />
        </button>

        {/* Step indicator */}
        <div className="flex gap-1.5 mb-3">
          {steps.map((_, i) => (
            <div
              key={i}
              className={`h-1.5 rounded-full flex-1 transition-colors ${
                i <= currentStep ? 'bg-brand-500' : 'bg-muted dark:bg-muted'
              }`}
            />
          ))}
        </div>

        {/* Content */}
        <h3
          id="onboarding-tour-title"
          className="text-base font-semibold text-foreground dark:text-foreground mb-2"
        >
          {t(step.titleKey)}
        </h3>
        <p className="text-sm text-muted-foreground dark:text-foreground/90 mb-4 leading-relaxed">
          {t(step.descKey)}
        </p>

        {/* Actions */}
        <div className="flex items-center justify-between">
          <button
            onClick={handleSkip}
            className="flex items-center gap-1 text-sm text-muted-foreground dark:text-muted-foreground hover:text-foreground dark:hover:text-foreground transition-colors"
          >
            <SkipForward className="h-3.5 w-3.5" />
            {t('skip') || 'Skip'}
          </button>
          <button
            onClick={handleNext}
            className="flex items-center gap-1.5 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {isLastStep ? (t('finish') || 'Finish') : (t('next') || 'Next')}
            {!isLastStep && <ChevronRight className={`h-3.5 w-3.5 ${isRTL ? 'rotate-180' : ''}`} />}
          </button>
        </div>
      </div>
    </div>
  );
};

export default OnboardingTour;
