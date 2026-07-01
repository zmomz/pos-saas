import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
import LoadingState from '@/components/states/LoadingState';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import ErrorState from '@/components/states/ErrorState';
import { FolderTree, Folder, FolderOpen, Plus } from 'lucide-react';

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
  const [loadError, setLoadError] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<Category | null>(null);
  const [formData, setFormData] = useState<CategoryFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const { t, tt } = useLanguage();

  useEffect(() => {
    loadCategories();
  }, []);

  async function loadCategories() {
    setLoading(true);
    setLoadError(false);
    try {
      const data = await getCategories();
      setCategories(Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load categories:', err);
      setCategories([]);
      setLoadError(true);
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
          <Label className="mb-1 block">{tt('name', 'Name')} *</Label>
          <Input
            value={formData.name}
            onChange={(e) => handleFormChange('name', e.target.value)}
            placeholder={tt('category_name_placeholder', 'Category name')}
          />
        </div>
        <div>
          <Label className="mb-1 block">{tt('parent_category', 'Parent Category')}</Label>
          <Select value={formData.parent_id} onValueChange={(v) => handleFormChange('parent_id', v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">
                {tt('none_top_level', 'None (Top Level)')}
              </SelectItem>
              {parentCategories
                .filter((c) => c.id !== selectedCategory?.id)
                .map((cat) => (
                  <SelectItem key={cat.id} value={cat.id}>
                    {cat.name}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="mb-1 block">{tt('icon_emoji_or_text', 'Icon (emoji or text)')}</Label>
          <Input
            value={formData.icon}
            onChange={(e) => handleFormChange('icon', e.target.value)}
            placeholder={tt('icon_placeholder', '📦 or icon name')}
          />
        </div>
        <div>
          <Label className="mb-1 block">{tt('sort_order', 'Sort Order')}</Label>
          <Input
            type="number"
            value={formData.sort_order}
            onChange={(e) => handleFormChange('sort_order', e.target.value)}
            placeholder="0"
          />
        </div>
        <div className="flex gap-3 pt-2">
          <Button
            onClick={onSubmit}
            disabled={submitting || !formData.name}
            className="flex-1"
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
            <div key={parent.id} className="dxr-tile p-0">
              <div className="flex items-center justify-between p-3">
                <div className="flex items-center gap-2">
                  {children.length > 0 ? (
                    <FolderOpen className="h-4 w-4 text-brand-700" />
                  ) : (
                    <Folder className="h-4 w-4 text-muted-foreground" />
                  )}
                  <span className="text-foreground font-medium">
                    {parent.icon && <span className="me-1">{parent.icon}</span>}
                    {parent.name}
                  </span>
                  {children.length > 0 && (
                    <span className="text-xs text-muted-foreground">({children.length})</span>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openEdit(parent)}
                    className="text-xs"
                  >
                    {tt('edit', 'Edit')}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openDelete(parent)}
                    className="border-danger/40 text-danger hover:bg-danger/10 text-xs"
                  >
                    {tt('delete', 'Delete')}
                  </Button>
                </div>
              </div>
              {children.length > 0 && (
                <div className="ps-8 pb-2 space-y-1">
                  {children.map((child) => (
                    <div
                      key={child.id}
                      className="flex items-center justify-between p-2 rounded bg-muted/30"
                    >
                      <div className="flex items-center gap-2">
                        <Folder className="h-3.5 w-3.5 text-muted-foreground" />
                        <span className="text-foreground/90 text-sm">
                          {child.icon && <span className="me-1">{child.icon}</span>}
                          {child.name}
                        </span>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => openEdit(child)}
                          className="text-xs h-7"
                        >
                          {tt('edit', 'Edit')}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => openDelete(child)}
                          className="border-danger/40 text-danger hover:bg-danger/10 text-xs h-7"
                        >
                          {tt('delete', 'Delete')}
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

  if (loading) return <LoadingState message={t('loading')} />;

  return (
    <div className="animate-fade-up space-y-6">
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><FolderTree className="h-[18px] w-[18px]" /></span>}
        title={tt('categories', 'Categories')}
        subtitle={t('categories_subtitle')
          .replace('{top}', String(parentCategories.length))
          .replace('{total}', String(categories.length))}
      >
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button
              onClick={() => setFormData(emptyForm)}
              className="h-11 rounded-[10px] shadow-brand"
            >
              <Plus className="h-4 w-4" />
              {tt('add_category', 'Add Category')}
            </Button>
          </DialogTrigger>
          <DialogContent className="max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{tt('add_new_category', 'Add New Category')}</DialogTitle>
            </DialogHeader>
            {renderForm(handleAddCategory, tt('add_category', 'Add Category'))}
          </DialogContent>
        </Dialog>
      </PageHeading>

      {/* Category Tree — a failed load shows an error+retry, never "none yet" */}
      {loadError ? (
        <ErrorState message={t('categories_load_error')} onRetry={loadCategories} />
      ) : categories.length === 0 ? (
        <div className="dxr-tile flex flex-col items-center justify-center py-16 text-center text-muted-foreground">
          <FolderTree className="mb-3 h-12 w-12 opacity-25" />
          <p>{tt('no_categories_yet', 'No categories yet. Add your first category above.')}</p>
        </div>
      ) : (
        renderCategoryTree()
      )}

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{tt('edit_category', 'Edit Category')}</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditCategory, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{tt('confirm_delete', 'Confirm Delete')}</DialogTitle>
          </DialogHeader>
          <p className="text-foreground/90">
            {tt('delete_confirm_prefix', 'Are you sure you want to delete')} <strong>{selectedCategory?.name}</strong>?
            {getChildren(selectedCategory?.id || '').length > 0 &&
              ` ${tt('delete_affects_children', 'This will also affect its child categories.')}`}
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
              onClick={handleDeleteCategory}
              disabled={submitting}
              className="flex-1"
            >
              {submitting ? t('loading') : tt('delete', 'Delete')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}