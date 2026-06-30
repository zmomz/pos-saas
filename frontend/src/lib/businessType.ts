// Business-type spine (issue #201). One place that decides what a merchant's
// `business_type ∈ {retail, restaurant, both}` means for navigation and route
// access, so nav, route guards, the dashboard and onboarding all derive from the
// same source of truth instead of each hardcoding a vertical.

export type BusinessType = 'retail' | 'restaurant' | 'both';

export type Vertical = 'retail' | 'restaurant';

// Routes that only make sense for the restaurant vertical (floor/tables, KDS,
// menu builder, reservations). Hidden + blocked for a pure retail merchant.
export const RESTAURANT_ONLY_PATHS = ['/floor', '/reservations', '/menu-builder', '/kds'] as const;

// Routes that only make sense for the retail / merchandising vertical (product
// catalog + procurement). Hidden + blocked for a pure restaurant merchant, who
// builds their offering through the menu builder instead.
export const RETAIL_ONLY_PATHS = ['/products', '/categories', '/suppliers', '/quotations'] as const;

// Which vertical (if any) a path belongs to. Prefix-aware so nested routes like
// `/floor/ticket/:id` resolve to the same vertical as their parent.
export function pathVertical(path: string): Vertical | null {
  const matches = (p: string) => path === p || path.startsWith(`${p}/`);
  if (RESTAURANT_ONLY_PATHS.some(matches)) return 'restaurant';
  if (RETAIL_ONLY_PATHS.some(matches)) return 'retail';
  return null;
}

// Does a business type include a given vertical? `both` includes everything.
export function typeIncludes(type: BusinessType, vertical: Vertical): boolean {
  return type === 'both' || type === vertical;
}

// Is a path reachable for this business type? Shared paths (no vertical) always
// are. Used by both the nav filter and the route guard so they never disagree.
export function isPathAllowed(path: string, type: BusinessType): boolean {
  const vertical = pathVertical(path);
  return vertical === null || typeIncludes(type, vertical);
}

export const isRestaurantType = (type: BusinessType) => typeIncludes(type, 'restaurant');
export const isRetailType = (type: BusinessType) => typeIncludes(type, 'retail');

// Hybrid sale modes surfaced by the `both` dashboard switch. `retail` is the
// over-the-counter mode; the rest map to the restaurant order types.
export type SaleMode = 'retail' | 'table' | 'takeaway' | 'delivery';
export const SALE_MODES: SaleMode[] = ['retail', 'table', 'takeaway', 'delivery'];
