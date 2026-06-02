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
} from '@/lib/api';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';

interface Product {
  id: number;
  name: string;
  name_ar?: string;
  barcode?: string;
  price: number;
  cost_price?: number;
  quantity: number;
  category?: string;
  vat_rate: number;
  is_active?: boolean;
}

interface ProductFormData {
  name: string;
  name_ar: string;
  barcode: string;
  price: string;
  cost_price: string;
  quantity: string;
  category: string;
  vat_rate: string;
}

const CATEGORIES = ['Food', 'Beverages', 'Electronics', 'Clothing', 'Other'];

const emptyForm: ProductFormData = {
  name: '',
  name_ar: '',
  barcode: '',
  price: '',
  cost_price: '',
  quantity: '',
  category: 'Food',
  vat_rate: '15',
};

export default function ProductManagement() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [formData, setFormData] = useState<ProductFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const navigate = useNavigate();
  const { t, language, setLanguage } = useLanguage();

  useEffect(() => {
    loadProducts();
  }, []);

  async function loadProducts() {
    setLoading(true);
    try {
      const category = categoryFilter !== 'all' ? categoryFilter : undefined;
      const searchTerm = search.trim() || undefined;
      const data = await getProductsList(category, searchTerm);
      setProducts(Array.isArray(data) ? data : data?.products || []);
    } catch (err) {
      console.error('Failed to load products:', err);
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timeout = setTimeout(() => {
      loadProducts();
    }, 300);
    return () => clearTimeout(timeout);
  }, [search, categoryFilter]);

  const totalProducts = products.length;
  const lowStockCount = products.filter((p) => p.quantity < 10).length;
  const activeProducts = products.filter((p) => p.is_active !== false).length;

  function handleFormChange(field: keyof ProductFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
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
        quantity: parseInt(formData.quantity, 10),
        category: formData.category || undefined,
        vat_rate: parseFloat(formData.vat_rate),
      });
      setAddOpen(false);
      setFormData(emptyForm);
      await loadProducts();
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
      category: product.category || 'Other',
      vat_rate: String(product.vat_rate),
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
        quantity: parseInt(formData.quantity, 10),
        category: formData.category || undefined,
        vat_rate: parseFloat(formData.vat_rate),
      });
      setEditOpen(false);
      setSelectedProduct(null);
      setFormData(emptyForm);
      await loadProducts();
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
    } catch (err) {
      console.error('Failed to delete product:', err);
    } finally {
      setSubmitting(false);
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
            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
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
                className="bg-blue-600 hover:bg-blue-700 text-white"
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
                products.map((product) => (
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
                      {product.quantity < 10 ? (
                        <Badge className="bg-red-600/20 text-red-400 border border-red-600/40">
                          {product.quantity}
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
    </div>
  );
}