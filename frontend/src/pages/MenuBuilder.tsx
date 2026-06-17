import { useEffect, useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import { formatMoney } from '@/lib/format';
import {
  getModifierGroups,
  createModifierGroup,
  deleteModifierGroup,
  getModifiers,
  createModifier,
  deleteModifier,
  getCombos,
  createCombo,
  deleteCombo,
  getProducts,
  getProductModifierGroups,
  attachModifierGroup,
  detachModifierGroup,
  getProductBom,
  addBomEntry,
  deleteBomEntry,
  type ModifierGroup,
  type Modifier,
  type Combo,
  type ComboComponentRef,
  type ProductModifierGroup,
  type BomEntry,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { UtensilsCrossed, Plus, Trash2, WifiOff, AlertTriangle, Lock, Layers, ChefHat } from 'lucide-react';

interface ProductLite {
  id: number;
  name: string;
  price: number;
}

export default function MenuBuilder() {
  const { t, language } = useLanguage();

  const [groups, setGroups] = useState<ModifierGroup[]>([]);
  const [modsByGroup, setModsByGroup] = useState<Record<number, Modifier[]>>({});
  const [combos, setCombos] = useState<Combo[]>([]);
  const [products, setProducts] = useState<ProductLite[]>([]);
  const [attachedByProduct, setAttachedByProduct] = useState<Record<number, ProductModifierGroup[]>>(
    {}
  );
  // Per-product selection in the "attach a group" dropdown.
  const [attachChoice, setAttachChoice] = useState<Record<number, number | ''>>({});
  // Per-product recipe (BOM) state: components, rolled-up COGS, and the add-row inputs.
  const [bomByProduct, setBomByProduct] = useState<Record<number, BomEntry[]>>({});
  const [cogsByProduct, setCogsByProduct] = useState<Record<number, number>>({});
  const [bomChoice, setBomChoice] = useState<Record<number, number | ''>>({});
  const [bomQty, setBomQty] = useState<Record<number, number>>({});

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);
  const [submitting, setSubmitting] = useState(false);

  const [groupOpen, setGroupOpen] = useState(false);
  const [groupForm, setGroupForm] = useState<{
    name: string;
    name_ar: string;
    required: boolean;
    min_select: number;
    max_select: number;
  }>({ name: '', name_ar: '', required: false, min_select: 0, max_select: 1 });

  const [modOpen, setModOpen] = useState<ModifierGroup | null>(null);
  const [modForm, setModForm] = useState<{ name: string; name_ar: string; price_delta: number }>({
    name: '',
    name_ar: '',
    price_delta: 0,
  });

  const [comboOpen, setComboOpen] = useState(false);
  const [comboForm, setComboForm] = useState<{
    name: string;
    name_ar: string;
    bundle_price: number;
    components: ComboComponentRef[];
  }>({ name: '', name_ar: '', bundle_price: 0, components: [] });

  // Offline banner (UX-02).
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const [grps, cmb, prods] = await Promise.all([getModifierGroups(), getCombos(), getProducts()]);
      const safeGroups = Array.isArray(grps) ? grps : [];
      const safeProducts = Array.isArray(prods) ? (prods as ProductLite[]) : [];
      setGroups(safeGroups);
      setCombos(Array.isArray(cmb) ? cmb : []);
      setProducts(safeProducts);
      // Pull each group's modifiers for display.
      const entries = await Promise.all(
        safeGroups.map(async (g) => [g.id, await getModifiers(g.id).catch(() => [])] as const)
      );
      setModsByGroup(Object.fromEntries(entries));
      // Pull each product's attached modifier groups for the attach/detach UI.
      const attachEntries = await Promise.all(
        safeProducts.map(
          async (p) =>
            [p.id, await getProductModifierGroups(p.id).then((r) => r.items).catch(() => [])] as const
        )
      );
      setAttachedByProduct(Object.fromEntries(attachEntries));
      // Pull each product's recipe (BOM) components + rolled-up cost-of-goods.
      const bomEntries = await Promise.all(
        safeProducts.map(
          async (p) =>
            [p.id, await getProductBom(p.id).catch(() => ({ items: [], total: 0, cost_of_goods: 0 }))] as const
        )
      );
      setBomByProduct(Object.fromEntries(bomEntries.map(([id, b]) => [id, b.items])));
      setCogsByProduct(Object.fromEntries(bomEntries.map(([id, b]) => [id, b.cost_of_goods])));
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setDenied(true);
      else setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreateGroup() {
    if (!groupForm.name.trim()) return;
    setSubmitting(true);
    try {
      await createModifierGroup(groupForm);
      setGroupOpen(false);
      setGroupForm({ name: '', name_ar: '', required: false, min_select: 0, max_select: 1 });
      await load();
    } catch (err) {
      console.error('Failed to create modifier group:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCreateModifier() {
    if (!modOpen || !modForm.name.trim()) return;
    setSubmitting(true);
    try {
      await createModifier(modOpen.id, modForm);
      setModOpen(null);
      setModForm({ name: '', name_ar: '', price_delta: 0 });
      await load();
    } catch (err) {
      console.error('Failed to create modifier:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCreateCombo() {
    if (!comboForm.name.trim()) return;
    setSubmitting(true);
    try {
      await createCombo({
        name: comboForm.name,
        name_ar: comboForm.name_ar || undefined,
        bundle_price: comboForm.bundle_price,
        components: comboForm.components.filter((c) => c.product_id),
      });
      setComboOpen(false);
      setComboForm({ name: '', name_ar: '', bundle_price: 0, components: [] });
      await load();
    } catch (err) {
      console.error('Failed to create combo:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAttachGroup(productId: number) {
    const groupId = attachChoice[productId];
    if (!groupId) return;
    setSubmitting(true);
    try {
      await attachModifierGroup(productId, groupId);
      setAttachChoice((c) => ({ ...c, [productId]: '' }));
      await load();
    } catch (err) {
      console.error('Failed to attach modifier group:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDetachGroup(productId: number, groupId: number) {
    setSubmitting(true);
    try {
      await detachModifierGroup(productId, groupId);
      await load();
    } catch (err) {
      console.error('Failed to detach modifier group:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAddComponent(productId: number) {
    const componentId = bomChoice[productId];
    const qtyPer = bomQty[productId] ?? 1;
    if (!componentId || qtyPer <= 0) return;
    setSubmitting(true);
    try {
      await addBomEntry(productId, { component_product_id: componentId, qty_per: qtyPer });
      setBomChoice((c) => ({ ...c, [productId]: '' }));
      setBomQty((q) => ({ ...q, [productId]: 1 }));
      await load();
    } catch (err) {
      console.error('Failed to add recipe component:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRemoveComponent(bomId: number) {
    setSubmitting(true);
    try {
      await deleteBomEntry(bomId);
      await load();
    } catch (err) {
      console.error('Failed to remove recipe component:', err);
    } finally {
      setSubmitting(false);
    }
  }

  // ---- Loading state ----
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-foreground animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  // ---- Permission-denied state (retail business_type / feature off) ----
  if (denied) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="bg-card border-border max-w-md">
          <CardContent className="p-8 text-center">
            <Lock className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <h3 className="text-foreground font-semibold mb-2">{t('restaurant_disabled')}</h3>
            <p className="text-muted-foreground text-sm">{t('restaurant_disabled_desc')}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ---- Error state ----
  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="bg-card border-border max-w-md">
          <CardContent className="p-8 text-center">
            <AlertTriangle className="h-12 w-12 text-danger mx-auto mb-3" />
            <p className="text-foreground/90 mb-4">{t('menu_load_error')}</p>
            <Button onClick={load}>
              {t('retry')}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-6">
      {!online && (
        <div className="flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-4 py-2 text-warning text-sm">
          <WifiOff className="h-4 w-4" />
          <span>{t('you_are_offline')}</span>
        </div>
      )}

      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><UtensilsCrossed className="h-[18px] w-[18px]" /></span>}
        title={t('menu_builder')}
      >
        <Button onClick={() => setGroupOpen(true)} className="h-11 rounded-[10px] shadow-brand">
          <Plus className="h-4 w-4" /> {t('add_modifier_group')}
        </Button>
        <Button
          variant="outline"
          onClick={() => setComboOpen(true)}
          className="h-11 rounded-[10px]"
        >
          <Layers className="h-4 w-4" /> {t('add_combo')}
        </Button>
      </PageHeading>

      {/* Modifier groups */}
      <div>
        <h3 className="text-[16px] font-extrabold tracking-tight mb-2">{t('modifier_groups')}</h3>
        {groups.length === 0 ? (
          <Card className="bg-card border-border">
            <CardContent className="p-8 text-center">
              <UtensilsCrossed className="h-10 w-10 text-muted-foreground mx-auto mb-2" />
              <p className="text-muted-foreground text-sm">{t('no_modifier_groups')}</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {groups.map((g) => (
              <Card key={g.id} className="bg-card border-border">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-foreground font-medium">{g.name}</span>
                      {g.required && (
                        <span className="pill-warning">{t('required')}</span>
                      )}
                      <span className="text-xs text-muted-foreground">
                        {g.min_select ?? 0}–{g.max_select ?? 1}
                      </span>
                    </div>
                    <button
                      onClick={() => deleteModifierGroup(g.id).then(load)}
                      className="text-muted-foreground hover:text-danger"
                      aria-label={t('delete')}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="space-y-1">
                    {(modsByGroup[g.id] || []).map((m) => (
                      <div
                        key={m.id}
                        className="flex items-center justify-between text-sm text-foreground/90"
                      >
                        <span>{m.name}</span>
                        <span className="flex items-center gap-3">
                          {m.price_delta !== 0 && (
                            <span className="text-xs text-muted-foreground">
                              {m.price_delta > 0 ? '+' : ''}
                              {m.price_delta}
                            </span>
                          )}
                          <button
                            onClick={() => deleteModifier(m.id).then(load)}
                            className="text-muted-foreground hover:text-danger"
                            aria-label={t('delete')}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </span>
                      </div>
                    ))}
                    {(modsByGroup[g.id] || []).length === 0 && (
                      <p className="text-xs text-muted-foreground">{t('no_modifiers')}</p>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setModForm({ name: '', name_ar: '', price_delta: 0 });
                      setModOpen(g);
                    }}
                    className="mt-3"
                  >
                    <Plus className="h-3.5 w-3.5" /> {t('add_modifier')}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Combos */}
      <div>
        <h3 className="text-[16px] font-extrabold tracking-tight mb-2">{t('combos')}</h3>
        {combos.length === 0 ? (
          <Card className="bg-card border-border">
            <CardContent className="p-8 text-center">
              <Layers className="h-10 w-10 text-muted-foreground mx-auto mb-2" />
              <p className="text-muted-foreground text-sm">{t('no_combos')}</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {combos.map((c) => (
              <Card key={c.id} className="bg-card border-border">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-foreground font-medium">{c.name}</span>
                    <button
                      onClick={() => deleteCombo(c.id).then(load)}
                      className="text-muted-foreground hover:text-danger"
                      aria-label={t('delete')}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="mt-2 text-sm">
                    <span className="text-foreground font-semibold tabular-nums">{formatMoney(c.bundle_price, language)}</span>
                    {c.component_sum != null && c.component_sum > c.bundle_price && (
                      <span className="text-xs text-muted-foreground ms-2 line-through tabular-nums">
                        {formatMoney(c.component_sum, language)}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {t('components')}: {c.components.length}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Product modifiers — attach/detach groups to products (ISSUE-040) */}
      <div>
        <h3 className="text-[16px] font-extrabold tracking-tight mb-2">{t('product_modifiers')}</h3>
        {products.length === 0 ? (
          <Card className="bg-card border-border">
            <CardContent className="p-8 text-center">
              <UtensilsCrossed className="h-10 w-10 text-muted-foreground mx-auto mb-2" />
              <p className="text-muted-foreground text-sm">{t('no_products_for_modifiers')}</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {products.map((p) => {
              const attached = attachedByProduct[p.id] || [];
              const attachedIds = new Set(attached.map((g) => g.id));
              const available = groups.filter((g) => !attachedIds.has(g.id));
              return (
                <Card
                  key={p.id}
                  data-testid={`product-mods-${p.id}`}
                  className="bg-card border-border"
                >
                  <CardContent className="p-4">
                    <div className="mb-2">
                      <span className="text-foreground font-medium">{p.name}</span>
                    </div>
                    {attached.length === 0 ? (
                      <p className="text-xs text-muted-foreground mb-2">{t('no_attached_groups')}</p>
                    ) : (
                      <div className="flex flex-wrap gap-2 mb-2">
                        {attached.map((g) => (
                          <span
                            key={g.id}
                            className="inline-flex items-center gap-1.5 rounded-full bg-brand-500/10 px-2.5 py-0.5 text-xs font-semibold text-brand-700 dark:text-brand-300"
                          >
                            {g.name}
                            <button
                              onClick={() => handleDetachGroup(p.id, g.id)}
                              disabled={submitting}
                              className="hover:text-danger"
                              aria-label={`${t('detach')} ${g.name}`}
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <Select
                        value={attachChoice[p.id] ? String(attachChoice[p.id]) : 'none'}
                        onValueChange={(v) =>
                          setAttachChoice((c) => ({
                            ...c,
                            [p.id]: v && v !== 'none' ? parseInt(v) : '',
                          }))
                        }
                        disabled={available.length === 0}
                      >
                        <SelectTrigger aria-label={`${t('attach_group')} — ${p.name}`} className="flex-1">
                          <SelectValue placeholder={t('attach_group')} />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">{t('attach_group')}</SelectItem>
                          {available.map((g) => (
                            <SelectItem key={g.id} value={String(g.id)}>
                              {g.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        size="sm"
                        onClick={() => handleAttachGroup(p.id)}
                        disabled={submitting || !attachChoice[p.id]}
                      >
                        <Plus className="h-3.5 w-3.5" /> {t('attach')}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Recipes (BOM) — define a product's component recipe (ISSUE-039) */}
      <div>
        <h3 className="text-[16px] font-extrabold tracking-tight mb-2 flex items-center gap-2">
          <ChefHat className="h-5 w-5 text-brand-700" />
          {t('recipes')}
        </h3>
        {products.length === 0 ? (
          <Card className="bg-card border-border">
            <CardContent className="p-8 text-center">
              <ChefHat className="h-10 w-10 text-muted-foreground mx-auto mb-2" />
              <p className="text-muted-foreground text-sm">{t('no_products_for_recipes')}</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {products.map((p) => {
              const components = bomByProduct[p.id] || [];
              const usedIds = new Set(components.map((b) => b.component_product_id));
              // A component can be any other product not already in this recipe (no self).
              const available = products.filter((c) => c.id !== p.id && !usedIds.has(c.id));
              const cogs = cogsByProduct[p.id] ?? 0;
              return (
                <Card
                  key={p.id}
                  data-testid={`product-bom-${p.id}`}
                  className="bg-card border-border"
                >
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-foreground font-medium">{p.name}</span>
                      {cogs > 0 && (
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {t('cost_of_goods')}: {formatMoney(cogs, language)}
                        </span>
                      )}
                    </div>
                    {components.length === 0 ? (
                      <p className="text-xs text-muted-foreground mb-2">{t('no_components')}</p>
                    ) : (
                      <div className="space-y-1 mb-2">
                        {components.map((b) => {
                          const comp = products.find((c) => c.id === b.component_product_id);
                          const compName = comp?.name ?? `#${b.component_product_id}`;
                          return (
                            <div
                              key={b.id}
                              className="flex items-center justify-between text-sm text-foreground/90"
                            >
                              <span>
                                {compName} <span className="text-muted-foreground">×{b.qty_per}</span>
                              </span>
                              <button
                                onClick={() => handleRemoveComponent(b.id)}
                                disabled={submitting}
                                className="text-muted-foreground hover:text-danger"
                                aria-label={`${t('remove')} ${compName}`}
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <Select
                        value={bomChoice[p.id] ? String(bomChoice[p.id]) : 'none'}
                        onValueChange={(v) =>
                          setBomChoice((c) => ({
                            ...c,
                            [p.id]: v && v !== 'none' ? parseInt(v) : '',
                          }))
                        }
                        disabled={available.length === 0}
                      >
                        <SelectTrigger aria-label={`${t('add_component')} — ${p.name}`} className="flex-1">
                          <SelectValue placeholder={t('add_component')} />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">{t('add_component')}</SelectItem>
                          {available.map((c) => (
                            <SelectItem key={c.id} value={String(c.id)}>
                              {c.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Input
                        type="number"
                        aria-label={`${t('qty_per')} — ${p.name}`}
                        value={bomQty[p.id] ?? 1}
                        min={0}
                        step="any"
                        onChange={(e) =>
                          setBomQty((q) => ({ ...q, [p.id]: parseFloat(e.target.value) || 0 }))
                        }
                        className="w-20 h-9"
                      />
                      <Button
                        size="sm"
                        onClick={() => handleAddComponent(p.id)}
                        disabled={submitting || !bomChoice[p.id]}
                      >
                        <Plus className="h-3.5 w-3.5" /> {t('add_component')}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Create modifier-group dialog */}
      <Dialog open={groupOpen} onOpenChange={setGroupOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('add_modifier_group')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="mb-1 block">{t('name')}</Label>
              <Input
                value={groupForm.name}
                onChange={(e) => setGroupForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div>
              <Label className="mb-1 block">{t('name_ar')}</Label>
              <Input
                value={groupForm.name_ar}
                onChange={(e) => setGroupForm((f) => ({ ...f, name_ar: e.target.value }))}
                dir="rtl"
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-foreground/90">
              <Checkbox
                checked={groupForm.required}
                onCheckedChange={(c) => setGroupForm((f) => ({ ...f, required: c === true }))}
              />
              {t('required')}
            </label>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="mb-1 block">{t('min_select')}</Label>
                <Input
                  type="number"
                  value={groupForm.min_select}
                  onChange={(e) => setGroupForm((f) => ({ ...f, min_select: parseInt(e.target.value) || 0 }))}
                />
              </div>
              <div>
                <Label className="mb-1 block">{t('max_select')}</Label>
                <Input
                  type="number"
                  value={groupForm.max_select}
                  onChange={(e) => setGroupForm((f) => ({ ...f, max_select: parseInt(e.target.value) || 1 }))}
                />
              </div>
            </div>
            <Button
              onClick={handleCreateGroup}
              disabled={submitting || !groupForm.name.trim()}
              className="w-full"
            >
              {submitting ? t('loading') : t('save')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Create modifier dialog */}
      <Dialog open={!!modOpen} onOpenChange={(o) => !o && setModOpen(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t('add_modifier')} — {modOpen?.name}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="mb-1 block">{t('name')}</Label>
              <Input
                value={modForm.name}
                onChange={(e) => setModForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div>
              <Label className="mb-1 block">{t('name_ar')}</Label>
              <Input
                value={modForm.name_ar}
                onChange={(e) => setModForm((f) => ({ ...f, name_ar: e.target.value }))}
                dir="rtl"
              />
            </div>
            <div>
              <Label className="mb-1 block">{t('price_delta')}</Label>
              <Input
                type="number"
                value={modForm.price_delta}
                onChange={(e) => setModForm((f) => ({ ...f, price_delta: parseFloat(e.target.value) || 0 }))}
              />
            </div>
            <Button
              onClick={handleCreateModifier}
              disabled={submitting || !modForm.name.trim()}
              className="w-full"
            >
              {submitting ? t('loading') : t('save')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Create combo dialog */}
      <Dialog open={comboOpen} onOpenChange={setComboOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('add_combo')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="mb-1 block">{t('name')}</Label>
              <Input
                value={comboForm.name}
                onChange={(e) => setComboForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div>
              <Label className="mb-1 block">{t('bundle_price')}</Label>
              <Input
                type="number"
                value={comboForm.bundle_price}
                onChange={(e) =>
                  setComboForm((f) => ({ ...f, bundle_price: parseFloat(e.target.value) || 0 }))
                }
              />
            </div>
            <div>
              <Label className="mb-1 block">{t('components')}</Label>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {products.map((p) => {
                  const sel = comboForm.components.find((c) => c.product_id === p.id);
                  return (
                    <label
                      key={p.id}
                      className="flex items-center justify-between gap-2 text-sm text-foreground/90"
                    >
                      <span className="flex items-center gap-2">
                        <Checkbox
                          checked={!!sel}
                          onCheckedChange={(checked) =>
                            setComboForm((f) => ({
                              ...f,
                              components: checked === true
                                ? [...f.components, { product_id: p.id, qty: 1 }]
                                : f.components.filter((c) => c.product_id !== p.id),
                            }))
                          }
                        />
                        {p.name} (<span className="tabular-nums">{formatMoney(p.price, language)}</span>)
                      </span>
                      {sel && (
                        <Input
                          type="number"
                          value={sel.qty}
                          onChange={(e) =>
                            setComboForm((f) => ({
                              ...f,
                              components: f.components.map((c) =>
                                c.product_id === p.id ? { ...c, qty: parseFloat(e.target.value) || 1 } : c
                              ),
                            }))
                          }
                          className="w-20 h-8"
                        />
                      )}
                    </label>
                  );
                })}
              </div>
            </div>
            <Button
              onClick={handleCreateCombo}
              disabled={submitting || !comboForm.name.trim()}
              className="w-full"
            >
              {submitting ? t('loading') : t('save')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
