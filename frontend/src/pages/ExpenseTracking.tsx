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
import { DollarSign, TrendingDown, TrendingUp, Receipt } from 'lucide-react';

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

  const { t } = useLanguage();

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [expData, txData] = await Promise.all([getExpenses(), getTransactions(1, 1000)]);
      const expItems = Array.isArray(expData?.items) ? expData.items : Array.isArray(expData) ? expData : [];
      setExpenses(expItems);

      const transactions = Array.isArray(txData?.transactions) ? txData.transactions : Array.isArray(txData) ? txData : [];
      const revenue = transactions.reduce((sum: number, tx: { total?: number }) => sum + (tx.total || 0), 0);
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
          <label className="text-sm text-slate-400 mb-1 block">Category *</label>
          <Select value={formData.category} onValueChange={(v) => handleFormChange('category', v)}>
            <SelectTrigger className="bg-slate-700 border-slate-600 text-white">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-800 border-slate-600">
              {EXPENSE_CATEGORIES.map((cat) => (
                <SelectItem key={cat} value={cat} className="text-white hover:bg-slate-700">
                  {cat}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Amount (SAR) *</label>
          <Input
            type="number"
            value={formData.amount}
            onChange={(e) => handleFormChange('amount', e.target.value)}
            placeholder="0.00"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Description</label>
          <Input
            value={formData.description}
            onChange={(e) => handleFormChange('description', e.target.value)}
            placeholder="Expense description"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Date</label>
          <Input
            type="date"
            value={formData.expense_date}
            onChange={(e) => handleFormChange('expense_date', e.target.value)}
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div className="flex gap-3 pt-2">
          <Button
            onClick={onSubmit}
            disabled={submitting || !formData.amount || !formData.category}
            className="flex-1 bg-brand-600 hover:bg-brand-700 text-white"
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
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <TrendingDown className="h-8 w-8 text-red-400" />
            <div>
              <p className="text-slate-400 text-sm">Expenses (This Month)</p>
              <p className="text-2xl font-bold text-red-400">SAR {totalExpenses.toFixed(2)}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <TrendingUp className="h-8 w-8 text-green-400" />
            <div>
              <p className="text-slate-400 text-sm">Revenue (Total)</p>
              <p className="text-2xl font-bold text-green-400">SAR {totalRevenue.toFixed(2)}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <DollarSign className={`h-8 w-8 ${netProfit >= 0 ? 'text-green-400' : 'text-red-400'}`} />
            <div>
              <p className="text-slate-400 text-sm">Net Profit/Loss</p>
              <p className={`text-2xl font-bold ${netProfit >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                SAR {netProfit.toFixed(2)}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Category Breakdown */}
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4">
          <h3 className="text-white font-semibold mb-3 flex items-center gap-2">
            <Receipt className="h-5 w-5 text-brand-400" />
            Category Breakdown
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {EXPENSE_CATEGORIES.map((cat) => {
              const catTotal = monthExpenses
                .filter((e) => e.category === cat)
                .reduce((sum, e) => sum + (e.amount || 0), 0);
              if (catTotal === 0) return null;
              return (
                <div key={cat} className="bg-slate-700/50 rounded-lg p-3">
                  <p className="text-xs text-slate-400">{cat}</p>
                  <p className="text-sm font-semibold text-white">SAR {catTotal.toFixed(2)}</p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Add Button */}
      <div className="flex justify-end">
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button
              onClick={() => setFormData(emptyForm)}
              className="bg-brand-600 hover:bg-brand-700 text-white"
            >
              + Add Expense
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="text-white">Add New Expense</DialogTitle>
            </DialogHeader>
            {renderForm(handleAddExpense, 'Add Expense')}
          </DialogContent>
        </Dialog>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full text-sm">
          <thead className="bg-slate-800">
            <tr className="text-slate-400">
              <th className="p-3 text-start">Date</th>
              <th className="p-3 text-start">Category</th>
              <th className="p-3 text-start">Description</th>
              <th className="p-3 text-start">Amount</th>
              <th className="p-3 text-start">Actions</th>
            </tr>
          </thead>
          <tbody>
            {expenses.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-6 text-center text-slate-500">
                  No expenses recorded
                </td>
              </tr>
            ) : (
              expenses.map((expense) => (
                <tr key={expense.id} className="border-t border-slate-700 text-slate-300">
                  <td className="p-3">
                    {expense.expense_date || (expense.created_at ? new Date(expense.created_at).toLocaleDateString() : '—')}
                  </td>
                  <td className="p-3">
                    <span className="px-2 py-0.5 rounded bg-slate-700 text-slate-300 text-xs">
                      {expense.category}
                    </span>
                  </td>
                  <td className="p-3 max-w-[200px] truncate">{expense.description || '—'}</td>
                  <td className="p-3 text-red-400 font-medium">SAR {expense.amount?.toFixed(2)}</td>
                  <td className="p-3">
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openEdit(expense)}
                        className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs"
                      >
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openDelete(expense)}
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

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-white">Edit Expense</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditExpense, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Confirm Delete</DialogTitle>
          </DialogHeader>
          <p className="text-slate-300">
            Are you sure you want to delete this expense? This action cannot be undone.
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
              onClick={handleDeleteExpense}
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