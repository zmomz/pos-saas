import { useEffect, useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
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
  type ModifierGroup,
  type Modifier,
  type Combo,
  type ComboComponentRef,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { UtensilsCrossed, Plus, Trash2, WifiOff, AlertTriangle, Lock, Layers } from 'lucide-react';

interface ProductLite {
  id: number;
  name: string;
  price: number;
}

export default function MenuBuilder() {
  const { t } = useLanguage();

  const [groups, setGroups] = useState<ModifierGroup[]>([]);
  const [modsByGroup, setModsByGroup] = useState<Record<number, Modifier[]>>({});
  const [combos, setCombos] = useState<Combo[]>([]);
  const [products, setProducts] = useState<ProductLite[]>([]);

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
      setGroups(safeGroups);
      setCombos(Array.isArray(cmb) ? cmb : []);
      setProducts(Array.isArray(prods) ? (prods as ProductLite[]) : []);
      // Pull each group's modifiers for display.
      const entries = await Promise.all(
        safeGroups.map(async (g) => [g.id, await getModifiers(g.id).catch(() => [])] as const)
      );
      setModsByGroup(Object.fromEntries(entries));
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

  // ---- Loading state ----
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  // ---- Permission-denied state (retail business_type / feature off) ----
  if (denied) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="bg-slate-800 border-slate-700 max-w-md">
          <CardContent className="p-8 text-center">
            <Lock className="h-12 w-12 text-slate-500 mx-auto mb-3" />
            <h3 className="text-white font-semibold mb-2">{t('restaurant_disabled')}</h3>
            <p className="text-slate-400 text-sm">{t('restaurant_disabled_desc')}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ---- Error state ----
  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="bg-slate-800 border-slate-700 max-w-md">
          <CardContent className="p-8 text-center">
            <AlertTriangle className="h-12 w-12 text-red-400 mx-auto mb-3" />
            <p className="text-slate-300 mb-4">{t('menu_load_error')}</p>
            <Button onClick={load} className="bg-brand-600 hover:bg-brand-700 text-white">
              {t('retry')}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {!online && (
        <div className="flex items-center gap-2 rounded-md border border-amber-600/40 bg-amber-500/10 px-4 py-2 text-amber-300 text-sm">
          <WifiOff className="h-4 w-4" />
          <span>{t('you_are_offline')}</span>
        </div>
      )}

      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <UtensilsCrossed className="h-6 w-6 text-brand-400" />
          {t('menu_builder')}
        </h2>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setGroupOpen(true)} className="bg-brand-600 hover:bg-brand-700 text-white">
            <Plus className="h-4 w-4 mr-2" /> {t('add_modifier_group')}
          </Button>
          <Button
            variant="outline"
            onClick={() => setComboOpen(true)}
            className="border-slate-600 text-slate-300 hover:bg-slate-700"
          >
            <Layers className="h-4 w-4 mr-2" /> {t('add_combo')}
          </Button>
        </div>
      </div>

      {/* Modifier groups */}
      <div>
        <h3 className="text-white font-semibold mb-2">{t('modifier_groups')}</h3>
        {groups.length === 0 ? (
          <Card className="bg-slate-800 border-slate-700">
            <CardContent className="p-8 text-center">
              <UtensilsCrossed className="h-10 w-10 text-slate-600 mx-auto mb-2" />
              <p className="text-slate-400 text-sm">{t('no_modifier_groups')}</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {groups.map((g) => (
              <Card key={g.id} className="bg-slate-800 border-slate-700">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-white font-medium">{g.name}</span>
                      {g.required && (
                        <Badge className="bg-amber-500/20 text-amber-400">{t('required')}</Badge>
                      )}
                      <span className="text-xs text-slate-400">
                        {g.min_select ?? 0}–{g.max_select ?? 1}
                      </span>
                    </div>
                    <button
                      onClick={() => deleteModifierGroup(g.id).then(load)}
                      className="text-slate-400 hover:text-red-400"
                      aria-label={t('delete')}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="space-y-1">
                    {(modsByGroup[g.id] || []).map((m) => (
                      <div
                        key={m.id}
                        className="flex items-center justify-between text-sm text-slate-300"
                      >
                        <span>{m.name}</span>
                        <span className="flex items-center gap-3">
                          {m.price_delta !== 0 && (
                            <span className="text-xs text-slate-400">
                              {m.price_delta > 0 ? '+' : ''}
                              {m.price_delta}
                            </span>
                          )}
                          <button
                            onClick={() => deleteModifier(m.id).then(load)}
                            className="text-slate-500 hover:text-red-400"
                            aria-label={t('delete')}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </span>
                      </div>
                    ))}
                    {(modsByGroup[g.id] || []).length === 0 && (
                      <p className="text-xs text-slate-500">{t('no_modifiers')}</p>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setModForm({ name: '', name_ar: '', price_delta: 0 });
                      setModOpen(g);
                    }}
                    className="mt-3 border-slate-600 text-slate-300 hover:bg-slate-700"
                  >
                    <Plus className="h-3.5 w-3.5 mr-1" /> {t('add_modifier')}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Combos */}
      <div>
        <h3 className="text-white font-semibold mb-2">{t('combos')}</h3>
        {combos.length === 0 ? (
          <Card className="bg-slate-800 border-slate-700">
            <CardContent className="p-8 text-center">
              <Layers className="h-10 w-10 text-slate-600 mx-auto mb-2" />
              <p className="text-slate-400 text-sm">{t('no_combos')}</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {combos.map((c) => (
              <Card key={c.id} className="bg-slate-800 border-slate-700">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-white font-medium">{c.name}</span>
                    <button
                      onClick={() => deleteCombo(c.id).then(load)}
                      className="text-slate-400 hover:text-red-400"
                      aria-label={t('delete')}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="mt-2 text-sm">
                    <span className="text-white font-semibold">{c.bundle_price.toFixed(2)}</span>
                    {c.component_sum != null && c.component_sum > c.bundle_price && (
                      <span className="text-xs text-slate-400 ml-2 line-through">
                        {c.component_sum.toFixed(2)}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 mt-1">
                    {t('components')}: {c.components.length}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Create modifier-group dialog */}
      <Dialog open={groupOpen} onOpenChange={setGroupOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">{t('add_modifier_group')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('name')}</label>
              <Input
                value={groupForm.name}
                onChange={(e) => setGroupForm((f) => ({ ...f, name: e.target.value }))}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('name_ar')}</label>
              <Input
                value={groupForm.name_ar}
                onChange={(e) => setGroupForm((f) => ({ ...f, name_ar: e.target.value }))}
                className="bg-slate-700 border-slate-600 text-white"
                dir="rtl"
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={groupForm.required}
                onChange={(e) => setGroupForm((f) => ({ ...f, required: e.target.checked }))}
              />
              {t('required')}
            </label>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm text-slate-400 mb-1 block">{t('min_select')}</label>
                <Input
                  type="number"
                  value={groupForm.min_select}
                  onChange={(e) => setGroupForm((f) => ({ ...f, min_select: parseInt(e.target.value) || 0 }))}
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
              <div>
                <label className="text-sm text-slate-400 mb-1 block">{t('max_select')}</label>
                <Input
                  type="number"
                  value={groupForm.max_select}
                  onChange={(e) => setGroupForm((f) => ({ ...f, max_select: parseInt(e.target.value) || 1 }))}
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
            </div>
            <Button
              onClick={handleCreateGroup}
              disabled={submitting || !groupForm.name.trim()}
              className="w-full bg-brand-600 hover:bg-brand-700 text-white"
            >
              {submitting ? t('loading') : t('save')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Create modifier dialog */}
      <Dialog open={!!modOpen} onOpenChange={(o) => !o && setModOpen(null)}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">
              {t('add_modifier')} — {modOpen?.name}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('name')}</label>
              <Input
                value={modForm.name}
                onChange={(e) => setModForm((f) => ({ ...f, name: e.target.value }))}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('name_ar')}</label>
              <Input
                value={modForm.name_ar}
                onChange={(e) => setModForm((f) => ({ ...f, name_ar: e.target.value }))}
                className="bg-slate-700 border-slate-600 text-white"
                dir="rtl"
              />
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('price_delta')}</label>
              <Input
                type="number"
                value={modForm.price_delta}
                onChange={(e) => setModForm((f) => ({ ...f, price_delta: parseFloat(e.target.value) || 0 }))}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>
            <Button
              onClick={handleCreateModifier}
              disabled={submitting || !modForm.name.trim()}
              className="w-full bg-brand-600 hover:bg-brand-700 text-white"
            >
              {submitting ? t('loading') : t('save')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Create combo dialog */}
      <Dialog open={comboOpen} onOpenChange={setComboOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-white">{t('add_combo')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('name')}</label>
              <Input
                value={comboForm.name}
                onChange={(e) => setComboForm((f) => ({ ...f, name: e.target.value }))}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('bundle_price')}</label>
              <Input
                type="number"
                value={comboForm.bundle_price}
                onChange={(e) =>
                  setComboForm((f) => ({ ...f, bundle_price: parseFloat(e.target.value) || 0 }))
                }
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('components')}</label>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {products.map((p) => {
                  const sel = comboForm.components.find((c) => c.product_id === p.id);
                  return (
                    <label
                      key={p.id}
                      className="flex items-center justify-between gap-2 text-sm text-slate-300"
                    >
                      <span className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={!!sel}
                          onChange={(e) =>
                            setComboForm((f) => ({
                              ...f,
                              components: e.target.checked
                                ? [...f.components, { product_id: p.id, qty: 1 }]
                                : f.components.filter((c) => c.product_id !== p.id),
                            }))
                          }
                        />
                        {p.name} ({p.price})
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
                          className="bg-slate-700 border-slate-600 text-white w-20 h-8"
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
              className="w-full bg-brand-600 hover:bg-brand-700 text-white"
            >
              {submitting ? t('loading') : t('save')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
