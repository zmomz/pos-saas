import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
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
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  getProductsList,
  createProduct,
  updateProduct,
  deleteProduct,
  getProductVariants,
  createProductVariant,
  updateProductVariant,
  deleteProductVariant,
  getReorderSuggestions,
  type ProductVariant,
  type ReorderSuggestion,
} from '@/lib/api';
import ErrorState from '@/components/states/ErrorState';
import { DataPagination } from '@/components/DataPagination';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';

const PAGE_SIZE = 10;

interface Product {
  id: number;
  client_id?: number;
  name: string;
  name_ar?: string;
  barcode?: string;
  price: number;
  cost_price?: number;
  quantity: number;
  reorder_point?: number;
  reorder_quantity?: number;
  category?: string;
  vat_rate: number;
  is_active?: boolean;
  // POS-11 (F-011): weighted / open-price configuration.
  is_weighted?: boolean;
  is_open_price?: boolean;
  unit_label?: string;
}

// INV-08 (F-035): a product is low when on-hand <= its reorder point (when set),
// else below the legacy fixed threshold of 10. Mirrors the backend predicate.
function isLowStock(p: Product): boolean {
  const rp = p.reorder_point || 0;
  return rp > 0 ? p.quantity <= rp : p.quantity < 10;
}

interface VariantFormData {
  name: string;
  attributes: string;
  sku: string;
  barcode: string;
  price: string;
  quantity: string;
}

const emptyVariant: VariantFormData = {
  name: '',
  attributes: '',
  sku: '',
  barcode: '',
  price: '',
  quantity: '',
};

interface ProductFormData {
  name: string;
  name_ar: string;
  barcode: string;
  price: string;
  cost_price: string;
  quantity: string;
  reorder_point: string;
  reorder_quantity: string;
  category: string;
  vat_rate: string;
  // POS-11 (F-011): weighted / open-price configuration.
  is_weighted: boolean;
  is_open_price: boolean;
  unit_label: string;
}

const CATEGORIES = ['Food', 'Beverages', 'Electronics', 'Clothing', 'Other'];

const emptyForm: ProductFormData = {
  name: '',
  name_ar: '',
  barcode: '',
  price: '',
  cost_price: '',
  quantity: '',
  reorder_point: '',
  reorder_quantity: '',
  category: 'Food',
  vat_rate: '15',
  is_weighted: false,
  is_open_price: false,
  unit_label: '',
};

