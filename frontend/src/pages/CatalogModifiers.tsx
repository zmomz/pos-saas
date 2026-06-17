import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import ErrorState from '@/components/states/ErrorState';
import LoadingState from '@/components/states/LoadingState';
import { formatMoney } from '@/lib/format';
import {
  getProductsList,
  getCatalogModifierGroups,
  createCatalogModifierGroup,
  createCatalogModifier,
  getCatalogProductModifierGroups,
  attachCatalogModifierGroup,
  detachCatalogModifierGroup,
  getCatalogCombos,
  createCatalogCombo,
  deleteCatalogCombo,
  type ModifierGroup,
  type ProductModifierGroup,
  type Combo,
  type ProductListItem,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { Layers } from 'lucide-react';

// ISSUE-066 — the retail counterpart of the restaurant MenuBuilder. It targets the
// un-gated /api/v1/catalog surface so a retail merchant (403'd by the restaurant
// menu-builder) can build gift-wrap modifiers and bundle combos. A combo defined
// here deducts its component stock when sold at the POS (wired in the sale path).

export default function CatalogModifiers() {
  const { t, language } = useLanguage();
  const [products, setProducts] = useState<ProductListItem[]>([]);
  const [groups, setGroups] = useState<ModifierGroup[]>([]);
  const [combos, setCombos] = useState<Combo[]>([]);
  const [attached, setAttached] = useState<Record<number, ProductModifierGroup[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Forms
  const [groupName, setGroupName] = useState('');
  const [modifierName, setModifierName] = useState<Record<number, string>>({});
  const [comboName, setComboName] = useState('');
  const [bundlePrice, setBundlePrice] = useState('');
  const [comboA, setComboA] = useState('');
  const [comboB, setComboB] = useState('');
  const [attachPick, setAttachPick] = useState<Record<number, string>>({});

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    setError(false);
    try {
      const [prodRes, grpRes, comboRes] = await Promise.all([
        getProductsList(),
        getCatalogModifierGroups(),
        getCatalogCombos(),
      ]);
      const prods = prodRes.items || [];
      setProducts(prods);
      setGroups(Array.isArray(grpRes) ? grpRes : []);
      setCombos(Array.isArray(comboRes) ? comboRes : []);
      const pairs = await Promise.all(
        prods.map(async (p) => [p.id, (await getCatalogProductModifierGroups(p.id)).items] as const)
      );
      setAttached(Object.fromEntries(pairs));
    } catch (err) {
      console.error('Failed to load catalog:', err);
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  async function handleAddGroup() {
    if (!groupName.trim()) return;
    await createCatalogModifierGroup({ name: groupName.trim() });
    setGroupName('');
    await load();
  }

  async function handleAddModifier(groupId: number) {
    const name = (modifierName[groupId] || '').trim();
    if (!name) return;
    await createCatalogModifier(groupId, { name });
    setModifierName((prev) => ({ ...prev, [groupId]: '' }));
    await load();
  }

  async function handleAttach(productId: number) {
    const groupId = parseInt(attachPick[productId] || '', 10);
    if (!groupId) return;
    await attachCatalogModifierGroup(productId, groupId);
    setAttachPick((prev) => ({ ...prev, [productId]: '' }));
    await load();
  }

  async function handleDetach(productId: number, groupId: number) {
    await detachCatalogModifierGroup(productId, groupId);
    await load();
  }

  async function handleAddCombo() {
    if (!comboName.trim() || !comboA) return;
    const components = [comboA, comboB]
      .filter(Boolean)
      .map((id) => ({ product_id: parseInt(id, 10), qty: 1 }));
    await createCatalogCombo({
      name: comboName.trim(),
      bundle_price: parseFloat(bundlePrice) || 0,
      components,
    });
    setComboName('');
    setBundlePrice('');
    setComboA('');
    setComboB('');
    await load();
  }

  if (loading) return <LoadingState />;
  if (error) return <ErrorState onRetry={load} />;

  // Radix Select disallows an empty value, so map "unpicked" to this sentinel.
  const NONE = 'none';

  return (
    <div className="animate-fade-up space-y-6">
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><Layers className="h-[18px] w-[18px]" /></span>}
        title={t('catalog_modifiers')}
      />

      {/* Modifier groups */}
      <div className="dxr-tile space-y-4">
        <h2 className="text-[16px] font-extrabold tracking-tight">{t('modifier_groups')}</h2>
        <div className="flex gap-2">
          <Input
            placeholder={t('group_name')}
            value={groupName}
            onChange={(e) => setGroupName(e.target.value)}
          />
          <Button onClick={handleAddGroup}>{t('add_modifier_group')}</Button>
        </div>
        {groups.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t('no_modifier_groups')}</p>
        ) : (
          <ul className="space-y-3">
            {groups.map((g) => (
              <li key={g.id} className="rounded-xl border border-border p-3">
                <div className="text-foreground font-medium">{g.name}</div>
                <div className="flex gap-2 mt-2">
                  <Input
                    aria-label={`${t('add_modifier')} ${g.name}`}
                    placeholder={t('add_modifier')}
                    value={modifierName[g.id] || ''}
                    onChange={(e) =>
                      setModifierName((prev) => ({ ...prev, [g.id]: e.target.value }))
                    }
                  />
                  <Button variant="outline" onClick={() => handleAddModifier(g.id)}>
                    {t('add_modifier')}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Product modifiers */}
      <div className="dxr-tile space-y-4">
        <h2 className="text-[16px] font-extrabold tracking-tight">{t('product_modifiers')}</h2>
        {products.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t('no_products_for_modifiers')}</p>
        ) : (
          <ul className="space-y-3">
            {products.map((p) => (
              <li key={p.id} className="rounded-xl border border-border p-3">
                <div className="text-foreground font-medium">{p.name}</div>
                <div className="flex flex-wrap gap-2 mt-2">
                  {(attached[p.id] || []).map((g) => (
                    <button
                      key={g.id}
                      onClick={() => handleDetach(p.id, g.id)}
                      className="inline-flex items-center gap-1.5 rounded-full bg-brand-500/10 px-2.5 py-1 text-xs font-semibold text-brand-700 dark:text-brand-300"
                    >
                      {g.name} ✕
                    </button>
                  ))}
                </div>
                <div className="flex gap-2 mt-2">
                  <Select
                    value={attachPick[p.id] || NONE}
                    onValueChange={(v) =>
                      setAttachPick((prev) => ({ ...prev, [p.id]: v === NONE ? '' : v }))
                    }
                  >
                    <SelectTrigger aria-label={`${t('attach_group')} ${p.name}`} className="w-48">
                      <SelectValue placeholder={t('attach_group')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE}>{t('attach_group')}</SelectItem>
                      {groups.map((g) => (
                        <SelectItem key={g.id} value={String(g.id)}>
                          {g.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button variant="outline" onClick={() => handleAttach(p.id)}>
                    {t('attach')}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Combos */}
      <div className="dxr-tile space-y-4">
        <h2 className="text-[16px] font-extrabold tracking-tight">{t('combos')}</h2>
        <div className="flex flex-wrap gap-2 items-center">
          <Input
            placeholder={t('combo_name')}
            value={comboName}
            onChange={(e) => setComboName(e.target.value)}
          />
          <Input
            type="number"
            placeholder={t('bundle_price')}
            value={bundlePrice}
            onChange={(e) => setBundlePrice(e.target.value)}
          />
          <Select
            value={comboA || NONE}
            onValueChange={(v) => setComboA(v === NONE ? '' : v)}
          >
            <SelectTrigger aria-label={`${t('components')} 1`} className="w-44">
              <SelectValue placeholder={t('components')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>{t('components')}</SelectItem>
              {products.map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={comboB || NONE}
            onValueChange={(v) => setComboB(v === NONE ? '' : v)}
          >
            <SelectTrigger aria-label={`${t('components')} 2`} className="w-44">
              <SelectValue placeholder={t('components')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>{t('components')}</SelectItem>
              {products.map((p) => (
                <SelectItem key={p.id} value={String(p.id)}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button onClick={handleAddCombo}>{t('add_combo')}</Button>
        </div>
        {combos.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t('no_combos')}</p>
        ) : (
          <ul className="space-y-2">
            {combos.map((c) => (
              <li
                key={c.id}
                className="rounded-xl border border-border p-3 flex items-center justify-between"
              >
                <span className="text-foreground">
                  {c.name} — <span className="tabular-nums">{formatMoney(c.bundle_price, language)}</span>
                </span>
                <Button
                  variant="outline"
                  onClick={async () => {
                    await deleteCatalogCombo(c.id);
                    await load();
                  }}
                >
                  {t('delete')}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
