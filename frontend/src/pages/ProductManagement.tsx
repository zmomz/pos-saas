import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
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
  DialogTrigger,
} from '@/components/ui/dialog';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import DataTable, { type DataTableColumn } from '@/components/dashboard/rx/DataTable';
import StatTile from '@/components/dashboard/StatTile';
import { formatMoney } from '@/lib/format';
import { Package as PackageIcon, AlertTriangle, CheckCircle2, Plus } from 'lucide-react';
import {
  getProductsList,
  createProduct,
  updateProduct,
  deleteProduct,
  restoreProduct,
  getProductVariants,
  createProductVariant,
  updateProductVariant,
  deleteProductVariant,
  getReorderSuggestions,
  exportProductsCsv,
  importProductsCsv,
  getCategories,
  uploadProductImage,
  productImageSrc,
  type ProductVariant,
  type ReorderSuggestion,
  type CsvImportResult,
} from '@/lib/api';
import ErrorState from '@/components/states/ErrorState';
import { DataPagination } from '@/components/DataPagination';
import { useLanguage } from '@/lib/i18n';

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
  category_id?: number | null;
  vat_rate: number;
  is_active?: boolean;
  // POS-11 (F-011): weighted / open-price configuration.
  is_weighted?: boolean;
  is_open_price?: boolean;
  unit_label?: string;
  // ISSUE-065 (P2 catalog): served URL of the product image.
  image_url?: string | null;
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
  // H7 (ISSUE-038): the linked category id ('' = uncategorised). Sourced from the
  // merchant's category tree rather than a hardcoded list.
  category_id: string;
  vat_rate: string;
  // POS-11 (F-011): weighted / open-price configuration.
  is_weighted: boolean;
  is_open_price: boolean;
  unit_label: string;
}

// H7 (ISSUE-038): the merchant's category tree, loaded from getCategories().
interface Category {
  id: number;
  name: string;
}

// Sentinel Select value for "no category" (Radix Select disallows an empty value).
const NO_CATEGORY = 'none';

