import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
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
import { getStaffMembers, createStaffMember, updateStaffMember, deleteStaffMember } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { UserCheck, UserX, Users } from 'lucide-react';

interface StaffMember {
  id: string;
  name: string;
  email?: string;
  phone?: string;
  role: string;
  is_active?: boolean;
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
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedStaff, setSelectedStaff] = useState<StaffMember | null>(null);
  const [formData, setFormData] = useState<StaffFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const { t } = useLanguage();

  useEffect(() => {
    loadStaff();
  }, []);

  async function loadStaff() {
    setLoading(true);
    try {
      const data = await getStaffMembers();
      setStaff(Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load staff:', err);
      setStaff([]);
    } finally {
      setLoading(false);
    }
  }

  const activeCount = staff.filter((s) => s.is_active !== false).length;
  const inactiveCount = staff.filter((s) => s.is_active === false).length;

  function handleFormChange(field: keyof StaffFormData, value: string) {
    setFormData((prev) => ({ ...prev, [field]: value }));
  }

  async function handleAddStaff() {
    setSubmitting(true);
    try {
      await createStaffMember({
        name: formData.name,
        email: formData.email || undefined,
        phone: formData.phone || undefined,
        role: formData.role,
        is_active: true,
      });
      setAddOpen(false);
      setFormData(emptyForm);
      await loadStaff();
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

  async function toggleStatus(member: StaffMember) {
    try {
      await updateStaffMember(member.id, { is_active: member.is_active === false });
      await loadStaff();
    } catch (err) {
      console.error('Failed to toggle staff status:', err);
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

  function renderForm(onSubmit: () => void, submitLabel: string) {
    return (
      <div className="space-y-4">
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Name *</label>
          <Input
            value={formData.name}
            onChange={(e) => handleFormChange('name', e.target.value)}
            placeholder="Staff name"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Email</label>
          <Input
            value={formData.email}
            onChange={(e) => handleFormChange('email', e.target.value)}
            placeholder="email@example.com"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Phone</label>
          <Input
            value={formData.phone}
            onChange={(e) => handleFormChange('phone', e.target.value)}
            placeholder="+966 5xx xxx xxxx"
            className="bg-slate-700 border-slate-600 text-white"
          />
        </div>
        <div>
          <label className="text-sm text-slate-400 mb-1 block">Role *</label>
          <Select value={formData.role} onValueChange={(v) => handleFormChange('role', v)}>
            <SelectTrigger className="bg-slate-700 border-slate-600 text-white">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-slate-800 border-slate-600">
              {STAFF_ROLES.map((role) => (
                <SelectItem key={role} value={role} className="text-white hover:bg-slate-700 capitalize">
                  {role.charAt(0).toUpperCase() + role.slice(1)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex gap-3 pt-2">
          <Button
            onClick={onSubmit}
            disabled={submitting || !formData.name || !formData.role}
            className="flex-1 bg-brand-600 hover:bg-brand-700 text-white"
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
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <Users className="h-8 w-8 text-brand-400" />
            <div>
              <p className="text-slate-400 text-sm">Total Staff</p>
              <p className="text-2xl font-bold text-white">{staff.length}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <UserCheck className="h-8 w-8 text-green-400" />
            <div>
              <p className="text-slate-400 text-sm">{t('active')}</p>
              <p className="text-2xl font-bold text-green-400">{activeCount}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <UserX className="h-8 w-8 text-red-400" />
            <div>
              <p className="text-slate-400 text-sm">{t('inactive')}</p>
              <p className="text-2xl font-bold text-red-400">{inactiveCount}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Add Button */}
      <div className="flex justify-end">
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button
              onClick={() => setFormData(emptyForm)}
              className="bg-brand-600 hover:bg-brand-700 text-white"
            >
              + Add Staff
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-slate-800 border-slate-700 text-white max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="text-white">Add New Staff Member</DialogTitle>
            </DialogHeader>
            {renderForm(handleAddStaff, 'Add Staff')}
          </DialogContent>
        </Dialog>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full text-sm">
          <thead className="bg-slate-800">
            <tr className="text-slate-400">
              <th className="p-3 text-start">Name</th>
              <th className="p-3 text-start">Email</th>
              <th className="p-3 text-start">Phone</th>
              <th className="p-3 text-start">Role</th>
              <th className="p-3 text-start">{t('status')}</th>
              <th className="p-3 text-start">Actions</th>
            </tr>
          </thead>
          <tbody>
            {staff.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-6 text-center text-slate-500">
                  No staff members found
                </td>
              </tr>
            ) : (
              staff.map((member) => (
                <tr key={member.id} className="border-t border-slate-700 text-slate-300">
                  <td className="p-3 text-white font-medium">{member.name}</td>
                  <td className="p-3">{member.email || '—'}</td>
                  <td className="p-3">{member.phone || '—'}</td>
                  <td className="p-3">
                    <Badge className="bg-slate-700 text-slate-300 capitalize">
                      {member.role}
                    </Badge>
                  </td>
                  <td className="p-3">
                    {member.is_active !== false ? (
                      <Badge className="bg-green-600/20 text-green-400 border border-green-600/40">
                        {t('active')}
                      </Badge>
                    ) : (
                      <Badge className="bg-slate-600/20 text-slate-400 border border-slate-600/40">
                        {t('inactive')}
                      </Badge>
                    )}
                  </td>
                  <td className="p-3">
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => toggleStatus(member)}
                        className={`text-xs ${
                          member.is_active !== false
                            ? 'border-orange-600/50 text-orange-400 hover:bg-orange-600/20'
                            : 'border-green-600/50 text-green-400 hover:bg-green-600/20'
                        }`}
                      >
                        {member.is_active !== false ? 'Deactivate' : 'Activate'}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openEdit(member)}
                        className="border-slate-600 text-slate-300 hover:bg-slate-700 text-xs"
                      >
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => openDelete(member)}
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
            <DialogTitle className="text-white">Edit Staff Member</DialogTitle>
          </DialogHeader>
          {renderForm(handleEditStaff, t('save'))}
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="bg-slate-800 border-slate-700 text-white">
          <DialogHeader>
            <DialogTitle className="text-white">Confirm Delete</DialogTitle>
          </DialogHeader>
          <p className="text-slate-300">
            Are you sure you want to delete <strong>{selectedStaff?.name}</strong>? This action
            cannot be undone.
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
              onClick={handleDeleteStaff}
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