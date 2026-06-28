import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { getClientProfile, type ClientProfile } from '@/lib/api';
import type { BusinessType, SaleMode } from '@/lib/businessType';

// The business-type spine (issue #201). Fetches the signed-in merchant's profile
// once and exposes its `business_type` to the whole client experience, so
// navigation, route guards, the dashboard and onboarding all derive from one
// source of truth. The ClientDashboard previously fetched neither the profile
// nor the type — this is the keystone the type-aware shell depends on.

interface BusinessProfileContextType {
  // The merchant's business type, or null for non-client roles / before load.
  businessType: BusinessType | null;
  profile: ClientProfile | null;
  // True once the profile resolution has settled (loaded, failed, or N/A). Route
  // guards wait for this so they never block a route on a not-yet-known type.
  ready: boolean;
  // Re-fetch the profile (called after the change-type flow so the shell
  // recomputes without a full reload).
  refresh: () => Promise<void>;
  // Hybrid (`both`) default sale mode, persisted locally. Drives the dashboard
  // sale-mode switch and the POS entry intent.
  saleMode: SaleMode;
  setSaleMode: (mode: SaleMode) => void;
}

const SALE_MODE_KEY = 'pos_sale_mode';

// Safe default for when the hook is used outside a provider (e.g. a component
// rendered in isolation in a unit test): the type is unknown, so the shell shows
// everything and route guards don't block — the same as the in-app loading
// state. The real provider below overrides this everywhere in the app.
const DEFAULT_CONTEXT: BusinessProfileContextType = {
  businessType: null,
  profile: null,
  ready: true,
  refresh: async () => {},
  saleMode: 'retail',
  setSaleMode: () => {},
};

const BusinessProfileContext = createContext<BusinessProfileContextType>(DEFAULT_CONTEXT);

export const useBusinessProfile = () => useContext(BusinessProfileContext);

function readSaleMode(): SaleMode {
  const stored = localStorage.getItem(SALE_MODE_KEY);
  if (stored === 'retail' || stored === 'table' || stored === 'takeaway' || stored === 'delivery') {
    return stored;
  }
  return 'retail';
}

export const BusinessProfileProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading: authLoading } = useAuth();
  const [profile, setProfile] = useState<ClientProfile | null>(null);
  const [ready, setReady] = useState(false);
  const [saleMode, setSaleModeState] = useState<SaleMode>(() => readSaleMode());

  const isClient = user?.role === 'client' && !user?.must_change_password;

  const refresh = useCallback(async () => {
    if (!isClient) {
      // Only client tenancies have a business type. Master/agent settle as N/A.
      setProfile(null);
      setReady(true);
      return;
    }
    try {
      const data = await getClientProfile();
      setProfile(data);
    } catch {
      // A transport blip must not silently mislabel the experience — leave the
      // type unknown (null) rather than fabricating 'retail'. The shell falls
      // back to showing everything until the next successful fetch.
      setProfile(null);
    } finally {
      setReady(true);
    }
  }, [isClient]);

  useEffect(() => {
    // Wait for auth to settle before deciding whether to fetch a profile.
    if (authLoading) {
      setReady(false);
      return;
    }
    refresh();
  }, [authLoading, refresh]);

  const setSaleMode = useCallback((mode: SaleMode) => {
    setSaleModeState(mode);
    localStorage.setItem(SALE_MODE_KEY, mode);
  }, []);

  const value: BusinessProfileContextType = {
    businessType: (profile?.business_type as BusinessType) ?? null,
    profile,
    ready,
    refresh,
    saleMode,
    setSaleMode,
  };

  return (
    <BusinessProfileContext.Provider value={value}>{children}</BusinessProfileContext.Provider>
  );
};
