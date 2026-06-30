import React, { useEffect, useRef } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import { useBusinessProfile } from '@/contexts/BusinessProfileContext';
import { useLanguage } from '@/lib/i18n';
import { typeIncludes, type Vertical } from '@/lib/businessType';

interface BusinessTypeRouteProps {
  vertical: Vertical;
}

/**
 * Type-driven route guard (issue #201). Blocks a vertical's routes when the
 * merchant's `business_type` doesn't include it — a retail merchant can't reach
 * the floor/KDS routes by typing the URL, and a restaurant merchant can't reach
 * the catalog/procurement routes.
 *
 * The decision derives purely from `business_type`, **before** any per-merchant
 * feature override — it mirrors the backend, which checks the type ahead of the
 * feature flag (routers/restaurant.py). Nested inside ProtectedRoute, so auth +
 * role are already enforced; this only adds the type gate.
 */
const BusinessTypeRoute: React.FC<BusinessTypeRouteProps> = ({ vertical }) => {
  const { businessType, ready } = useBusinessProfile();
  const { t } = useLanguage();
  const location = useLocation();
  const notified = useRef(false);

  const blocked = ready && businessType !== null && !typeIncludes(businessType, vertical);

  useEffect(() => {
    if (blocked && !notified.current) {
      notified.current = true;
      toast.error(t('type_section_unavailable'));
    }
  }, [blocked, t]);

  if (!ready) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-10 w-10 animate-spin rounded-full border-b-2 border-brand-500" />
      </div>
    );
  }

  if (blocked) {
    // Send them back to their dashboard rather than rendering a dead page.
    return <Navigate to="/client" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
};

export default BusinessTypeRoute;
