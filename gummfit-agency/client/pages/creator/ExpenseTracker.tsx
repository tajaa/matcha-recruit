import { useEffect, useState } from 'react';
import {
  Receipt,
  Plus,
  Filter,
  ChevronDown,
  Calendar,
  Building,
  Trash2,
  CheckCircle2
} from 'lucide-react';
import { api } from '../../api/client';
import type { Expense, ExpenseCreate, ExpenseCategory } from '../../types/creator';

export function ExpenseTracker() {
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNewExpense, setShowNewExpense] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [formData, setFormData] = useState<ExpenseCreate>({
    amount: 0,
    date: new Date().toISOString().split('T')[0],
    category: 'equipment',
    description: '',
    is_deductible: true,
  });

  useEffect(() => {
    loadExpenses();
  }, []);

  const loadExpenses = async () => {
    try {
      const res = await api.creators.listExpenses({ limit: 100 });
      setExpenses(res);
    } catch (err) {
      console.error('Failed to load expenses:', err);
    } finally {
      setLoading(false);
    }
  };

  const createExpense = async () => {
    if (!formData.amount || !formData.description) return;
    try {
      await api.creators.createExpense(formData);
      setShowNewExpense(false);
      setFormData({
        amount: 0,
        date: new Date().toISOString().split('T')[0],
        category: 'equipment',
        description: '',
        is_deductible: true,
      });
      loadExpenses();
    } catch (err) {
      console.error('Failed to create expense:', err);
    }
  };

  const deleteExpense = async (id: string) => {
    if (!confirm('Delete this expense?')) return;
    try {
      await api.creators.deleteExpense(id);
      loadExpenses();
    } catch (err) {
      console.error('Failed to delete expense:', err);
    }
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const categories: { value: ExpenseCategory; label: string; color: string }[] = [
    { value: 'equipment', label: 'Equipment', color: 'text-blue-400' },
    { value: 'software', label: 'Software', color: 'text-purple-400' },
    { value: 'travel', label: 'Travel', color: 'text-emerald-400' },
    { value: 'marketing', label: 'Marketing', color: 'text-pink-400' },
    { value: 'contractors', label: 'Contractors', color: 'text-amber-400' },
    { value: 'office', label: 'Office', color: 'text-cyan-400' },
    { value: 'education', label: 'Education', color: 'text-indigo-400' },
    { value: 'legal', label: 'Legal', color: 'text-red-400' },
    { value: 'other', label: 'Other', color: 'text-zinc-400' },
  ];

  const getCategoryColor = (category: string) => {
    return categories.find(c => c.value === category)?.color || 'text-zinc-400';
  };

  const filteredExpenses = selectedCategory === 'all'
    ? expenses
    : expenses.filter(e => e.category === selectedCategory);

  const totalExpenses = filteredExpenses.reduce((sum, e) => sum + e.amount, 0);
  const deductibleExpenses = filteredExpenses.filter(e => e.is_deductible).reduce((sum, e) => sum + e.amount, 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="px-2 py-1 border border-amber-500/20 bg-amber-900/10 text-amber-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Expense Tracking
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Expenses
          </h1>
        </div>
        <button
          onClick={() => setShowNewExpense(true)}
          className="px-6 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest transition-all font-bold flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          Log Expense
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-white/10 border border-white/10">
        <div className="bg-zinc-950 p-8">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded bg-amber-500/10 text-amber-500">
              <Receipt className="w-4 h-4" />
            </div>
            <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">
              Total Expenses
            </span>
          </div>
          <div className="text-3xl font-light text-white">
            {formatCurrency(totalExpenses)}
          </div>
        </div>

        <div className="bg-zinc-950 p-8">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded bg-emerald-500/10 text-emerald-500">
              <CheckCircle2 className="w-4 h-4" />
            </div>
            <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">
              Deductible
            </span>
          </div>
          <div className="text-3xl font-light text-emerald-400">
            {formatCurrency(deductibleExpenses)}
          </div>
        </div>

        <div className="bg-zinc-950 p-8">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded bg-blue-500/10 text-blue-500">
              <Filter className="w-4 h-4" />
            </div>
            <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">
              Entries
            </span>
          </div>
          <div className="text-3xl font-light text-white">
            {filteredExpenses.length}
          </div>
        </div>
      </div>

      {/* Category Filter */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setSelectedCategory('all')}
          className={`px-4 py-2 text-xs font-mono uppercase tracking-widest transition-all border ${
            selectedCategory === 'all'
              ? 'bg-white text-black border-white'
              : 'border-white/20 text-zinc-400 hover:border-white/40'
          }`}
        >
          All
        </button>
        {categories.map((cat) => (
          <button
            key={cat.value}
            onClick={() => setSelectedCategory(cat.value)}
            className={`px-4 py-2 text-xs font-mono uppercase tracking-widest transition-all border ${
              selectedCategory === cat.value
                ? 'bg-white text-black border-white'
                : 'border-white/20 text-zinc-400 hover:border-white/40'
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Expenses List */}
      <div className="border border-white/10 bg-zinc-900/30">
        <div className="p-4 border-b border-white/10 flex justify-between items-center">
          <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">
            Expense Entries
          </h2>
          <span className="text-[10px] text-zinc-500">{filteredExpenses.length} entries</span>
        </div>
        <div className="divide-y divide-white/5">
          {filteredExpenses.length === 0 ? (
            <div className="p-12 text-center text-zinc-500">
              <Receipt className="w-8 h-8 mx-auto mb-3 opacity-50" />
              <p className="text-sm mb-4">No expenses recorded</p>
              <button
                onClick={() => setShowNewExpense(true)}
                className="text-xs text-amber-400 hover:text-amber-300"
              >
                Log your first expense →
              </button>
            </div>
          ) : (
            filteredExpenses.map((expense) => (
              <div
                key={expense.id}
                className="p-4 flex items-center justify-between hover:bg-white/5 transition-colors group"
              >
                <div className="flex items-center gap-4">
                  <div className={`p-2 rounded bg-white/5 ${getCategoryColor(expense.category)}`}>
                    <Receipt className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-zinc-300">{expense.description}</span>
                      {expense.is_deductible && (
                        <span className="text-[9px] px-1.5 py-0.5 bg-emerald-500/10 text-emerald-400 rounded">
                          Deductible
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <Calendar className="w-3 h-3 text-zinc-600" />
                      <span className="text-[10px] text-zinc-500">{formatDate(expense.date)}</span>
                      <span className="text-zinc-700">•</span>
                      <span className={`text-[10px] capitalize ${getCategoryColor(expense.category)}`}>
                        {expense.category}
                      </span>
                      {expense.vendor && (
                        <>
                          <span className="text-zinc-700">•</span>
                          <Building className="w-3 h-3 text-zinc-600" />
                          <span className="text-[10px] text-zinc-500">{expense.vendor}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-lg font-light text-amber-400">
                    -{formatCurrency(expense.amount)}
                  </div>
                  <button
                    onClick={() => deleteExpense(expense.id)}
                    className="p-2 opacity-0 group-hover:opacity-100 hover:bg-red-500/10 text-red-400 transition-all"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* New Expense Modal */}
      {showNewExpense && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-900 border border-white/10 max-w-md w-full">
            <div className="p-6 border-b border-white/10">
              <h2 className="text-lg font-bold text-white">Log Expense</h2>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Amount
                </label>
                <input
                  type="number"
                  value={formData.amount || ''}
                  onChange={(e) => setFormData({ ...formData, amount: parseFloat(e.target.value) || 0 })}
                  placeholder="0.00"
                  className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Description
                </label>
                <input
                  type="text"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="e.g., Camera equipment"
                  className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                    Date
                  </label>
                  <input
                    type="date"
                    value={formData.date}
                    onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                    className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white focus:outline-none focus:border-white/30"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                    Category
                  </label>
                  <div className="relative">
                    <select
                      value={formData.category}
                      onChange={(e) => setFormData({ ...formData, category: e.target.value as ExpenseCategory })}
                      className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white appearance-none focus:outline-none focus:border-white/30"
                    >
                      {categories.map((cat) => (
                        <option key={cat.value} value={cat.value}>{cat.label}</option>
                      ))}
                    </select>
                    <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
                  </div>
                </div>
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Vendor (optional)
                </label>
                <input
                  type="text"
                  value={formData.vendor || ''}
                  onChange={(e) => setFormData({ ...formData, vendor: e.target.value })}
                  placeholder="e.g., Amazon"
                  className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
                />
              </div>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.is_deductible}
                  onChange={(e) => setFormData({ ...formData, is_deductible: e.target.checked })}
                  className="w-4 h-4 bg-zinc-800 border border-white/20 rounded"
                />
                <span className="text-sm text-zinc-300">Tax Deductible</span>
              </label>
            </div>
            <div className="p-6 border-t border-white/10 flex justify-end gap-4">
              <button
                onClick={() => setShowNewExpense(false)}
                className="px-6 py-2 border border-white/20 text-xs font-mono uppercase tracking-widest hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={createExpense}
                className="px-6 py-2 bg-white text-black text-xs font-mono uppercase tracking-widest hover:bg-zinc-200 font-bold"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ExpenseTracker;
