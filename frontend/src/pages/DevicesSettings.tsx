import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { listTerminals, registerTerminal, type Terminal } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { CreditCard } from 'lucide-react';

interface TerminalFormData {
  label: string;
  serial: string;
  provider: string;
  branch_id: string;
}

const emptyForm: TerminalFormData = {
  label: '',
  serial: '',
  provider: 'geidea',
  branch_id: '',
};

export default function DevicesSettings() {
  const [terminals, setTerminals] = useState<Terminal[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [formData, setFormData] = useState<TerminalFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const { t } = useLanguage();

  useEffect(() => {
    loadTerminals();
  }, []);

  async function loadTerminals() {
    setLoading(true);
    try {
      const data = await listTerminals();
      setTerminals(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load terminals:', err);
      setTerminals([]);
    } finally {
      setLoading(false);
    }
  }

  function handleFormChange(field: keyof TerminalFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  async function handleAddTerminal() {
    setSubmitting(true);
    try {
      await registerTerminal({
        provider: formData.provider || undefined,
        label: formData.label || undefined,
        serial: formData.serial || undefined,
        branch_id: formData.branch_id ? parseInt(formData.branch_id, 10) : undefined,
      });
      setAddOpen(false);
      setFormData(emptyForm);
      await loadTerminals();
    } catch (err) {
      console.error('Failed to register terminal:', err);
    } finally {
      setSubmitting(false);
    }
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
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <CreditCard className="h-8 w-8 text-brand-400" />
            <div>
              <h2 className="text-lg font-bold text-white">{t('device_settings')}</h2>
              <p className="text-slate-400 text-sm">{terminals.length}</p>
            </div>
          </div>
          <Dialog open={addOpen} onOpenChange={setAddOpen}>
            <DialogTrigger asChild>
              <Button
                onClick={() => setFormData(emptyForm)}
                className="bg-brand-600 hover:bg-brand-700 text-white"
              >
                + {t('add_terminal')}
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle className="text-white">{t('add_terminal')}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-slate-400 mb-1 block">{t('terminal_name')} *</label>
                  <Input
                    value={formData.label}
                    onChange={(e) => handleFormChange('label', e.target.value)}
                    placeholder={t('terminal_name')}
                    className="bg-slate-700 border-slate-600 text-white"
                  />
                </div>
                <div>
                  <label className="text-sm text-slate-400 mb-1 block">{t('terminal_provider')}</label>
                  <select
                    aria-label={t('terminal_provider')}
                    value={formData.provider}
                    onChange={(e) => handleFormChange('provider', e.target.value)}
                    className="w-full rounded-md bg-slate-700 border border-slate-600 text-white p-2 text-sm"
                  >
                    <option value="geidea">Geidea</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm text-slate-400 mb-1 block">{t('terminal_serial')}</label>
                  <Input
                    value={formData.serial}
                    onChange={(e) => handleFormChange('serial', e.target.value)}
                    placeholder={t('terminal_serial')}
                    className="bg-slate-700 border-slate-600 text-white"
                  />
                </div>
                <div>
                  <label className="text-sm text-slate-400 mb-1 block">
                    {t('terminal_branch_optional')}
                  </label>
                  <Input
                    type="number"
                    value={formData.branch_id}
                    onChange={(e) => handleFormChange('branch_id', e.target.value)}
                    placeholder="—"
                    className="bg-slate-700 border-slate-600 text-white"
                  />
                </div>
                <div className="flex gap-3 pt-2">
                  <Button
                    onClick={handleAddTerminal}
                    disabled={submitting || !formData.label}
                    className="flex-1 bg-brand-600 hover:bg-brand-700 text-white"
                  >
                    {submitting ? t('loading') : t('add_terminal')}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>

      {terminals.length === 0 ? (
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-8 text-center">
            <CreditCard className="h-12 w-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-500">{t('no_terminals')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {terminals.map((term) => (
            <div
              key={term.id}
              className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-slate-700"
            >
              <div className="flex items-center gap-2">
                <CreditCard className="h-4 w-4 text-brand-400" />
                <span className="text-white font-medium">{term.label || `#${term.id}`}</span>
                <span className="text-xs text-slate-500">
                  {term.provider}
                  {term.serial ? ` · ${term.serial}` : ''}
                  {term.branch_id ? ` · #${term.branch_id}` : ''}
                </span>
              </div>
              <span
                className={`text-xs ${
                  term.status === 'active' ? 'text-emerald-400' : 'text-slate-500'
                }`}
              >
                {term.status === 'active' ? t('terminal_active') : term.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
