import { Package, UserCheck, Receipt } from 'lucide-react';
import type { GlobalSearchResults } from '@/lib/api';
import type { PaletteGroup } from './CommandPalette';

/**
 * #231 (Productivity — Global search UI). Maps the cross-entity /search API
 * shape into ⌘K command-palette groups so the same backend that powers the
 * (page-local, read-only) Operations search becomes reachable — and *actionable*
 * — from every page. Each hit navigates to the entity's management page, which
 * is what makes the palette a true global search rather than a lookup box.
 *
 * Group labels reuse the existing ops_search_* i18n keys (already in all four
 * locales), so this adds no new translation surface.
 *
 * #273 (Productivity follow-up — deep-linking): a hit no longer dumps the user
 * on the bare list page. It carries a `?q=` seed — the record's most-identifying
 * field (barcode / phone / invoice number, falling back to name / #id) — which
 * each destination page reads to pre-filter itself down to that one record.
 */
function deepLink(path: string, seed: string): string {
  return `${path}?q=${encodeURIComponent(seed)}`;
}

export function buildSearchGroups(
  results: GlobalSearchResults,
  navigate: (path: string) => void,
  t: (key: string) => string,
): PaletteGroup[] {
  const { products, customers, transactions } = results.results;
  const groups: PaletteGroup[] = [];

  if (products.length) {
    groups.push({
      label: t('ops_search_products'),
      items: products.map((p) => ({
        icon: Package,
        label: p.barcode ? `${p.name} · ${p.barcode}` : p.name,
        onSelect: () => navigate(deepLink('/products', p.barcode || p.name)),
      })),
    });
  }

  if (customers.length) {
    groups.push({
      label: t('ops_search_customers'),
      items: customers.map((c) => {
        const contact = c.phone || c.email;
        return {
          icon: UserCheck,
          label: contact ? `${c.name} · ${contact}` : c.name,
          onSelect: () => navigate(deepLink('/customers', contact || c.name)),
        };
      }),
    });
  }

  if (transactions.length) {
    groups.push({
      label: t('ops_search_transactions'),
      items: transactions.map((tx) => {
        const ref = tx.invoice_number || `#${tx.id}`;
        return {
          icon: Receipt,
          label: tx.customer_name ? `${ref} · ${tx.customer_name}` : ref,
          onSelect: () => navigate(deepLink('/ops', tx.invoice_number || String(tx.id))),
        };
      }),
    });
  }

  return groups;
}
