import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
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
import { getCategories, createCategory, updateCategory, deleteCategory } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { FolderTree, Folder, FolderOpen } from 'lucide-react';

interface Category {
  id: string;
  name: string;
  parent_id?: string;
  icon?: string;
  sort_order?: number;
  created_at?: string;
}

interface CategoryFormData {
  name: string;
  parent_id: string;
  icon: string;
  sort_order: string;
}

const emptyForm: CategoryFormData = {
  name: '',
  parent_id: 'none',
  icon: '',
  sort_order: '0',
};

export default function CategoryManagement() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<Category | null>(null);
  const [formData, setFormData] = useState<CategoryFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const { t } = useLanguage();

  useEffect(() => {
    loadCategories();
  }, []);

  async function loadCategories() {
    setLoading(true);
    try {
      const data = await getCategories();
      setCategories(Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load categories:', err);
      setCategories([]);
    } finally {
      setLoading(false);
    }
  }

  const parentCategories = categories.filter((c) => !c.parent_id);
  const getChildren = (parentId: string) => categories.filter((c) => c.parent_id === parentId);

  function handleFormChange(field: keyof CategoryFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  async function handleAddCategory() {
    setSubmitting(true);
    try {
      await createCategory({
        name: formData.name,
        parent_id: formData.parent_id !== 'none' ? formData.parent_id : undefined,
        icon: formData.icon || undefined,
        sort_order: parseInt(formData.sort_order, 10) || 0,
      });
      setAddOpen(false);
      setFormData(emptyForm);
      await loadCategories();
    } catch (err) {
      console.error('Failed to create category:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function openEdit(category: Category) {
    setSelectedCategory(category);
    setFormData({
      name: category.name,
      parent_id: category.parent_id || 'none',
      icon: category.icon || '',
      sort_order: String(category.sort_order || 0),
    });
    setEditOpen(true);
  }

  async function handleEditCategory() {
    if (!selectedCategory) return;
    setSubmitting(true);
    try {
      await updateCategory(selectedCategory.id, {
        name: formData.name,
        parent_id: formData.parent_id !== 'none' ? formData.parent_id : null,
        icon: formData.icon || undefined,
        sort_order: parseInt(formData.sort_order, 10) || 0,
      });
      setEditOpen(false);
      setSelectedCategory(null);
      setFormData(emptyForm);
      await loadCategories();
    } catch (err) {
      console.error('Failed to update category:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function openDelete(category: Category) {
    setSelectedCategory(category);
    setDeleteOpen(true);
  }

  async function handleDeleteCategory() {
    if (!selectedCategory) return;
    setSubmitting(true);
    try {
      await deleteCategory(selectedCategory.id);
      setDeleteOpen(false);
      setSelectedCategory(null);
      await loadCategories();
    } catch (err) {
      console.error('Failed to delete category:', err);
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
            placeholder="Category name"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Parent Category</label>
          <Select value={formData.parent_id} onValueChange={(v) => handleFormChange('parent_id', v)}>
            <SelectTrigger className="bg-slate-700 border-slate-600 text-white">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-800 border-slate-600">
              <SelectItem value="none" className="text-white hover:bg-slate-700">
                None (Top Level)
              </SelectItem>
              {parentCategories
                .filter((c) => c.id !== selectedCategory?.id)
                .map((cat) => (
                  <SelectItem key={cat.id} value={cat.id} className="text-white hover:bg-slate-700">
                    {cat.name}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Icon (emoji or text)</label>
          <Input
            value={formData.icon}
            onChange={(e) => handleFormChange('icon', e.target.value)}
            placeholder="📦 or icon name"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Sort Order</label>
          <Input
            type="number"
            value={formData.sort_order}
            onChange={(e) => handleFormChange('sort_order', e.target.value)}
            placeholder="0"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div className="flex gap-3 pt-2">
          <Button
            onClick={onSubmit}
            disabled={submitting || !formData.name}
            className="flex-1 bg-brand-600 hover:bg-brand-700 text-white"
          >
            {submitting ? t('loading') : submitLabel}
          </Button>
        </div>
      </div>
    );
  }

  function renderCategoryTree() {
    const sorted = [...parentCategories].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));

    return (
      <div className="space-y-2">
        {sorted.map((parent) => {
          const children = getChildren(parent.id).sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
          return (
            <div key={parent.id} className="bg-slate-800/50 rounded-lg border border-slate-700">
              <div className="flex items-center justify-between p-3">
                <div className="flex items-center gap-2">
                  {children.length > 0 ? (
                    <FolderOpen className="h-4 w-4 text-brand-400" />
                  ) : (
                    <Folder className="h-4 w-4 text-slate-400" />
                  )}
                  <span className="text-white font-medium">
                    {parent.icon && <span className="mr-1">{parent.icon}</span>}
                    {parent.name}
                  </span>
                  {children.length > 0 && (
                    <span className="text-xs text-slate-500">({children.length})</span>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openEdit(parent)}
                    className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs"
                  >
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openDelete(parent)}
                    className="border-red-600/50 text-red-400 hover:bg-red-600/20 text-xs"
                  >
                    Delete
                  </Button>
                </div>
              </div>
              {children.length > 0 && (
                <div className="pl-8 pb-2 space-y-1">
                  {children.map((child) => (
                    <div
                      key={child.id}
                      className="flex items-center justify-between p-2 rounded bg-slate-700/30"
                    >
                      <div className="flex items-center gap-2">
                        <Folder className="h-3.5 w-3.5 text-slate-500" />
                        <span className="text-slate-300 text-sm">
                          {child.icon && <span className="mr-1">{child.icon}</span>}
                          {child.name}
                        </span>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => openEdit(child)}
                          className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs h-7"
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => openDelete(child)}
                          className="border-red-600/50 text-red-400 hover:bg-red-600/20 text-xs h-7"
                        >
                          Delete
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <FolderTree className="h-8 w-8 text-brand-400" />
            <div>
              <h2 className="text-lg font-bold text-white">Categories</h2>
              <p className="text-slate-400 text-sm">
                {parentCategories.length} top-level, {categories.length} total
              </p>
            </div>
          </div>
          <Dialog open={addOpen} onOpenChange={setAddOpen}>
            <DialogTrigger asChild>
              <Button
                onClick={() => setFormData(emptyForm)}
                className="bg-brand-600 hover:bg-brand-700 text-white"
              >
                + Add Category
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle className="text-white">Add New Category</DialogTitle>
              </DialogHeader>
              {renderForm(handleAddCategory, 'Add Category')}
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>

      {/* Category Tree */}
      {categories.length === 0 ? (
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-8 text-center">
            <FolderTree className="h-12 w-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-500">No categories yet. Add your first category above.</p>
          </CardContent>
        </Card>
      ) : (
        renderCategoryTree()
      )}

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-white">Edit Category</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditCategory, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Confirm Delete</DialogTitle>
          </DialogHeader>
          <p className="text-slate-300">
            Are you sure you want to delete <strong>{selectedCategory?.name}</strong>?
            {getChildren(selectedCategory?.id || '').length > 0 &&
              ' This will also affect its child categories.'}
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
              onClick={handleDeleteCategory}
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