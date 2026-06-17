import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
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
import {
  listPrinters,
  createPrinter,
  updatePrinter,
  deletePrinter,
  type Printer,
  type PrinterRole,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { Printer as PrinterIcon, Star, Plus } from 'lucide-react';

interface PrinterFormData {
  name: string;
  role: PrinterRole;
  station_id: string;
  device_id: string;
  paper_size: string;
  is_default: boolean;
}

const emptyForm: PrinterFormData = {
  name: '',
  role: 'receipt',
  station_id: '',
  device_id: '',
  paper_size: '80mm',
  is_default: false,
};

export default function PrinterSettings() {
  const [printers, setPrinters] = useState<Printer[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [formData, setFormData] = useState<PrinterFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const { t } = useLanguage();

  useEffect(() => {
    loadPrinters();
  }, []);

  async function loadPrinters() {
    setLoading(true);
    try {
      const data = await listPrinters();
      setPrinters(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load printers:', err);
      setPrinters([]);
    } finally {
      setLoading(false);
    }
  }

  function handleFormChange(field: keyof PrinterFormData, value: string | boolean) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  async function handleAddPrinter() {
    setSubmitting(true);
    try {
      await createPrinter({
        name: formData.name,
        role: formData.role,
        station_id: formData.station_id ? parseInt(formData.station_id, 10) : undefined,
        device_id: formData.device_id || undefined,
        paper_size: formData.paper_size || undefined,
        is_default: formData.is_default,
      });
      setAddOpen(false);
      setFormData(emptyForm);
      await loadPrinters();
    } catch (err) {
      console.error('Failed to create printer:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSetDefault(printer: Printer) {
    try {
      await updatePrinter(printer.id, { is_default: true, role: printer.role });
      await loadPrinters();
    } catch (err) {
      console.error('Failed to set default printer:', err);
    }
  }

  async function handleDelete(printer: Printer) {
    try {
      await deletePrinter(printer.id);
      await loadPrinters();
    } catch (err) {
      console.error('Failed to delete printer:', err);
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
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><PrinterIcon className="h-[18px] w-[18px]" /></span>}
        title={t('printer_settings')}
        subtitle={`${printers.length} ${t('configured') || 'configured'}`}
      >
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button onClick={() => setFormData(emptyForm)} className="h-11 rounded-[10px] shadow-brand">
              <Plus className="h-4 w-4 me-2" /> {t('add_printer')}
            </Button>
          </DialogTrigger>
          <DialogContent className="max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{t('add_printer')}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label className="text-muted-foreground">{t('printer_name')} *</Label>
                <Input
                  value={formData.name}
                  onChange={(e) => handleFormChange('name', e.target.value)}
                  placeholder={t('printer_name')}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-muted-foreground">{t('printer_role')}</Label>
                <Select
                  value={formData.role}
                  onValueChange={(v) => handleFormChange('role', v as PrinterRole)}
                >
                  <SelectTrigger aria-label={t('printer_role')}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="receipt">{t('role_receipt')}</SelectItem>
                    <SelectItem value="kot">{t('role_kot')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-muted-foreground">{t('paper_size')}</Label>
                <Select
                  value={formData.paper_size}
                  onValueChange={(v) => handleFormChange('paper_size', v)}
                >
                  <SelectTrigger aria-label={t('paper_size')}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="80mm">80mm</SelectItem>
                    <SelectItem value="58mm">58mm</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-muted-foreground">{t('prep_station_optional')}</Label>
                <Input
                  type="number"
                  value={formData.station_id}
                  onChange={(e) => handleFormChange('station_id', e.target.value)}
                  placeholder="—"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-muted-foreground">{t('device_label')}</Label>
                <Input
                  value={formData.device_id}
                  onChange={(e) => handleFormChange('device_id', e.target.value)}
                  placeholder="usb:0x04b8"
                />
              </div>
              <Label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={formData.is_default}
                  onCheckedChange={(c) => handleFormChange('is_default', c === true)}
                />
                {t('set_as_default')}
              </Label>
              <div className="flex gap-3 pt-2">
                <Button
                  onClick={handleAddPrinter}
                  disabled={submitting || !formData.name}
                  className="flex-1 shadow-brand"
                >
                  {submitting ? t('loading') : t('add_printer')}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </PageHeading>

      {printers.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center">
            <PrinterIcon className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">{t('no_printers')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {printers.map((p) => (
            <div
              key={p.id}
              className="dxr-tile flex items-center justify-between"
            >
              <div className="flex items-center gap-2">
                <PrinterIcon className="h-4 w-4 text-brand-600" />
                <span className="text-foreground font-medium">{p.name}</span>
                <span className="text-xs text-muted-foreground">
                  {p.role === 'kot' ? t('role_kot') : t('role_receipt')}
                  {p.paper_size ? ` · ${p.paper_size}` : ''}
                  {p.station_id ? ` · #${p.station_id}` : ''}
                </span>
                {p.is_default && (
                  <span className="pill-gold">
                    <Star className="h-3.5 w-3.5 fill-current" />
                    {t('default_printer')}
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                {!p.is_default && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleSetDefault(p)}
                    className="text-xs"
                  >
                    {t('set_as_default')}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => handleDelete(p)}
                  className="text-xs"
                >
                  {t('delete')}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
