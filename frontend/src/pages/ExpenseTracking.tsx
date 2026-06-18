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
import { getExpenses, createExpense, updateExpense, deleteExpense, getTransactions } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatMoney, formatDate } from '@/lib/format';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import StatTile from '@/components/dashboard/StatTile';
import { DollarSign, TrendingDown, TrendingUp, Receipt, Plus } from 'lucide-react';

interface Expense {
  id: string;
  category: string;
  amount: number;
  description?: string;
  expense_date?: string;
  created_at?: string;
}

interface ExpenseFormData {
  category: string;
  amount: string;
  description: string;
  expense_date: string;
}

const EXPENSE_CATEGORIES = ['Rent', 'Utilities', 'Supplies', 'Salary', 'Marketing', 'Maintenance', 'Other'];

const emptyForm: ExpenseFormData = {
  category: 'Supplies',
  amount: '',
  description: '',
  expense_date: new Date().toISOString().split('T')[0],
};

export default function ExpenseTracking() {
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [totalRevenue, setTotalRevenue] = useState(0);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedExpense, setSelectedExpense] = useState<Expense | null>(null);
  const [formData, setFormData] = useState<ExpenseFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const { t, language } = useLanguage();
  const tt = (key: string, fallback: string) => {
    const v = t(key);
    return v === key ? fallback : v;
  };

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [expData, txData] = await Promise.all([getExpenses(), getTransactions(1, 1000)]);
      const expItems = Array.isArray(expData?.items) ? expData.items : [];
      setExpenses(expItems as unknown as Expense[]);

      const transactions = Array.isArray(txData?.items) ? txData.items : Array.isArray(txData) ? txData : [];
      const revenue = transactions.reduce((sum: number, tx: { total_amount?: number }) => sum + (tx.total_amount || 0), 0);
      setTotalRevenue(revenue);
    } catch (err) {
      console.error('Failed to load data:', err);
      setExpenses([]);
    } finally {
      setLoading(false);
    }
  }

  const now = new Date();
  const monthExpenses = expenses.filter((e) => {
    const d = new Date(e.expense_date || e.created_at || '');
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
  });
  const totalExpenses = monthExpenses.reduce((sum, e) => sum + (e.amount || 0), 0);
  const netProfit = totalRevenue - totalExpenses;

  function handleFormChange(field: keyof ExpenseFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  async function handleAddExpense() {
    setSubmitting(true);
    try {
      await createExpense({
        category: formData.category,
        amount: parseFloat(formData.amount),
        description: formData.description || undefined,
        expense_date: formData.expense_date || undefined,
      });
      setAddOpen(false);
      setFormData(emptyForm);
      await loadData();
    } catch (err) {
      console.error('Failed to create expense:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function openEdit(expense: Expense) {
    setSelectedExpense(expense);
    setFormData({
      category: expense.category || 'Other',
      amount: String(expense.amount),
      description: expense.description || '',
      expense_date: expense.expense_date || '',
    });
    setEditOpen(true);
  }

  async function handleEditExpense() {
    if (!selectedExpense) return;
    setSubmitting(true);
    try {
      await updateExpense(selectedExpense.id, {
        category: formData.category,
        amount: parseFloat(formData.amount),
        description: formData.description || undefined,
        expense_date: formData.expense_date || undefined,
      });
      setEditOpen(false);
      setSelectedExpense(null);
      setFormData(emptyForm);
      await loadData();
    } catch (err) {
      console.error('Failed to update expense:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function openDelete(expense: Expense) {
    setSelectedExpense(expense);
    setDeleteOpen(true);
  }

  async function handleDeleteExpense() {
    if (!selectedExpense) return;
    setSubmitting(true);
    try {
      await deleteExpense(selectedExpense.id);
      setDeleteOpen(false);
      setSelectedExpense(null);
      await loadData();
    } catch (err) {
      console.error('Failed to delete expense:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function renderForm(onSubmit: () => void, submitLabel: string) {
    return (
      <div className="space-y-4">
        <div>
          <label className="text-sm text-muted-foreground mb-1 block">{tt('expense_category', 'Category')} *</label>
          <Select value={formData.category} onValueChange={(v) => handleFormChange('category', v)}>
            <SelectTrigger className="bg-muted border-input text-foreground">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-card border-input">
              {EXPENSE_CATEGORIES.map((cat) => (
                <SelectItem key={cat} value={cat} className="text-foreground hover:bg-muted">
                  {cat}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-sm text-muted-foreground mb-1 block">{tt('expense_amount_sar', 'Amount (⃁)')} *</label>
          <Input
            type="number"
            value={formData.amount}
            onChange={(e) => handleFormChange('amount', e.target.value)}
            placeholder="0.00"
            className="bg-muted border-input text-foreground"
          />
        </div>
        <div>
          <label className="text-sm text-muted-foreground mb-1 block">{tt('description', 'Description')}</label>
          <Input
            value={formData.description}
            onChange={(e) => handleFormChange('description', e.target.value)}
            placeholder={tt('expense_description_placeholder', 'Expense description')}
            className="bg-muted border-input text-foreground"
          />
        </div>
        <div>
          <label className="text-sm text-muted-foreground mb-1 block">{tt('date', 'Date')}</label>
          <Input
            type="date"
            value={formData.expense_date}
            onChange={(e) => handleFormChange('expense_date', e.target.value)}
            className="bg-muted border-input text-foreground"
          />
        </div>
        <div className="flex gap-3 pt-2">
          <Button
            onClick={onSubmit}
            disabled={submitting || !formData.amount || !formData.category}
            className="flex-1 shadow-brand"
          >
            {submitting ? t('loading') : submitLabel}
          </Button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-foreground animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-6">
      {/* Header */}
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><Receipt className="h-[18px] w-[18px]" /></span>}
        title={tt('expense_tracking', 'Expense Tracking')}
        subtitle={tt('expense_tracking_desc', 'Track and manage your business expenses')}
      >
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button
              onClick={() => setFormData(emptyForm)}
              className="h-11 rounded-[10px] shadow-brand"
            >
              <Plus className="h-4 w-4 me-2" /> {tt('add_expense', 'Add Expense')}
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-card border-border text-foreground max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="text-foreground">{tt('add_new_expense', 'Add New Expense')}</DialogTitle>
            </DialogHeader>
            {renderForm(handleAddExpense, tt('add_expense', 'Add Expense'))}
          </DialogContent>
        </Dialog>
      </PageHeading>

      {/* Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          icon={TrendingDown}
          tone="warning"
          label={tt('expenses_this_month', 'Expenses (This Month)')}
          value={<span className="tabular-nums">{formatMoney(totalExpenses, language)}</span>}
        />
        <StatTile
          icon={TrendingUp}
          tone="success"
          label={tt('revenue_total', 'Revenue (Total)')}
          value={<span className="tabular-nums">{formatMoney(totalRevenue, language)}</span>}
        />
        <StatTile
          icon={DollarSign}
          tone={netProfit >= 0 ? 'success' : 'warning'}
          label={tt('net_profit_loss', 'Net Profit/Loss')}
          value={
            <span className={`tabular-nums ${netProfit >= 0 ? 'text-success' : 'text-danger'}`}>
              {formatMoney(netProfit, language)}
            </span>
          }
        />
      </div>

      {/* Category Breakdown */}
      <Card className="bg-card border-border">
        <CardContent className="p-4">
          <h3 className="text-foreground font-semibold mb-3 flex items-center gap-2">
            <Receipt className="h-5 w-5 text-brand" />
            {tt('category_breakdown', 'Category Breakdown')}
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {EXPENSE_CATEGORIES.map((cat) => {
              const catTotal = monthExpenses
                .filter((e) => e.category === cat)
                .reduce((sum, e) => sum + (e.amount || 0), 0);
              if (catTotal === 0) return null;
              return (
                <div key={cat} className="bg-muted/50 rounded-lg p-3">
                  <p className="text-xs text-muted-foreground">{cat}</p>
                  <p className="text-sm font-semibold text-foreground tabular-nums">{formatMoney(catTotal, language)}</p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-card">
            <tr className="text-muted-foreground">
              <th className="p-3 text-start">{tt('date', 'Date')}</th>
              <th className="p-3 text-start">{tt('expense_category', 'Category')}</th>
              <th className="p-3 text-start">{tt('description', 'Description')}</th>
              <th className="p-3 text-start">{tt('amount', 'Amount')}</th>
              <th className="p-3 text-start">{tt('actions', 'Actions')}</th>
            </tr>
          </thead>
          <tbody>
            {expenses.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-6 text-center text-muted-foreground">
                  {tt('no_expenses_recorded', 'No expenses recorded')}
                </td>
              </tr>
            ) : (
              expenses.map((expense) => (
                <tr key={expense.id} className="border-t border-border text-foreground/90">
                  <td className="p-3 tabular-nums">
                    {expense.expense_date || (expense.created_at ? formatDate(expense.created_at, language) : '—')}
                  </td>
                  <td className="p-3">
                    <span className="px-2 py-0.5 rounded bg-muted text-foreground/90 text-xs">
                      {expense.category}
                    </span>
                  </td>
                  <td className="p-3 max-w-[200px] truncate">{expense.description || '—'}</td>
                  <td className="p-3 text-danger font-medium tabular-nums">{formatMoney(expense.amount || 0, language)}</td>
                  <td className="p-3">
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openEdit(expense)}
                        className="border-input text-foreground/90 hover:bg-muted text-xs"
                      >
                        {tt('edit', 'Edit')}
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => openDelete(expense)}
                        className="text-xs"
                      >
                        {tt('delete', 'Delete')}
                      </Button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="bg-card border-border text-foreground max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-foreground">{tt('edit_expense', 'Edit Expense')}</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditExpense, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="bg-card border-border text-foreground">
          <DialogHeader>
            <DialogTitle className="text-foreground">{tt('confirm_delete', 'Confirm Delete')}</DialogTitle>
          </DialogHeader>
          <p className="text-foreground/90">
            {tt('expense_delete_confirm', 'Are you sure you want to delete this expense? This action cannot be undone.')}
          </p>
          <div className="flex gap-3 pt-4">
            <Button
              variant="outline"
              onClick={() => setDeleteOpen(false)}
              className="flex-1 border-input text-foreground/90 hover:bg-muted"
            >
              {t('cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteExpense}
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