export default function ProductManagement() {
  const [products, setProducts] = useState<Product[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [formData, setFormData] = useState<ProductFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  // INV-04 (F-033): per-product variants (matrix) management.
  const [variantsOpen, setVariantsOpen] = useState(false);
  const [variantsProduct, setVariantsProduct] = useState<Product | null>(null);
  const [variants, setVariants] = useState<ProductVariant[]>([]);
  const [variantsLoading, setVariantsLoading] = useState(false);
  const [variantsError, setVariantsError] = useState(false);
  const [variantForm, setVariantForm] = useState<VariantFormData>(emptyVariant);
  const [editingVariantId, setEditingVariantId] = useState<number | null>(null);
  const [variantSubmitting, setVariantSubmitting] = useState(false);

  // INV-08 (F-035): auto-PO suggestions for products at/below their reorder point.
  const [suggestions, setSuggestions] = useState<ReorderSuggestion[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(true);
  const [suggestionsError, setSuggestionsError] = useState(false);

  const navigate = useNavigate();
  const { t, language, setLanguage } = useLanguage();

  useEffect(() => {
    loadProducts();
    loadSuggestions();
  }, []);

  async function loadSuggestions() {
    setSuggestionsLoading(true);
    setSuggestionsError(false);
    try {
      const data = await getReorderSuggestions();
      setSuggestions(data?.items || []);
    } catch (err) {
      console.error('Failed to load reorder suggestions:', err);
      setSuggestionsError(true);
    } finally {
      setSuggestionsLoading(false);
    }
  }

  async function loadProducts() {
    setLoading(true);
    try {
      const category = categoryFilter !== 'all' ? categoryFilter : undefined;
      const searchTerm = search.trim() || undefined;
      const data = await getProductsList(category, searchTerm);
      // /products/list returns ProductListResponse { items, total } (ISSUE-021).
      setProducts(Array.isArray(data) ? data : data?.items || []);
    } catch (err) {
      console.error('Failed to load products:', err);
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timeout = setTimeout(() => {
      setPage(1); // reset to first page whenever the filter/search changes
      loadProducts();
    }, 300);
    return () => clearTimeout(timeout);
  }, [search, categoryFilter]);

  const pagedProducts = products.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const totalProducts = products.length;
  const lowStockCount = products.filter(isLowStock).length;
  const activeProducts = products.filter((p) => p.is_active !== false).length;

  function handleFormChange(field: keyof ProductFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  // POS-11 (F-011): toggle a boolean configuration flag (weighted / open-price).
  function handleFormToggle(field: 'is_weighted' | 'is_open_price', checked: boolean) {
    setFormData((prev) => ({ ...prev, [field]: checked }));
  }

  async function handleAddProduct() {
    setSubmitting(true);
    try {
      await createProduct({
        name: formData.name,
        name_ar: formData.name_ar || undefined,
        barcode: formData.barcode || undefined,
        price: parseFloat(formData.price),
        cost_price: formData.cost_price ? parseFloat(formData.cost_price) : undefined,
        quantity: parseFloat(formData.quantity),
        reorder_point: formData.reorder_point ? parseInt(formData.reorder_point, 10) : undefined,
        reorder_quantity: formData.reorder_quantity
          ? parseInt(formData.reorder_quantity, 10)
          : undefined,
        category: formData.category || undefined,
        vat_rate: parseFloat(formData.vat_rate),
        is_weighted: formData.is_weighted,
        is_open_price: formData.is_open_price,
        unit_label: formData.unit_label || undefined,
      });
      setAddOpen(false);
      setFormData(emptyForm);
      await loadProducts();
      await loadSuggestions();
    } catch (err) {
      console.error('Failed to create product:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function openEdit(product: Product) {
    setSelectedProduct(product);
    setFormData({
      name: product.name,
      name_ar: product.name_ar || '',
      barcode: product.barcode || '',
      price: String(product.price),
      cost_price: product.cost_price ? String(product.cost_price) : '',
      quantity: String(product.quantity),
      reorder_point: product.reorder_point ? String(product.reorder_point) : '',
      reorder_quantity: product.reorder_quantity ? String(product.reorder_quantity) : '',
      category: product.category || 'Other',
      vat_rate: String(product.vat_rate),
      is_weighted: !!product.is_weighted,
      is_open_price: !!product.is_open_price,
      unit_label: product.unit_label || '',
    });
    setEditOpen(true);
  }

  async function handleEditProduct() {
    if (!selectedProduct) return;
    setSubmitting(true);
    try {
      await updateProduct(selectedProduct.id, {
        name: formData.name,
        name_ar: formData.name_ar || undefined,
        barcode: formData.barcode || undefined,
        price: parseFloat(formData.price),
        cost_price: formData.cost_price ? parseFloat(formData.cost_price) : undefined,
        quantity: parseFloat(formData.quantity),
        reorder_point: formData.reorder_point ? parseInt(formData.reorder_point, 10) : 0,
        reorder_quantity: formData.reorder_quantity ? parseInt(formData.reorder_quantity, 10) : 0,
        category: formData.category || undefined,
        vat_rate: parseFloat(formData.vat_rate),
        is_weighted: formData.is_weighted,
        is_open_price: formData.is_open_price,
        unit_label: formData.unit_label || undefined,
      });
      setEditOpen(false);
      setSelectedProduct(null);
      setFormData(emptyForm);
      await loadProducts();
      await loadSuggestions();
    } catch (err) {
      console.error('Failed to update product:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function openDelete(product: Product) {
    setSelectedProduct(product);
    setDeleteOpen(true);
  }

  async function handleDeleteProduct() {
    if (!selectedProduct) return;
    setSubmitting(true);
    try {
      await deleteProduct(selectedProduct.id);
      setDeleteOpen(false);
      setSelectedProduct(null);
      await loadProducts();
      await loadSuggestions();
    } catch (err) {
      console.error('Failed to delete product:', err);
    } finally {
      setSubmitting(false);
    }
  }

  // ---- INV-04: variant matrix editor ----
  function openVariants(product: Product) {
    setVariantsProduct(product);
    setVariantForm(emptyVariant);
    setEditingVariantId(null);
    setVariantsOpen(true);
    loadVariants(product.id);
  }

  async function loadVariants(productId: number) {
    setVariantsLoading(true);
    setVariantsError(false);
    try {
      const data = await getProductVariants(productId);
      setVariants(data);
    } catch (err) {
      console.error('Failed to load variants:', err);
      setVariantsError(true);
    } finally {
      setVariantsLoading(false);
    }
  }

  function startEditVariant(v: ProductVariant) {
    setEditingVariantId(v.id);
    setVariantForm({
      name: v.name,
      attributes: v.attributes || '',
      sku: v.sku || '',
      barcode: v.barcode || '',
      price: v.price != null ? String(v.price) : '',
      quantity: v.quantity != null ? String(v.quantity) : '',
    });
  }

  function resetVariantForm() {
    setEditingVariantId(null);
    setVariantForm(emptyVariant);
  }

  async function handleSaveVariant() {
    if (!variantsProduct || !variantForm.name) return;
    setVariantSubmitting(true);
    try {
      const payload = {
        name: variantForm.name,
        attributes: variantForm.attributes || undefined,
        sku: variantForm.sku || undefined,
        barcode: variantForm.barcode || undefined,
        price: variantForm.price ? parseFloat(variantForm.price) : undefined,
        quantity: variantForm.quantity ? parseInt(variantForm.quantity, 10) : 0,
      };
      if (editingVariantId) {
        await updateProductVariant(editingVariantId, payload);
      } else {
        await createProductVariant({
          product_id: variantsProduct.id,
          client_id: variantsProduct.client_id ?? 0,
          ...payload,
        });
      }
      resetVariantForm();
      await loadVariants(variantsProduct.id);
    } catch (err) {
      console.error('Failed to save variant:', err);
      setVariantsError(true);
    } finally {
      setVariantSubmitting(false);
    }
  }

  async function handleDeleteVariant(id: number) {
    if (!variantsProduct) return;
    try {
      await deleteProductVariant(id);
      if (editingVariantId === id) resetVariantForm();
      await loadVariants(variantsProduct.id);
    } catch (err) {
      console.error('Failed to delete variant:', err);
      setVariantsError(true);
    }
  }

  function renderForm(onSubmit: () => void, submitLabel: string) {
    return (
      <div className="space-y-4">
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Name *</label>
          <Input
            value={formData.name}
            onChange={(e) => handleFormChange('name', e.target.value)}
            placeholder="Product name"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Arabic Name</label>
          <Input
            value={formData.name_ar}
            onChange={(e) => handleFormChange('name_ar', e.target.value)}
            placeholder="اسم المنتج"
            dir="rtl"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Barcode</label>
          <Input
            value={formData.barcode}
            onChange={(e) => handleFormChange('barcode', e.target.value)}
            placeholder="e.g. 1234567890"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-sm text-slate-400 mb-1 block">{t('price')} *</label>
            <Input
              type="number"
              value={formData.price}
              onChange={(e) => handleFormChange('price', e.target.value)}
              placeholder="0.00"
              className="bg-slate-700 border-slate-600 text-white"
            />
          </div>
          <div>
            <label className="text-sm text-slate-400 mb-1 block">Cost Price</label>
            <Input
              type="number"
              value={formData.cost_price}
              onChange={(e) => handleFormChange('cost_price', e.target.value)}
              placeholder="0.00"
              className="bg-slate-700 border-slate-600 text-white"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-sm text-slate-400 mb-1 block">{t('quantity')} *</label>
            <Input
              type="number"
              value={formData.quantity}
              onChange={(e) => handleFormChange('quantity', e.target.value)}
              placeholder="0"
              className="bg-slate-700 border-slate-600 text-white"
            />
          </div>
          <div>
            <label className="text-sm text-slate-400 mb-1 block">VAT %</label>
            <Input
              type="number"
              value={formData.vat_rate}
              onChange={(e) => handleFormChange('vat_rate', e.target.value)}
              placeholder="15"
              className="bg-slate-700 border-slate-600 text-white"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-sm text-slate-400 mb-1 block">{t('reorder_point')}</label>
            <Input
              type="number"
              value={formData.reorder_point}
              onChange={(e) => handleFormChange('reorder_point', e.target.value)}
              placeholder="0"
              className="bg-slate-700 border-slate-600 text-white"
            />
          </div>
          <div>
            <label className="text-sm text-slate-400 mb-1 block">{t('reorder_quantity')}</label>
            <Input
              type="number"
              value={formData.reorder_quantity}
              onChange={(e) => handleFormChange('reorder_quantity', e.target.value)}
              placeholder="0"
              className="bg-slate-700 border-slate-600 text-white"
            />
          </div>
        </div>
        <p className="text-xs text-slate-500 -mt-2">{t('reorder_point_hint')}</p>
        {/* POS-11 (F-011): weighted & open-price configuration */}
        <div className="space-y-2 border border-slate-700 rounded-md p-3">
          <label className="flex items-center gap-2 text-sm text-slate-200">
            <input
              type="checkbox"
              checked={formData.is_weighted}
              onChange={(e) => handleFormToggle('is_weighted', e.target.checked)}
              className="h-4 w-4 accent-brand-600"
            />
            {t('weighted_item')}
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-200">
            <input
              type="checkbox"
              checked={formData.is_open_price}
              onChange={(e) => handleFormToggle('is_open_price', e.target.checked)}
              className="h-4 w-4 accent-brand-600"
            />
            {t('open_price_item')}
          </label>
          {formData.is_weighted && (
            <div>
              <label className="text-sm text-slate-400 mb-1 block">{t('unit_label')}</label>
              <Input
                value={formData.unit_label}
                onChange={(e) => handleFormChange('unit_label', e.target.value)}
                placeholder={t('unit_label_placeholder')}
                className="bg-slate-700 border-slate-600 text-white"
              />
            </div>
          )}
          <p className="text-xs text-slate-500">{t('weighted_open_price_hint')}</p>
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Category</label>
          <Select value={formData.category} onValueChange={(v) => handleFormChange('category', v)}>
            <SelectTrigger className="bg-slate-700 border-slate-600 text-white">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-800 border-slate-600">
              {CATEGORIES.map((cat) => (
                <SelectItem key={cat} value={cat} className="text-white hover:bg-slate-700">
                  {cat}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex gap-3 pt-2">
          <Button
            onClick={onSubmit}
            disabled={submitting || !formData.name || !formData.price || !formData.quantity}
            className="flex-1 bg-brand-600 hover:bg-brand-700 text-white"
          >
            {submitting ? t('loading') : submitLabel}
          </Button>
        </div>
      </div>
    );
  }

  if (loading && products.length === 0) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Header */}
      <header className="flex items-center justify-between p-4 border-b border-slate-700">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-white">{t('products')}</h1>
        </div>
        <div className="flex items-center gap-3">
          <Select value={language} onValueChange={(v) => setLanguage(v as Language)}>
            <SelectTrigger className="w-32 bg-slate-800 border-slate-600 text-white">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-800 border-slate-600">
              {languageOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value} className="text-white hover:bg-slate-700">
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            onClick={() => navigate('/client')}
            className="border-slate-600 text-slate-300 hover:bg-slate-700"
          >
            {t('back')}
          </Button>
        </div>
      </header>

      <main className="p-6 space-y-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card className="bg-slate-800 border-slate-700">
            <CardContent className="p-4">
              <p className="text-slate-400 text-sm">Total Products</p>
              <p className="text-2xl font-bold text-white">{totalProducts}</p>
            </CardContent>
          </Card>
          <Card className="bg-slate-800 border-slate-700">
            <CardContent className="p-4">
              <p className="text-slate-400 text-sm">Low Stock</p>
              <p className="text-2xl font-bold text-orange-400">{lowStockCount}</p>
            </CardContent>
          </Card>
          <Card className="bg-slate-800 border-slate-700">
            <CardContent className="p-4">
              <p className="text-slate-400 text-sm">{t('active')}</p>
              <p className="text-2xl font-bold text-green-400">{activeProducts}</p>
            </CardContent>
          </Card>
        </div>

        {/* Reorder suggestions (INV-08, F-035): loading / error / empty / list */}
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-white font-semibold">{t('reorder_suggestions')}</h2>
              <Button
                size="sm"
                variant="outline"
                onClick={loadSuggestions}
                className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs"
              >
                {t('refresh')}
              </Button>
            </div>
            {suggestionsLoading ? (
              <div className="py-6 text-center text-slate-400 animate-pulse">{t('loading')}</div>
            ) : suggestionsError ? (
              <ErrorState message={t('reorder_load_error')} onRetry={loadSuggestions} />
            ) : suggestions.length === 0 ? (
              <div className="py-6 text-center text-slate-500">{t('no_reorder_suggestions')}</div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-700">
                <table className="w-full text-sm">
                  <thead className="bg-slate-900/40">
                    <tr className="text-slate-400">
                      <th className="p-2 text-start">Name</th>
                      <th className="p-2 text-start">{t('on_hand')}</th>
                      <th className="p-2 text-start">{t('reorder_point')}</th>
                      <th className="p-2 text-start">{t('suggested_order')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {suggestions.map((s) => (
                      <tr key={s.product_id} className="border-t border-slate-700 text-slate-300">
                        <td className="p-2">
                          <span className="text-white">{s.name}</span>
                          {s.name_ar && (
                            <span className="block text-xs text-slate-500" dir="rtl">
                              {s.name_ar}
                            </span>
                          )}
                        </td>
                        <td className="p-2">
                          <Badge className="bg-red-600/20 text-red-400 border border-red-600/40">
                            {s.on_hand}
                          </Badge>
                        </td>
                        <td className="p-2">{s.reorder_point}</td>
                        <td className="p-2 font-semibold text-brand-300">
                          {s.suggested_order_quantity}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Search, Filter, Add */}
        <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search products..."
            className="flex-1 bg-slate-800 border-slate-600 text-white placeholder:text-slate-500"
          />
          <Select value={categoryFilter} onValueChange={setCategoryFilter}>
            <SelectTrigger className="w-40 bg-slate-800 border-slate-600 text-white">
              <SelectValue placeholder="Category" />
            </SelectTrigger>
            <SelectContent className="bg-slate-800 border-slate-600">
              <SelectItem value="all" className="text-white hover:bg-slate-700">
                All Categories
              </SelectItem>
              {CATEGORIES.map((cat) => (
                <SelectItem key={cat} value={cat} className="text-white hover:bg-slate-700">
                  {cat}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Add Product Dialog */}
          <Dialog open={addOpen} onOpenChange={setAddOpen}>
            <DialogTrigger asChild>
              <Button
                onClick={() => setFormData(emptyForm)}
                className="bg-brand-600 hover:bg-brand-700 text-white"
              >
                + Add Product
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle className="text-white">Add New Product</DialogTitle>
              </DialogHeader>
              {renderForm(handleAddProduct, 'Add Product')}
            </DialogContent>
          </Dialog>
        </div>

        {/* Products Table */}
        <div className="overflow-x-auto rounded-lg border border-slate-700">
          <table className="w-full text-sm">
            <thead className="bg-slate-800">
              <tr className="text-slate-400">
                <th className="p-3 text-start">Name</th>
                <th className="p-3 text-start">Category</th>
                <th className="p-3 text-start">{t('price')}</th>
                <th className="p-3 text-start">Stock</th>
                <th className="p-3 text-start">VAT%</th>
                <th className="p-3 text-start">{t('status')}</th>
                <th className="p-3 text-start">Actions</th>
              </tr>
            </thead>
            <tbody>
              {products.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-slate-500">
                    {t('no_products')}
                  </td>
                </tr>
              ) : (
                pagedProducts.map((product) => (
                  <tr key={product.id} className="border-t border-slate-700 text-slate-300">
                    <td className="p-3">
                      <div>
                        <span className="text-white font-medium">{product.name}</span>
                        {product.name_ar && (
                          <span className="block text-xs text-slate-400" dir="rtl">
                            {product.name_ar}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="p-3">
                      <Badge className="bg-slate-700 text-slate-300">
                        {product.category || 'Other'}
                      </Badge>
                    </td>
                    <td className="p-3">${product.price.toFixed(2)}</td>
                    <td className="p-3">
                      {isLowStock(product) ? (
                        <Badge className="bg-red-600/20 text-red-400 border border-red-600/40">
                          {product.quantity}
                          {(product.reorder_point || 0) > 0 && (
                            <span className="ms-1 text-[10px] opacity-70">
                              / {product.reorder_point}
                            </span>
                          )}
                        </Badge>
                      ) : (
                        <span>{product.quantity}</span>
                      )}
                    </td>
                    <td className="p-3">{product.vat_rate}%</td>
                    <td className="p-3">
                      {product.is_active !== false ? (
                        <Badge className="bg-green-600/20 text-green-400 border border-green-600/40">
                          {t('active')}
                        </Badge>
                      ) : (
                        <Badge className="bg-slate-600/20 text-slate-400 border border-slate-600/40">
                          {t('inactive')}
                        </Badge>
                      )}
                    </td>
                    <td className="p-3">
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => openVariants(product)}
                          className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs"
                        >
                          {t('variants')}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => openEdit(product)}
                          className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs"
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => openDelete(product)}
                          className="border-red-600/50 text-red-400 hover:bg-red-600/20 text-xs"
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <DataPagination
          page={page}
          pageSize={PAGE_SIZE}
          total={products.length}
          onPageChange={setPage}
        />
      </main>

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-white">Edit Product</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditProduct, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Confirm Delete</DialogTitle>
          </DialogHeader>
          <p className="text-slate-300">
            Are you sure you want to delete <strong>{selectedProduct?.name}</strong>? This action
            cannot be undone.
          </p>
          <div className="flex gap-3 pt-4">
            <Button
              variant="outline"
              onClick={() => setDeleteOpen(false)}
              className="flex-1 border-slate-600 text-slate-300 hover:bg-slate-700"
            >
              {t('cancel')}
            </Button>
            <Button
              onClick={handleDeleteProduct}
              disabled={submitting}
              className="flex-1 bg-red-600 hover:bg-red-700 text-white"
            >
              {submitting ? t('loading') : 'Delete'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Variants Matrix Editor (INV-04, F-033) */}
      <Dialog open={variantsOpen} onOpenChange={setVariantsOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-white">
              {t('variants')} — {variantsProduct?.name}
            </DialogTitle>
          </DialogHeader>

          {/* Existing variants: loading / error (distinct from empty) / empty / list */}
          {variantsLoading ? (
            <div className="py-8 text-center text-slate-400 animate-pulse">{t('loading')}</div>
          ) : variantsError ? (
            <ErrorState
              message={t('variant_load_error')}
              onRetry={() => variantsProduct && loadVariants(variantsProduct.id)}
            />
          ) : variants.length === 0 ? (
            <div className="py-6 text-center text-slate-500">{t('no_variants')}</div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-700">
              <table className="w-full text-sm">
                <thead className="bg-slate-900/40">
                  <tr className="text-slate-400">
                    <th className="p-2 text-start">{t('variant_name')}</th>
                    <th className="p-2 text-start">{t('barcode')}</th>
                    <th className="p-2 text-start">{t('price')}</th>
                    <th className="p-2 text-start">{t('stock')}</th>
                    <th className="p-2 text-start"></th>
                  </tr>
                </thead>
                <tbody>
                  {variants.map((v) => (
                    <tr key={v.id} className="border-t border-slate-700 text-slate-300">
                      <td className="p-2">
                        <span className="text-white">{v.name}</span>
                        {v.attributes && (
                          <span className="block text-xs text-slate-500">{v.attributes}</span>
                        )}
                      </td>
                      <td className="p-2 font-mono text-xs">{v.barcode || '—'}</td>
                      <td className="p-2">{v.price != null ? v.price.toFixed(2) : '—'}</td>
                      <td className="p-2">{v.quantity ?? 0}</td>
                      <td className="p-2">
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => startEditVariant(v)}
                            className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs"
                          >
                            {t('edit')}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleDeleteVariant(v.id)}
                            className="border-red-600/50 text-red-400 hover:bg-red-600/20 text-xs"
                          >
                            {t('delete')}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Add / edit a variant */}
          <div className="mt-2 space-y-3 rounded-lg border border-slate-700 p-3">
            <p className="text-sm font-medium text-slate-300">
              {editingVariantId ? t('edit_variant') : t('add_variant')}
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-slate-400 mb-1 block">{t('variant_name')} *</label>
                <Input
                  value={variantForm.name}
                  onChange={(e) => setVariantForm((p) => ({ ...p, name: e.target.value }))}
                  placeholder="Red / Large"
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 mb-1 block">{t('variant_attributes')}</label>
                <Input
                  value={variantForm.attributes}
                  onChange={(e) => setVariantForm((p) => ({ ...p, attributes: e.target.value }))}
                  placeholder='{"size":"L","color":"Red"}'
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 mb-1 block">{t('barcode')}</label>
                <Input
                  value={variantForm.barcode}
                  onChange={(e) => setVariantForm((p) => ({ ...p, barcode: e.target.value }))}
                  placeholder="e.g. TSHIRT-RED-L"
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 mb-1 block">SKU</label>
                <Input
                  value={variantForm.sku}
                  onChange={(e) => setVariantForm((p) => ({ ...p, sku: e.target.value }))}
                  placeholder="SKU"
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 mb-1 block">{t('price')}</label>
                <Input
                  type="number"
                  value={variantForm.price}
                  onChange={(e) => setVariantForm((p) => ({ ...p, price: e.target.value }))}
                  placeholder="0.00"
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 mb-1 block">{t('stock')}</label>
                <Input
                  type="number"
                  value={variantForm.quantity}
                  onChange={(e) => setVariantForm((p) => ({ ...p, quantity: e.target.value }))}
                  placeholder="0"
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                onClick={handleSaveVariant}
                disabled={variantSubmitting || !variantForm.name}
                className="bg-brand-600 hover:bg-brand-700 text-white"
              >
                {variantSubmitting ? t('loading') : editingVariantId ? t('save') : t('add_variant')}
              </Button>
              {editingVariantId && (
                <Button
                  variant="outline"
                  onClick={resetVariantForm}
                  className="border-slate-600 text-slate-300 hover:bg-slate-700"
                >
                  {t('cancel')}
                </Button>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}