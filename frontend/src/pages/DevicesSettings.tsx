import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
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
import PageHeading from '@/components/dashboard/rx/PageHeading';
import { listTerminals, registerTerminal, type Terminal } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { CreditCard, Plus } from 'lucide-react';

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
        <div className="text-foreground animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-6">
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><CreditCard className="h-[18px] w-[18px]" /></span>}
        title={t('device_settings')}
        subtitle={`${terminals.length} ${t('configured') || 'configured'}`}
      >
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button onClick={() => setFormData(emptyForm)} className="h-11 rounded-[10px] shadow-brand">
              <Plus className="h-4 w-4 me-2" /> {t('add_terminal')}
            </Button>
          </DialogTrigger>
          <DialogContent className="max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{t('add_terminal')}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label className="text-muted-foreground">{t('terminal_name')} *</Label>
                <Input
                  value={formData.label}
                  onChange={(e) => handleFormChange('label', e.target.value)}
                  placeholder={t('terminal_name')}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-muted-foreground">{t('terminal_provider')}</Label>
                <Select
                  value={formData.provider}
                  onValueChange={(v) => handleFormChange('provider', v)}
                >
                  <SelectTrigger aria-label={t('terminal_provider')}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="geidea">Geidea</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-muted-foreground">{t('terminal_serial')}</Label>
                <Input
                  value={formData.serial}
                  onChange={(e) => handleFormChange('serial', e.target.value)}
                  placeholder={t('terminal_serial')}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-muted-foreground">{t('terminal_branch_optional')}</Label>
                <Input
                  type="number"
                  value={formData.branch_id}
                  onChange={(e) => handleFormChange('branch_id', e.target.value)}
                  placeholder="—"
                />
              </div>
              <div className="flex gap-3 pt-2">
                <Button
                  onClick={handleAddTerminal}
                  disabled={submitting || !formData.label}
                  className="flex-1 shadow-brand"
                >
                  {submitting ? t('loading') : t('add_terminal')}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </PageHeading>

      {terminals.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center">
            <CreditCard className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">{t('no_terminals')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {terminals.map((term) => (
            <div
              key={term.id}
              className="dxr-tile flex items-center justify-between"
            >
              <div className="flex items-center gap-2">
                <CreditCard className="h-4 w-4 text-brand-600" />
                <span className="text-foreground font-medium">{term.label || `#${term.id}`}</span>
                <span className="text-xs text-muted-foreground">
                  {term.provider}
                  {term.serial ? ` · ${term.serial}` : ''}
                  {term.branch_id ? ` · #${term.branch_id}` : ''}
                </span>
              </div>
              {term.status === 'active' ? (
                <span className="pill-success">{t('terminal_active')}</span>
              ) : (
                <span className="pill-muted">{term.status}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
