import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
import {
  getStaffMembers,
  createStaffMember,
  updateStaffMember,
  deleteStaffMember,
  getStaffPermissions,
  setStaffPermission,
  exportStaffAttendanceCsv,
  type StaffPermission,
} from '@/lib/api';
import StaffWorkforceDialog, {
  StatusPill,
  staffStatus,
  type WorkforceStaff,
} from '@/components/staff/StaffWorkforceDialog';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import DataTable, { type DataTableColumn } from '@/components/dashboard/rx/DataTable';
import StatTile from '@/components/dashboard/StatTile';
import { useLanguage } from '@/lib/i18n';
import { Download, Plus, UserCheck, UserX, Users } from 'lucide-react';
import { toast } from 'sonner';

interface StaffMember {
  id: string;
  name: string;
  email?: string;
  phone?: string;
  role: string;
  is_active?: boolean;
  status?: string;
  created_at?: string;
}

interface StaffFormData {
  name: string;
  email: string;
  phone: string;
  role: string;
}

const STAFF_ROLES = ['cashier', 'manager', 'admin'];

const emptyForm: StaffFormData = {
  name: '',
  email: '',
  phone: '',
  role: 'cashier',
};

export default function StaffManagement() {
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedStaff, setSelectedStaff] = useState<StaffMember | null>(null);
  const [formData, setFormData] = useState<StaffFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [permsOpen, setPermsOpen] = useState(false);
  const [permsStaff, setPermsStaff] = useState<StaffMember | null>(null);
  const [perms, setPerms] = useState<StaffPermission[]>([]);
  const [permsHasLogin, setPermsHasLogin] = useState(true);
  const [permsLoading, setPermsLoading] = useState(false);
  const [workforceOpen, setWorkforceOpen] = useState(false);
  const [workforceStaff, setWorkforceStaff] = useState<WorkforceStaff | null>(null);
  const [exporting, setExporting] = useState(false);

  const { t, isRTL } = useLanguage();

  useEffect(() => {
    loadStaff();
  }, []);

  async function loadStaff() {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const data = await getStaffMembers();
      setStaff(Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      console.error('Failed to load staff:', err);
      setStaff([]);
      const status = (err as { response?: { status?: number } })?.response?.status;
      // 403 means the account lacks access to staff management; show the in-page
      // permission state rather than a misleading empty table (UX-02). Any other
      // failure is a real error, not "no staff".
      if (status === 403) {
        setDenied(true);
      } else {
        setError(true);
      }
    } finally {
      setLoading(false);
    }
  }

  const activeCount = staff.filter((s) => staffStatus(s) === 'active').length;
  const inactiveCount = staff.filter((s) => staffStatus(s) !== 'active').length;

  function openWorkforce(member: StaffMember) {
    setWorkforceStaff({
      id: member.id,
      name: member.name,
      status: member.status,
      is_active: member.is_active,
    });
    setWorkforceOpen(true);
  }

  async function handleExportAttendance() {
    setExporting(true);
    try {
      const csv = await exportStaffAttendanceCsv();
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'attendance.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to export attendance:', err);
      toast.error(t('stf_export_failed'));
    } finally {
      setExporting(false);
    }
  }

  function handleFormChange(field: keyof StaffFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  async function handleAddStaff() {
    setSubmitting(true);
    try {
      const created = await createStaffMember({
        name: formData.name,
        email: formData.email || undefined,
        phone: formData.phone || undefined,
        role: formData.role,
        is_active: true,
      });
      setAddOpen(false);
      setFormData(emptyForm);
      await loadStaff();
      // A freshly provisioned login returns a one-time temp password the merchant
      // must relay to the staff member — it is never shown again (#33).
      const tempPassword = (created as { temp_password?: string } | undefined)?.temp_password;
      if (tempPassword) {
        toast.success(t('staff_login_created') || 'Login created — share this password', {
          description: `${formData.email}: ${tempPassword}`,
          duration: Infinity,
          closeButton: true,
        });
      }
    } catch (err) {
      console.error('Failed to create staff:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function openEdit(member: StaffMember) {
    setSelectedStaff(member);
    setFormData({
      name: member.name,
      email: member.email || '',
      phone: member.phone || '',
      role: member.role || 'cashier',
    });
    setEditOpen(true);
  }

  async function handleEditStaff() {
    if (!selectedStaff) return;
    setSubmitting(true);
    try {
      await updateStaffMember(selectedStaff.id, {
        name: formData.name,
        email: formData.email || undefined,
        phone: formData.phone || undefined,
        role: formData.role,
      });
      setEditOpen(false);
      setSelectedStaff(null);
      setFormData(emptyForm);
      await loadStaff();
    } catch (err) {
      console.error('Failed to update staff:', err);
    } finally {
      setSubmitting(false);
    }
  }

  function openDelete(member: StaffMember) {
    setSelectedStaff(member);
    setDeleteOpen(true);
  }

  async function handleDeleteStaff() {
    if (!selectedStaff) return;
    setSubmitting(true);
    try {
      await deleteStaffMember(selectedStaff.id);
      setDeleteOpen(false);
      setSelectedStaff(null);
      await loadStaff();
    } catch (err) {
      console.error('Failed to delete staff:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function openPermissions(member: StaffMember) {
    setPermsStaff(member);
    setPerms([]);
    setPermsHasLogin(true);
    setPermsOpen(true);
    await loadPermissions(member.id);
  }

  async function loadPermissions(staffId: string) {
    setPermsLoading(true);
    try {
      const data = await getStaffPermissions(staffId);
      setPerms(data.permissions || []);
      setPermsHasLogin(data.has_login);
    } catch (err) {
      console.error('Failed to load staff permissions:', err);
      setPerms([]);
    } finally {
      setPermsLoading(false);
    }
  }

  async function handleSetPermission(key: string, isGranted: boolean | null) {
    if (!permsStaff) return;
    try {
      await setStaffPermission(permsStaff.id, key, isGranted);
      await loadPermissions(permsStaff.id);
    } catch (err) {
      console.error('Failed to set permission:', err);
    }
  }

  const staffColumns: DataTableColumn<StaffMember>[] = [
    {
      key: 'name',
      header: t('name'),
      cell: (member) => <span className="font-medium text-foreground">{member.name}</span>,
    },
    { key: 'email', header: t('email'), cell: (member) => member.email || '—' },
    { key: 'phone', header: t('phone'), cell: (member) => member.phone || '—' },
    {
      key: 'role',
      header: t('role'),
      cell: (member) => <span className="pill-muted">{t(`role_${member.role}`)}</span>,
    },
    {
      key: 'status',
      header: t('status'),
      cell: (member) => <StatusPill status={staffStatus(member)} />,
    },
    {
      key: 'actions',
      header: t('actions'),
      cell: (member) => (
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => openWorkforce(member)}
            className="text-xs"
          >
            {t('stf_workforce')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => openPermissions(member)}
            className="text-xs"
          >
            {t('permissions')}
          </Button>
          <Button size="sm" variant="outline" onClick={() => openEdit(member)} className="text-xs">
            {t('edit')}
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => openDelete(member)}
            className="text-xs"
          >
            {t('delete')}
          </Button>
        </div>
      ),
    },
  ];

  function renderForm(onSubmit: () => void, submitLabel: string) {
    return (
      <div className="space-y-4">
        <div>
          <Label className="mb-1 block">{t('name')} *</Label>
          <Input
            value={formData.name}
            onChange={(e) => handleFormChange('name', e.target.value)}
            placeholder={t('stf_name_ph')}
          />
        </div>
        <div>
          <Label className="mb-1 block">{t('email')}</Label>
          <Input
            value={formData.email}
            onChange={(e) => handleFormChange('email', e.target.value)}
            placeholder={t('stf_email_ph')}
          />
        </div>
        <div>
          <Label className="mb-1 block">{t('phone')}</Label>
          <Input
            value={formData.phone}
            onChange={(e) => handleFormChange('phone', e.target.value)}
            placeholder="+966 5xx xxx xxxx"
          />
        </div>
        <div>
          <Label className="mb-1 block">{t('role')} *</Label>
          <Select value={formData.role} onValueChange={(v) => handleFormChange('role', v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STAFF_ROLES.map((role) => (
                <SelectItem key={role} value={role}>
                  {t(`role_${role}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex gap-3 pt-2">
          <Button
            onClick={onSubmit}
            disabled={submitting || !formData.name || !formData.role}
            className="flex-1"
          >
            {submitting ? t('loading') : submitLabel}
          </Button>
        </div>
      </div>
    );
  }

  if (loading && staff.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-foreground animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  // A 403 lacks access; any other failure is a real error — show the in-page
  // state rather than a misleading empty table (UX-02).
  if (denied) {
    return (
      <div dir={isRTL ? 'rtl' : 'ltr'}>
        <PermissionDenied />
      </div>
    );
  }
  if (error) {
    return (
      <div dir={isRTL ? 'rtl' : 'ltr'}>
        <ErrorState onRetry={loadStaff} />
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-6" dir={isRTL ? 'rtl' : 'ltr'}>
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <PageHeading
          icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><Users className="h-[18px] w-[18px]" /></span>}
          title={t('staff')}
          subtitle={`${staff.length} ${t('stf_total_staff')}`}
        >
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={handleExportAttendance}
              disabled={exporting}
              className="h-11 rounded-[10px]"
            >
              <Download className="h-4 w-4" />
              {exporting ? t('loading') : t('stf_export_attendance')}
            </Button>
            <DialogTrigger asChild>
              <Button
                onClick={() => setFormData(emptyForm)}
                className="h-11 rounded-[10px] shadow-brand"
              >
                <Plus className="h-4 w-4" />
                {t('stf_add_staff')}
              </Button>
            </DialogTrigger>
          </div>
        </PageHeading>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('stf_add_title')}</DialogTitle>
          </DialogHeader>
          {renderForm(handleAddStaff, t('stf_add_staff'))}
        </DialogContent>
      </Dialog>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile icon={Users} label={t('stf_total_staff')} value={staff.length} tone="brand" />
        <StatTile icon={UserCheck} label={t('active')} value={activeCount} tone="success" />
        <StatTile icon={UserX} label={t('inactive')} value={inactiveCount} tone="warning" />
      </div>

      {/* Table */}
      <DataTable
        className="dxr-tile p-0"
        columns={staffColumns}
        rows={staff}
        rowKey={(member) => member.id}
        empty={t('stf_none')}
      />

      {/* Edit Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('stf_edit_title')}</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditStaff, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('stf_confirm_delete')}</DialogTitle>
          </DialogHeader>
          <p className="text-foreground/90">
            {t('stf_delete_q')} <strong>{selectedStaff?.name}</strong>? {t('stf_delete_warn')}
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
              onClick={handleDeleteStaff}
              disabled={submitting}
              className="flex-1"
            >
              {submitting ? t('loading') : t('delete')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Permissions Dialog (ISSUE-035) */}
      <Dialog open={permsOpen} onOpenChange={setPermsOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {t('manage_permissions')} — {permsStaff?.name}
            </DialogTitle>
          </DialogHeader>

          {permsLoading && perms.length === 0 ? (
            <div className="py-6 text-center text-muted-foreground animate-pulse">{t('loading')}</div>
          ) : !permsHasLogin ? (
            <p role="alert" className="py-4 text-sm text-warning">
              {t('no_login_permissions')}
            </p>
          ) : (
            <div className="space-y-3">
              {perms.map((p) => (
                <div
                  key={p.permission_key}
                  data-perm-row
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background/40 p-3"
                >
                  <div className="min-w-0">
                    <p className="font-mono text-sm text-foreground">{p.permission_key}</p>
                    <p className="text-xs text-muted-foreground">
                      {t('role_default')}: {p.role_default ? t('allowed') : t('denied')}
                      {p.override === null && ` · ${t('role_default')}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleSetPermission(p.permission_key, true)}
                      className={`text-xs ${
                        p.effective
                          ? 'border-success bg-success/20 text-success'
                          : 'text-muted-foreground'
                      }`}
                    >
                      {t('allowed')}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleSetPermission(p.permission_key, false)}
                      className={`text-xs ${
                        !p.effective
                          ? 'border-danger bg-danger/20 text-danger'
                          : 'text-muted-foreground'
                      }`}
                    >
                      {t('denied')}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={p.override === null}
                      onClick={() => handleSetPermission(p.permission_key, null)}
                      title={t('reset_to_default')}
                      className="text-xs text-muted-foreground disabled:opacity-40"
                    >
                      ↺
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Workforce: lifecycle / attendance / schedule / PIN (#216) */}
      <StaffWorkforceDialog
        open={workforceOpen}
        onOpenChange={setWorkforceOpen}
        staff={workforceStaff}
        onChanged={loadStaff}
      />
    </div>
  );
}