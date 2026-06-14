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
import {
  listPrinters,
  createPrinter,
  updatePrinter,
  deletePrinter,
  type Printer,
  type PrinterRole,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { Printer as PrinterIcon, Star } from 'lucide-react';

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
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="bg-slate-800 border-slate-700">
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <PrinterIcon className="h-8 w-8 text-brand-400" />
            <div>
              <h2 className="text-lg font-bold text-white">{t('printer_settings')}</h2>
              <p className="text-slate-400 text-sm">{printers.length}</p>
            </div>
          </div>
          <Dialog open={addOpen} onOpenChange={setAddOpen}>
            <DialogTrigger asChild>
              <Button
                onClick={() => setFormData(emptyForm)}
                className="bg-brand-600 hover:bg-brand-700 text-white"
              >
                + {t('add_printer')}
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle className="text-white">{t('add_printer')}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-slate-400 mb-1 block">{t('printer_name')} *</label>
                  <Input
                    value={formData.name}
                    onChange={(e) => handleFormChange('name', e.target.value)}
                    placeholder={t('printer_name')}
                    className="bg-slate-700 border-slate-600 text-white"
                  />
                </div>
                <div>
                  <label className="text-sm text-slate-400 mb-1 block">{t('printer_role')}</label>
                  <select
                    aria-label={t('printer_role')}
                    value={formData.role}
                    onChange={(e) => handleFormChange('role', e.target.value as PrinterRole)}
                    className="w-full rounded-md bg-slate-700 border border-slate-600 text-white p-2 text-sm"
                  >
                    <option value="receipt">{t('role_receipt')}</option>
                    <option value="kot">{t('role_kot')}</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm text-slate-400 mb-1 block">{t('paper_size')}</label>
                  <select
                    aria-label={t('paper_size')}
                    value={formData.paper_size}
                    onChange={(e) => handleFormChange('paper_size', e.target.value)}
                    className="w-full rounded-md bg-slate-700 border border-slate-600 text-white p-2 text-sm"
                  >
                    <option value="80mm">80mm</option>
                    <option value="58mm">58mm</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm text-slate-400 mb-1 block">
                    {t('prep_station_optional')}
                  </label>
                  <Input
                    type="number"
                    value={formData.station_id}
                    onChange={(e) => handleFormChange('station_id', e.target.value)}
                    placeholder="—"
                    className="bg-slate-700 border-slate-600 text-white"
                  />
                </div>
                <div>
                  <label className="text-sm text-slate-400 mb-1 block">{t('device_label')}</label>
                  <Input
                    value={formData.device_id}
                    onChange={(e) => handleFormChange('device_id', e.target.value)}
                    placeholder="usb:0x04b8"
                    className="bg-slate-700 border-slate-600 text-white"
                  />
                </div>
                <label className="flex items-center gap-2 text-sm text-slate-300">
                  <input
                    type="checkbox"
                    checked={formData.is_default}
                    onChange={(e) => handleFormChange('is_default', e.target.checked)}
                  />
                  {t('set_as_default')}
                </label>
                <div className="flex gap-3 pt-2">
                  <Button
                    onClick={handleAddPrinter}
                    disabled={submitting || !formData.name}
                    className="flex-1 bg-brand-600 hover:bg-brand-700 text-white"
                  >
                    {submitting ? t('loading') : t('add_printer')}
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>

      {printers.length === 0 ? (
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-8 text-center">
            <PrinterIcon className="h-12 w-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-500">{t('no_printers')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {printers.map((p) => (
            <div
              key={p.id}
              className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-slate-700"
            >
              <div className="flex items-center gap-2">
                <PrinterIcon className="h-4 w-4 text-brand-400" />
                <span className="text-white font-medium">{p.name}</span>
                <span className="text-xs text-slate-500">
                  {p.role === 'kot' ? t('role_kot') : t('role_receipt')}
                  {p.paper_size ? ` · ${p.paper_size}` : ''}
                  {p.station_id ? ` · #${p.station_id}` : ''}
                </span>
                {p.is_default && (
                  <span className="inline-flex items-center gap-1 text-xs text-amber-400">
                    <Star className="h-3.5 w-3.5 fill-amber-400" />
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
                    className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs"
                  >
                    {t('set_as_default')}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleDelete(p)}
                  className="border-red-600/50 text-red-400 hover:bg-red-600/20 text-xs"
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
