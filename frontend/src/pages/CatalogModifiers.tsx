import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
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
  const { t } = useLanguage();
  const [products, setProducts] = useState<ProductListItem[]>([]);
  const [groups, setGroups] = useState<ModifierGroup[]>([]);
  const [combos, setCombos] = useState<Combo[]>([]);
  const [attached, setAttached] = useState<Record<number, ProductModifierGroup[]>>({});
  const [loading, setLoading] = useState(true);

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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  const selectCls =
    'rounded-md bg-slate-900 border border-slate-700 text-white px-2 py-2 text-sm';

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-brand-gold">
        <Layers className="h-5 w-5" />
        <h1 className="text-xl font-semibold text-white">{t('catalog_modifiers')}</h1>
      </div>

      {/* Modifier groups */}
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4 space-y-4">
          <h2 className="font-semibold text-white">{t('modifier_groups')}</h2>
          <div className="flex gap-2">
            <Input
              placeholder={t('group_name')}
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
            />
            <Button onClick={handleAddGroup}>{t('add_modifier_group')}</Button>
          </div>
          {groups.length === 0 ? (
            <p className="text-slate-400 text-sm">{t('no_modifier_groups')}</p>
          ) : (
            <ul className="space-y-3">
              {groups.map((g) => (
                <li key={g.id} className="border border-slate-700 rounded-md p-3">
                  <div className="text-white font-medium">{g.name}</div>
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
        </CardContent>
      </Card>

      {/* Product modifiers */}
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4 space-y-4">
          <h2 className="font-semibold text-white">{t('product_modifiers')}</h2>
          {products.length === 0 ? (
            <p className="text-slate-400 text-sm">{t('no_products_for_modifiers')}</p>
          ) : (
            <ul className="space-y-3">
              {products.map((p) => (
                <li key={p.id} className="border border-slate-700 rounded-md p-3">
                  <div className="text-white font-medium">{p.name}</div>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {(attached[p.id] || []).map((g) => (
                      <button
                        key={g.id}
                        onClick={() => handleDetach(p.id, g.id)}
                        className="text-xs rounded-full bg-brand-petrol/30 text-white px-2 py-1"
                      >
                        {g.name} ✕
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-2 mt-2">
                    <select
                      aria-label={`${t('attach_group')} ${p.name}`}
                      className={selectCls}
                      value={attachPick[p.id] || ''}
                      onChange={(e) =>
                        setAttachPick((prev) => ({ ...prev, [p.id]: e.target.value }))
                      }
                    >
                      <option value="">{t('attach_group')}</option>
                      {groups.map((g) => (
                        <option key={g.id} value={g.id}>
                          {g.name}
                        </option>
                      ))}
                    </select>
                    <Button variant="outline" onClick={() => handleAttach(p.id)}>
                      {t('attach')}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Combos */}
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4 space-y-4">
          <h2 className="font-semibold text-white">{t('combos')}</h2>
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
            <select
              aria-label={`${t('components')} 1`}
              className={selectCls}
              value={comboA}
              onChange={(e) => setComboA(e.target.value)}
            >
              <option value="">{t('components')}</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <select
              aria-label={`${t('components')} 2`}
              className={selectCls}
              value={comboB}
              onChange={(e) => setComboB(e.target.value)}
            >
              <option value="">{t('components')}</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <Button onClick={handleAddCombo}>{t('add_combo')}</Button>
          </div>
          {combos.length === 0 ? (
            <p className="text-slate-400 text-sm">{t('no_combos')}</p>
          ) : (
            <ul className="space-y-2">
              {combos.map((c) => (
                <li
                  key={c.id}
                  className="border border-slate-700 rounded-md p-3 flex items-center justify-between"
                >
                  <span className="text-white">
                    {c.name} — {c.bundle_price}
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
        </CardContent>
      </Card>
    </div>
  );
}
