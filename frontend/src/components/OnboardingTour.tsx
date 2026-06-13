import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useLanguage } from '@/lib/i18n';
import { X, ChevronRight, SkipForward } from 'lucide-react';

interface TourStep {
  title: string;
  description: string;
  targetSelector: string;
  position: 'top' | 'bottom' | 'left' | 'right';
}

const masterSteps: TourStep[] = [
  {
    title: 'Welcome, Master Admin!',
    description: 'This is your control center. Manage all agents, packages, and system settings from here.',
    targetSelector: '[data-tour="dashboard-title"]',
    position: 'bottom',
  },
  {
    title: 'Navigation Sidebar',
    description: 'Use the sidebar to navigate between agents, packages, audit logs, and notifications.',
    targetSelector: '[data-tour="sidebar-nav"]',
    position: 'right',
  },
  {
    title: 'Quick Stats',
    description: 'View key metrics at a glance — total agents, revenue, and system health.',
    targetSelector: '[data-tour="stats-section"]',
    position: 'bottom',
  },
  {
    title: 'Theme & Language',
    description: 'Switch between dark/light mode and change language using the header controls.',
    targetSelector: '[data-tour="theme-toggle"]',
    position: 'bottom',
  },
];

const agentSteps: TourStep[] = [
  {
    title: 'Welcome, Agent!',
    description: 'Manage your clients, customize branding, and track revenue from your dashboard.',
    targetSelector: '[data-tour="dashboard-title"]',
    position: 'bottom',
  },
  {
    title: 'Client Management',
    description: 'Add and manage your clients. Monitor their activity and subscription status.',
    targetSelector: '[data-tour="sidebar-nav"]',
    position: 'right',
  },
  {
    title: 'Revenue Overview',
    description: 'Track your monthly revenue, active clients, and subscription metrics.',
    targetSelector: '[data-tour="stats-section"]',
    position: 'bottom',
  },
  {
    title: 'Branding & Products',
    description: 'Customize your white-label branding and manage product catalog for your clients.',
    targetSelector: '[data-tour="quick-actions"]',
    position: 'bottom',
  },
];

const clientSteps: TourStep[] = [
  {
    title: 'Welcome to Your POS!',
    description: 'Process sales, manage products, and track your business performance.',
    targetSelector: '[data-tour="dashboard-title"]',
    position: 'bottom',
  },
  {
    title: 'POS Terminal',
    description: 'Open the POS terminal to process sales with ZATCA-compliant invoices.',
    targetSelector: '[data-tour="sidebar-nav"]',
    position: 'right',
  },
  {
    title: 'Sales Overview',
    description: "View today's sales, total transactions, and product counts at a glance.",
    targetSelector: '[data-tour="stats-section"]',
    position: 'bottom',
  },
  {
    title: 'Quick Actions',
    description: 'Access POS, products, reports, and more with one click.',
    targetSelector: '[data-tour="quick-actions"]',
    position: 'bottom',
  },
];

const OnboardingTour: React.FC = () => {
  const { user } = useAuth();
  const { t } = useLanguage();
  const [currentStep, setCurrentStep] = useState(0);
  const [isVisible, setIsVisible] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState({ top: 0, left: 0 });

  const role = (user?.role as 'master' | 'agent' | 'client') || 'client';
  const storageKey = `onboarding_completed_${role}`;

  const steps = role === 'master' ? masterSteps : role === 'agent' ? agentSteps : clientSteps;

  useEffect(() => {
    const completed = localStorage.getItem(storageKey);
    if (!completed) {
      const timer = setTimeout(() => {
        setIsVisible(true);
        positionTooltip(0);
      }, 800);
      return () => clearTimeout(timer);
    }
  }, [storageKey]);

  const positionTooltip = (stepIndex: number) => {
    const step = steps[stepIndex];
    if (!step) return;

    const target = document.querySelector(step.targetSelector);
    if (target) {
      const rect = target.getBoundingClientRect();
      let top = 0;
      let left = 0;

      switch (step.position) {
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

  if (!isVisible) return null;

  const step = steps[currentStep];
  const isLastStep = currentStep === steps.length - 1;

  return (
    <div className="fixed inset-0 z-[9999]">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={handleSkip} />

      {/* Tooltip */}
      <div
        className="absolute z-[10000] w-[320px] bg-white dark:bg-slate-800 rounded-xl shadow-2xl border border-slate-200 dark:border-slate-600 p-5 animate-in fade-in duration-300"
        style={{ top: tooltipPosition.top, left: tooltipPosition.left }}
      >
        {/* Close button */}
        <button
          onClick={handleSkip}
          className="absolute top-3 right-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Step indicator */}
        <div className="flex gap-1.5 mb-3">
          {steps.map((_, i) => (
            <div
              key={i}
              className={`h-1.5 rounded-full flex-1 transition-colors ${
                i <= currentStep ? 'bg-brand-500' : 'bg-slate-300 dark:bg-slate-600'
              }`}
            />
          ))}
        </div>

        {/* Content */}
        <h3 className="text-base font-semibold text-slate-900 dark:text-white mb-2">
          {step.title}
        </h3>
        <p className="text-sm text-slate-600 dark:text-slate-300 mb-4 leading-relaxed">
          {step.description}
        </p>

        {/* Actions */}
        <div className="flex items-center justify-between">
          <button
            onClick={handleSkip}
            className="flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
          >
            <SkipForward className="h-3.5 w-3.5" />
            {t('skip') || 'Skip'}
          </button>
          <button
            onClick={handleNext}
            className="flex items-center gap-1.5 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {isLastStep ? (t('finish') || 'Finish') : (t('next') || 'Next')}
            {!isLastStep && <ChevronRight className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>
    </div>
  );
};

export default OnboardingTour;