import { useCallback, useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  assignStaffShift,
  cancelStaffShift,
  clearStaffPin,
  clockInStaff,
  clockOutStaff,
  getStaffAttendance,
  getStaffShifts,
  setStaffLifecycle,
  setStaffPin,
  type StaffAttendance,
  type StaffLifecycleAction,
  type StaffShift,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatDateTime } from '@/lib/format';
import { toast } from 'sonner';

export interface WorkforceStaff {
  id: string | number;
  name: string;
  status?: string;
  is_active?: boolean;
}

/** Resolve a staff member's effective lifecycle status, tolerating older rows
 * that only carry the legacy ``is_active`` flag. */
export function staffStatus(member: { status?: string; is_active?: boolean }): string {
  if (member.status) return member.status;
  return member.is_active === false ? 'suspended' : 'active';
}

const STATUS_PILL: Record<string, string> = {
  active: 'pill-success',
  suspended: 'pill-warning',
  terminated: 'pill-danger',
};

export function StatusPill({ status }: { status: string }) {
  const { t } = useLanguage();
  return <span className={STATUS_PILL[status] || 'pill-muted'}>{t(`stf_status_${status}`)}</span>;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  staff: WorkforceStaff | null;
  onChanged: () => void;
}

export default function StaffWorkforceDialog({ open, onOpenChange, staff, onChanged }: Props) {
  const { t, language } = useLanguage();
  const [busy, setBusy] = useState(false);

  // PIN
  const [pin, setPin] = useState('');

  // Attendance
  const [attendance, setAttendance] = useState<StaffAttendance[]>([]);
  const [attLoading, setAttLoading] = useState(false);

  // Schedule
  const [shifts, setShifts] = useState<StaffShift[]>([]);
  const [shiftsLoading, setShiftsLoading] = useState(false);
  const [shiftStart, setShiftStart] = useState('');
  const [shiftEnd, setShiftEnd] = useState('');
  const [shiftRole, setShiftRole] = useState('');

  const status = staff ? staffStatus(staff) : 'active';
  const openRecord = attendance.find((a) => !a.clock_out);

  const loadAttendance = useCallback(async () => {
    if (!staff) return;
    setAttLoading(true);
    try {
      setAttendance(await getStaffAttendance(staff.id));
    } catch (err) {
      console.error('Failed to load attendance:', err);
      setAttendance([]);
    } finally {
      setAttLoading(false);
    }
  }, [staff]);

  const loadShifts = useCallback(async () => {
    if (!staff) return;
    setShiftsLoading(true);
    try {
      setShifts(await getStaffShifts(staff.id));
    } catch (err) {
      console.error('Failed to load shifts:', err);
      setShifts([]);
    } finally {
      setShiftsLoading(false);
    }
  }, [staff]);

  useEffect(() => {
    if (open && staff) {
      setPin('');
      setShiftStart('');
      setShiftEnd('');
      setShiftRole('');
      loadAttendance();
      loadShifts();
    }
  }, [open, staff, loadAttendance, loadShifts]);

  if (!staff) return null;

  async function runLifecycle(action: StaffLifecycleAction) {
    if (!staff) return;
    setBusy(true);
    try {
      await setStaffLifecycle(staff.id, action);
      toast.success(t(`stf_${action}_done`));
      onChanged();
    } catch (err) {
      console.error('Lifecycle action failed:', err);
      toast.error(t('stf_action_failed'));
    } finally {
      setBusy(false);
    }
  }

  async function handleSetPin() {
    if (!staff) return;
    setBusy(true);
    try {
      await setStaffPin(staff.id, pin);
      setPin('');
      toast.success(t('stf_pin_set_done'));
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || t('stf_action_failed'));
    } finally {
      setBusy(false);
    }
  }

  async function handleClearPin() {
    if (!staff) return;
    setBusy(true);
    try {
      await clearStaffPin(staff.id);
      toast.success(t('stf_pin_cleared_done'));
    } catch (err) {
      console.error('Clear PIN failed:', err);
      toast.error(t('stf_action_failed'));
    } finally {
      setBusy(false);
    }
  }

  async function handleClock() {
    if (!staff) return;
    setBusy(true);
    try {
      if (openRecord) {
        await clockOutStaff(staff.id);
        toast.success(t('stf_clocked_out'));
      } else {
        await clockInStaff(staff.id);
        toast.success(t('stf_clocked_in'));
      }
      await loadAttendance();
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || t('stf_action_failed'));
    } finally {
      setBusy(false);
    }
  }

  async function handleAssignShift() {
    if (!staff || !shiftStart || !shiftEnd) return;
    setBusy(true);
    try {
      await assignStaffShift(staff.id, {
        starts_at: new Date(shiftStart).toISOString(),
        ends_at: new Date(shiftEnd).toISOString(),
        role: shiftRole || undefined,
      });
      setShiftStart('');
      setShiftEnd('');
      setShiftRole('');
      toast.success(t('stf_shift_assigned'));
      await loadShifts();
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || t('stf_action_failed'));
    } finally {
      setBusy(false);
    }
  }

  async function handleCancelShift(shiftId: number) {
    setBusy(true);
    try {
      await cancelStaffShift(shiftId);
      await loadShifts();
    } catch (err) {
      console.error('Cancel shift failed:', err);
      toast.error(t('stf_action_failed'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {t('stf_workforce')} — {staff.name}
            <StatusPill status={status} />
          </DialogTitle>
        </DialogHeader>

        <Tabs defaultValue="lifecycle" className="mt-2">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="lifecycle">{t('stf_tab_lifecycle')}</TabsTrigger>
            <TabsTrigger value="attendance">{t('stf_tab_attendance')}</TabsTrigger>
            <TabsTrigger value="schedule">{t('stf_tab_schedule')}</TabsTrigger>
            <TabsTrigger value="pin">{t('pin')}</TabsTrigger>
          </TabsList>

          {/* Lifecycle */}
          <TabsContent value="lifecycle" className="space-y-3 pt-3">
            <p className="text-sm text-muted-foreground">{t('stf_lifecycle_hint')}</p>
            <div className="flex flex-wrap gap-2">
              {status !== 'active' && (
                <Button onClick={() => runLifecycle('reactivate')} disabled={busy}>
                  {t('stf_reactivate')}
                </Button>
              )}
              {status === 'active' && (
                <Button
                  variant="outline"
                  className="border-warning text-warning hover:bg-warning/10"
                  onClick={() => runLifecycle('suspend')}
                  disabled={busy}
                >
                  {t('stf_suspend')}
                </Button>
              )}
              {status !== 'terminated' && (
                <Button variant="destructive" onClick={() => runLifecycle('terminate')} disabled={busy}>
                  {t('stf_terminate')}
                </Button>
              )}
            </div>
          </TabsContent>

          {/* Attendance */}
          <TabsContent value="attendance" className="space-y-3 pt-3">
            <Button onClick={handleClock} disabled={busy || status !== 'active'} className="w-full">
              {openRecord ? t('stf_clock_out') : t('stf_clock_in')}
            </Button>
            {attLoading ? (
              <p className="py-4 text-center text-muted-foreground animate-pulse">{t('loading')}</p>
            ) : attendance.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">{t('stf_no_attendance')}</p>
            ) : (
              <ul className="space-y-2">
                {attendance.map((a) => (
                  <li
                    key={a.id}
                    className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background/40 p-3 text-sm"
                  >
                    <div className="min-w-0">
                      <p className="text-foreground">{a.clock_in ? formatDateTime(a.clock_in, language) : '—'}</p>
                      <p className="text-xs text-muted-foreground">
                        {a.clock_out ? formatDateTime(a.clock_out, language) : t('stf_attendance_open')}
                      </p>
                    </div>
                    <span className={a.clock_out ? 'pill-muted' : 'pill-success'}>
                      {a.hours != null ? `${a.hours} ${t('stf_hours')}` : t('stf_attendance_open')}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </TabsContent>

          {/* Schedule */}
          <TabsContent value="schedule" className="space-y-3 pt-3">
            <div className="grid gap-3">
              <div>
                <Label className="mb-1 block">{t('stf_shift_start')}</Label>
                <Input
                  type="datetime-local"
                  value={shiftStart}
                  onChange={(e) => setShiftStart(e.target.value)}
                />
              </div>
              <div>
                <Label className="mb-1 block">{t('stf_shift_end')}</Label>
                <Input
                  type="datetime-local"
                  value={shiftEnd}
                  onChange={(e) => setShiftEnd(e.target.value)}
                />
              </div>
              <div>
                <Label className="mb-1 block">{t('role')}</Label>
                <Input
                  value={shiftRole}
                  onChange={(e) => setShiftRole(e.target.value)}
                  placeholder={t('stf_shift_role_ph')}
                />
              </div>
              <Button onClick={handleAssignShift} disabled={busy || !shiftStart || !shiftEnd}>
                {t('stf_assign_shift')}
              </Button>
            </div>
            {shiftsLoading ? (
              <p className="py-4 text-center text-muted-foreground animate-pulse">{t('loading')}</p>
            ) : shifts.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">{t('stf_no_shifts')}</p>
            ) : (
              <ul className="space-y-2">
                {shifts.map((s) => (
                  <li
                    key={s.id}
                    className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background/40 p-3 text-sm"
                  >
                    <div className="min-w-0">
                      <p className="text-foreground">
                        {s.starts_at ? formatDateTime(s.starts_at, language) : '—'}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {s.ends_at ? formatDateTime(s.ends_at, language) : '—'}
                        {s.role ? ` · ${s.role}` : ''}
                      </p>
                    </div>
                    {s.status === 'cancelled' ? (
                      <span className="pill-muted">{t('cancelled')}</span>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-xs"
                        onClick={() => handleCancelShift(s.id)}
                        disabled={busy}
                      >
                        {t('cancel')}
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </TabsContent>

          {/* PIN */}
          <TabsContent value="pin" className="space-y-3 pt-3">
            <p className="text-sm text-muted-foreground">{t('stf_pin_hint')}</p>
            <div>
              <Label className="mb-1 block">{t('stf_new_pin')}</Label>
              <Input
                type="password"
                inputMode="numeric"
                autoComplete="off"
                value={pin}
                onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 8))}
                placeholder="••••"
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={handleSetPin} disabled={busy || pin.length < 4} className="flex-1">
                {t('stf_set_pin')}
              </Button>
              <Button variant="outline" onClick={handleClearPin} disabled={busy}>
                {t('stf_clear_pin')}
              </Button>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