const emptyForm: ProductFormData = {
  name: '',
  name_ar: '',
  barcode: '',
  price: '',
  cost_price: '',
  quantity: '',
  reorder_point: '',
  reorder_quantity: '',
  category_id: '',
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
  // ISSUE-068: opt in to see archived (soft-deleted) products so they can be restored.
  const [showArchived, setShowArchived] = useState(false);
  // H7 (ISSUE-038): the merchant's categories, sourced for the form + filter.
  const [categories, setCategories] = useState<Category[]>([]);
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

  // ISSUE-064: catalog CSV import/export.
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<CsvImportResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { t, tt, language } = useLanguage();

  useEffect(() => {
    loadProducts();
    loadSuggestions();
    loadCategories();
  }, []);

  // H7 (ISSUE-038): source the category options from the merchant's category tree.
  async function loadCategories() {
    try {
      const data = await getCategories();
      const items = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : [];
      setCategories(items.map((c: { id: number; name: string }) => ({ id: c.id, name: c.name })));
    } catch (err) {
      console.error('Failed to load categories:', err);
      setCategories([]);
    }
  }

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
      // H7 (ISSUE-038): filter by the linked category id.
      const categoryId = categoryFilter !== 'all' ? categoryFilter : undefined;
      const searchTerm = search.trim() || undefined;
      const data = await getProductsList(categoryId, searchTerm, showArchived);
      // /products/list returns ProductListResponse { items, total } (ISSUE-021).
      setProducts((Array.isArray(data?.items) ? data.items : []) as unknown as Product[]);
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
  }, [search, categoryFilter, showArchived]);

  // ISSUE-064: catalog CSV export/import.
  async function handleExportCsv() {
    try {
      const blob = await exportProductsCsv();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'products.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to export catalog:', err);
    }
  }

  async function handleImportCsv(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-importing the same file
    if (!file) return;
    setImporting(true);
    setImportResult(null);
    try {
      const result = await importProductsCsv(file);
      setImportResult(result);
      await loadProducts();
    } catch (err) {
      console.error('Failed to import catalog:', err);
    } finally {
      setImporting(false);
    }
  }

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
        category_id: formData.category_id ? parseInt(formData.category_id, 10) : undefined,
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
      category_id: product.category_id != null ? String(product.category_id) : '',
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
        category_id: formData.category_id ? parseInt(formData.category_id, 10) : null,
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

  // ISSUE-068: un-archive a soft-deleted product so it reappears in the catalog/POS.
  async function handleRestoreProduct(product: Product) {
    setSubmitting(true);
    try {
      await restoreProduct(product.id);
      await loadProducts();
      await loadSuggestions();
    } catch (err) {
      console.error('Failed to restore product:', err);
    } finally {
      setSubmitting(false);
    }
  }

  // ISSUE-065 (P2 catalog): upload an image for a product; the served URL is
  // persisted and surfaces in the catalog table + the POS tile grid.
  async function handleImageUpload(product: Product, file: File) {
    setSubmitting(true);
    try {
      await uploadProductImage(product.id, file);
      await loadProducts();
    } catch (err) {
      console.error('Failed to upload product image:', err);
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
          <Label className="mb-1 block">{tt('name', 'Name')} *</Label>
          <Input
            value={formData.name}
            onChange={(e) => handleFormChange('name', e.target.value)}
            placeholder={tt('product_name_placeholder', 'Product name')}
          />
        </div>
        <div>
          <Label className="mb-1 block">{tt('arabic_name', 'Arabic Name')}</Label>
          <Input
            value={formData.name_ar}
            onChange={(e) => handleFormChange('name_ar', e.target.value)}
            placeholder="اسم المنتج"
            dir="rtl"
          />
        </div>
        <div>
          <Label className="mb-1 block">{tt('barcode', 'Barcode')}</Label>
          <Input
            value={formData.barcode}
            onChange={(e) => handleFormChange('barcode', e.target.value)}
            placeholder="e.g. 1234567890"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="mb-1 block">{t('price')} *</Label>
            <Input
              type="number"
              value={formData.price}
              onChange={(e) => handleFormChange('price', e.target.value)}
              placeholder="0.00"
            />
          </div>
          <div>
            <Label className="mb-1 block">{tt('cost_price', 'Cost Price')}</Label>
            <Input
              type="number"
              value={formData.cost_price}
              onChange={(e) => handleFormChange('cost_price', e.target.value)}
              placeholder="0.00"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="mb-1 block">{t('quantity')} *</Label>
            <Input
              type="number"
              value={formData.quantity}
              onChange={(e) => handleFormChange('quantity', e.target.value)}
              placeholder="0"
            />
          </div>
          <div>
            <Label className="mb-1 block">{tt('vat_percent', 'VAT %')}</Label>
            <Input
              type="number"
              value={formData.vat_rate}
              onChange={(e) => handleFormChange('vat_rate', e.target.value)}
              placeholder="15"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="mb-1 block">{t('reorder_point')}</Label>
            <Input
              type="number"
              value={formData.reorder_point}
              onChange={(e) => handleFormChange('reorder_point', e.target.value)}
              placeholder="0"
            />
          </div>
          <div>
            <Label className="mb-1 block">{t('reorder_quantity')}</Label>
            <Input
              type="number"
              value={formData.reorder_quantity}
              onChange={(e) => handleFormChange('reorder_quantity', e.target.value)}
              placeholder="0"
            />
          </div>
        </div>
        <p className="text-xs text-muted-foreground -mt-2">{t('reorder_point_hint')}</p>
        {/* POS-11 (F-011): weighted & open-price configuration */}
        <div className="space-y-2 border border-border rounded-md p-3">
          <label className="flex items-center gap-2 text-sm text-foreground">
            <Checkbox
              checked={formData.is_weighted}
              onCheckedChange={(c) => handleFormToggle('is_weighted', c === true)}
            />
            {t('weighted_item')}
          </label>
          <label className="flex items-center gap-2 text-sm text-foreground">
            <Checkbox
              checked={formData.is_open_price}
              onCheckedChange={(c) => handleFormToggle('is_open_price', c === true)}
            />
            {t('open_price_item')}
          </label>
          {formData.is_weighted && (
            <div>
              <Label className="mb-1 block">{t('unit_label')}</Label>
              <Input
                value={formData.unit_label}
                onChange={(e) => handleFormChange('unit_label', e.target.value)}
                placeholder={t('unit_label_placeholder')}
              />
            </div>
          )}
          <p className="text-xs text-muted-foreground">{t('weighted_open_price_hint')}</p>
        </div>
        <div>
          <Label className="mb-1 block">{t('category')}</Label>
          <Select
            value={formData.category_id || NO_CATEGORY}
            onValueChange={(v) =>
              handleFormChange('category_id', v === NO_CATEGORY ? '' : v)
            }
          >
            <SelectTrigger>
              <SelectValue placeholder={t('category')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_CATEGORY}>
                {t('no_category')}
              </SelectItem>
              {categories.map((cat) => (
                <SelectItem
                  key={cat.id}
                  value={String(cat.id)}
                >
                  {cat.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex gap-3 pt-2">
          <Button
            onClick={onSubmit}
            disabled={submitting || !formData.name || !formData.price || !formData.quantity}
            className="flex-1"
          >
            {submitting ? t('loading') : submitLabel}
          </Button>
        </div>
      </div>
    );
  }

  const suggestionColumns: DataTableColumn<ReorderSuggestion>[] = [
    {
      header: tt('name', 'Name'),
      cell: (s) => (
        <>
          <span className="text-foreground">{s.name}</span>
          {s.name_ar && (
            <span className="block text-xs text-muted-foreground" dir="rtl">
              {s.name_ar}
            </span>
          )}
        </>
      ),
    },
    {
      header: t('on_hand'),
      cell: (s) => <span className="pill-danger tabular-nums">{s.on_hand}</span>,
    },
    {
      header: t('reorder_point'),
      cell: (s) => <span className="tabular-nums">{s.reorder_point}</span>,
    },
    {
      header: t('suggested_order'),
      cell: (s) => (
        <span className="font-semibold text-brand-700 tabular-nums">
          {s.suggested_order_quantity}
        </span>
      ),
    },
  ];

  const productColumns: DataTableColumn<Product>[] = [
    {
      header: tt('name', 'Name'),
      cell: (product) => (
        <div className="flex items-center gap-3">
          {/* ISSUE-065: image thumbnail, or the name initial fallback. */}
          {productImageSrc(product.image_url) ? (
            <img
              src={productImageSrc(product.image_url)}
              alt={product.name}
              className="h-10 w-10 shrink-0 rounded-lg object-cover"
            />
          ) : (
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-muted text-sm font-semibold text-foreground/90">
              {product.name?.charAt(0)?.toUpperCase() || '?'}
            </span>
          )}
          <div>
            <span className="text-foreground font-medium">{product.name}</span>
            {product.name_ar && (
              <span className="block text-xs text-muted-foreground" dir="rtl">
                {product.name_ar}
              </span>
            )}
          </div>
        </div>
      ),
    },
    {
      header: t('category'),
      cell: (product) => (
        <span className="pill-muted">{product.category || tt('other', 'Other')}</span>
      ),
    },
    {
      header: t('price'),
      cell: (product) => (
        <span className="tabular-nums">{formatMoney(product.price, language)}</span>
      ),
    },
    {
      header: tt('stock', 'Stock'),
      cell: (product) =>
        isLowStock(product) ? (
          <span className="pill-danger tabular-nums">
            {product.quantity}
            {(product.reorder_point || 0) > 0 && (
              <span className="ms-1 text-[10px] opacity-70">
                / {product.reorder_point}
              </span>
            )}
          </span>
        ) : (
          <span className="tabular-nums">{product.quantity}</span>
        ),
    },
    {
      header: tt('vat_percent', 'VAT%'),
      cell: (product) => <span className="tabular-nums">{product.vat_rate}%</span>,
    },
    {
      header: t('status'),
      cell: (product) =>
        product.is_active !== false ? (
          <span className="pill-success">{t('active')}</span>
        ) : (
          <span className="pill-muted">{t('inactive')}</span>
        ),
    },
    {
      header: tt('actions', 'Actions'),
      cell: (product) => (
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => openVariants(product)}
            className="text-xs"
          >
            {t('variants')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => openEdit(product)}
            className="text-xs"
          >
            {tt('edit', 'Edit')}
          </Button>
          {/* ISSUE-065: upload a product image (catalog + POS tile). */}
          <label className="inline-flex cursor-pointer items-center rounded-md border border-input px-3 py-1.5 text-xs text-foreground/90 hover:bg-muted">
            {t('image')}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              className="hidden"
              disabled={submitting}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleImageUpload(product, file);
                e.target.value = '';
              }}
            />
          </label>
          {product.is_active === false ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleRestoreProduct(product)}
              disabled={submitting}
              className="border-success/40 text-success hover:bg-success/10 text-xs"
            >
              {t('restore')}
            </Button>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onClick={() => openDelete(product)}
              className="border-danger/40 text-danger hover:bg-danger/10 text-xs"
            >
              {tt('delete', 'Delete')}
            </Button>
          )}
        </div>
      ),
    },
  ];

  const variantColumns: DataTableColumn<ProductVariant>[] = [
    {
      header: t('variant_name'),
      cell: (v) => (
        <>
          <span className="text-foreground">{v.name}</span>
          {v.attributes && (
            <span className="block text-xs text-muted-foreground">{v.attributes}</span>
          )}
        </>
      ),
    },
    {
      header: t('barcode'),
      cell: (v) => <span className="font-mono text-xs">{v.barcode || '—'}</span>,
    },
    {
      header: t('price'),
      cell: (v) => (
        <span className="tabular-nums">
          {v.price != null ? formatMoney(v.price, language) : '—'}
        </span>
      ),
    },
    {
      header: t('stock'),
      cell: (v) => <span className="tabular-nums">{v.quantity ?? 0}</span>,
    },
    {
      header: '',
      cell: (v) => (
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => startEditVariant(v)}
            className="text-xs"
          >
            {t('edit')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleDeleteVariant(v.id)}
            className="border-danger/40 text-danger hover:bg-danger/10 text-xs"
          >
            {t('delete')}
          </Button>
        </div>
      ),
    },
  ];

  if (loading && products.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-foreground animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-6">
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><PackageIcon className="h-[18px] w-[18px]" /></span>}
        title={t('products')}
        subtitle={`${totalProducts} ${t('products')}`}
      >
        <Button
          variant="outline"
          onClick={handleExportCsv}
        >
          {t('export_csv')}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv"
          onChange={handleImportCsv}
          className="hidden"
          data-testid="csv-import-input"
        />
        <Button
          variant="outline"
          disabled={importing}
          onClick={() => fileInputRef.current?.click()}
        >
          {importing ? t('loading') : t('import_csv')}
        </Button>
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button
              onClick={() => setFormData(emptyForm)}
              className="h-11 rounded-[10px] shadow-brand"
            >
              <Plus className="h-4 w-4" />
              {tt('add_product', 'Add Product')}
            </Button>
          </DialogTrigger>
          <DialogContent className="max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{tt('add_new_product', 'Add New Product')}</DialogTitle>
            </DialogHeader>
            {renderForm(handleAddProduct, tt('add_product', 'Add Product'))}
          </DialogContent>
        </Dialog>
      </PageHeading>

      {/* Stats Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile icon={PackageIcon} label={tt('total_products', 'Total Products')} value={totalProducts} tone="brand" />
        <StatTile icon={AlertTriangle} label={tt('low_stock', 'Low Stock')} value={lowStockCount} tone="warning" />
        <StatTile icon={CheckCircle2} label={t('active')} value={activeProducts} tone="success" />
      </div>

      {/* Reorder suggestions (INV-08, F-035): loading / error / empty / list */}
      <div className="dxr-tile">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[16px] font-extrabold tracking-tight">{t('reorder_suggestions')}</h2>
          <Button
            size="sm"
            variant="outline"
            onClick={loadSuggestions}
            className="text-xs"
          >
            {t('refresh')}
          </Button>
        </div>
        {suggestionsLoading ? (
          <div className="py-6 text-center text-muted-foreground animate-pulse">{t('loading')}</div>
        ) : suggestionsError ? (
          <ErrorState message={t('reorder_load_error')} onRetry={loadSuggestions} />
        ) : suggestions.length === 0 ? (
          <div className="py-6 text-center text-muted-foreground">{t('no_reorder_suggestions')}</div>
        ) : (
          <div className="rounded-lg border border-border">
            <DataTable
              columns={suggestionColumns}
              rows={suggestions}
              rowKey={(s) => s.product_id}
            />
          </div>
        )}
      </div>

      {/* Search, Filter */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={tt('search_products_placeholder', 'Search products...')}
          className="flex-1"
        />
        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder={t('category')} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">
              {t('all_categories')}
            </SelectItem>
            {categories.map((cat) => (
              <SelectItem
                key={cat.id}
                value={String(cat.id)}
              >
                {cat.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* ISSUE-068: opt in to see archived products so they can be restored. */}
        <label className="flex items-center gap-2 text-sm text-foreground/90 whitespace-nowrap">
          <Checkbox
            checked={showArchived}
            onCheckedChange={(c) => setShowArchived(c === true)}
          />
          {t('show_archived')}
        </label>
      </div>

      {/* ISSUE-064: import outcome — created/updated counts + rejected rows. */}
      {importResult && (
        <div className="dxr-tile space-y-2">
          <p className="text-foreground text-sm">
            {t('import_summary')
              .replace('{created}', String(importResult.created))
              .replace('{updated}', String(importResult.updated))}
          </p>
          {importResult.errors.length > 0 && (
            <div className="text-sm text-warning">
              <p className="font-semibold">
                {t('import_rejected').replace('{count}', String(importResult.errors.length))}
              </p>
              <ul className="list-disc ms-5 mt-1 space-y-0.5">
                {importResult.errors.map((err) => (
                  <li key={err.row}>
                    {t('row')} {err.row}: {err.errors.join('; ')}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Products Table */}
      <div className="dxr-tile p-0">
        <DataTable
          columns={productColumns}
          rows={pagedProducts}
          rowKey={(product) => product.id}
          empty={t('no_products')}
        />
      </div>

      <DataPagination
        page={page}
        pageSize={PAGE_SIZE}
        total={products.length}
        onPageChange={setPage}
      />

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{tt('edit_product', 'Edit Product')}</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditProduct, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{tt('confirm_delete', 'Confirm Delete')}</DialogTitle>
          </DialogHeader>
          <p className="text-foreground/90">
            {tt('delete_product_confirm_prefix', 'Are you sure you want to delete')} <strong>{selectedProduct?.name}</strong>? {tt('action_cannot_be_undone', 'This action cannot be undone.')}
          </p>
          <div className="flex gap-3 pt-4">
            <Button
              variant="outline"
              onClick={() => setDeleteOpen(false)}
              className="flex-1"
            >
              {t('cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteProduct}
              disabled={submitting}
              className="flex-1"
            >
              {submitting ? t('loading') : tt('delete', 'Delete')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Variants Matrix Editor (INV-04, F-033) */}
      <Dialog open={variantsOpen} onOpenChange={setVariantsOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {t('variants')} — {variantsProduct?.name}
            </DialogTitle>
          </DialogHeader>

          {/* Existing variants: loading / error (distinct from empty) / empty / list */}
          {variantsLoading ? (
            <div className="py-8 text-center text-muted-foreground animate-pulse">{t('loading')}</div>
          ) : variantsError ? (
            <ErrorState
              message={t('variant_load_error')}
              onRetry={() => variantsProduct && loadVariants(variantsProduct.id)}
            />
          ) : variants.length === 0 ? (
            <div className="py-6 text-center text-muted-foreground">{t('no_variants')}</div>
          ) : (
            <div className="rounded-lg border border-border">
              <DataTable
                columns={variantColumns}
                rows={variants}
                rowKey={(v) => v.id}
              />
            </div>
          )}

          {/* Add / edit a variant */}
          <div className="mt-2 space-y-3 rounded-lg border border-border p-3">
            <p className="text-sm font-medium text-foreground/90">
              {editingVariantId ? t('edit_variant') : t('add_variant')}
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="mb-1 block text-xs">{t('variant_name')} *</Label>
                <Input
                  value={variantForm.name}
                  onChange={(e) => setVariantForm((p) => ({ ...p, name: e.target.value }))}
                  placeholder="Red / Large"
                />
              </div>
              <div>
                <Label className="mb-1 block text-xs">{t('variant_attributes')}</Label>
                <Input
                  value={variantForm.attributes}
                  onChange={(e) => setVariantForm((p) => ({ ...p, attributes: e.target.value }))}
                  placeholder='{"size":"L","color":"Red"}'
                />
              </div>
              <div>
                <Label className="mb-1 block text-xs">{t('barcode')}</Label>
                <Input
                  value={variantForm.barcode}
                  onChange={(e) => setVariantForm((p) => ({ ...p, barcode: e.target.value }))}
                  placeholder="e.g. TSHIRT-RED-L"
                />
              </div>
              <div>
                <Label className="mb-1 block text-xs">SKU</Label>
                <Input
                  value={variantForm.sku}
                  onChange={(e) => setVariantForm((p) => ({ ...p, sku: e.target.value }))}
                  placeholder="SKU"
                />
              </div>
              <div>
                <Label className="mb-1 block text-xs">{t('price')}</Label>
                <Input
                  type="number"
                  value={variantForm.price}
                  onChange={(e) => setVariantForm((p) => ({ ...p, price: e.target.value }))}
                  placeholder="0.00"
                />
              </div>
              <div>
                <Label className="mb-1 block text-xs">{t('stock')}</Label>
                <Input
                  type="number"
                  value={variantForm.quantity}
                  onChange={(e) => setVariantForm((p) => ({ ...p, quantity: e.target.value }))}
                  placeholder="0"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                onClick={handleSaveVariant}
                disabled={variantSubmitting || !variantForm.name}
              >
                {variantSubmitting ? t('loading') : editingVariantId ? t('save') : t('add_variant')}
              </Button>
              {editingVariantId && (
                <Button
                  variant="outline"
                  onClick={resetVariantForm}
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