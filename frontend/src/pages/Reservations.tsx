import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  getRestaurantTables,
  getReservations,
  createReservation,
  cancelReservation,
  getWaitlist,
  addToWaitlist,
  cancelWaitlistEntry,
  seatWaitlistEntry,
  type RestaurantTable,
  type Reservation,
  type WaitlistEntry,
} from '@/lib/api';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import OfflineBanner from '@/components/states/OfflineBanner';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import { useLanguage } from '@/lib/i18n';
import { CalendarClock, ListOrdered, Plus, Users, Armchair, X } from 'lucide-react';

// Status badge tints — a seated party reads as a positive outcome (success),
// while cancelled / no-show fade to muted; active bookings/waits stay brand.
const STATUS_BADGE: Record<string, string> = {
  booked: 'bg-brand-500/15 text-brand-600',
  waiting: 'bg-brand-500/15 text-brand-600',
  seated: 'pill-success',
  cancelled: 'pill-muted',
  no_show: 'pill-muted',
};

function statusLabel(t: (k: string) => string, status?: string | null): string {
  switch (status) {
    case 'booked':
      return t('rw_status_booked');
    case 'seated':
      return t('rw_status_seated');
    case 'cancelled':
      return t('rw_status_cancelled');
    case 'waiting':
      return t('rw_status_waiting');
    default:
      return status || '';
  }
}

export default function Reservations() {
  const { t } = useLanguage();

  const [tables, setTables] = useState<RestaurantTable[]>([]);
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [waitlist, setWaitlist] = useState<WaitlistEntry[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);
  const [submitting, setSubmitting] = useState(false);

  // Reservation form.
  const [resForm, setResForm] = useState<{
    table_id?: number;
    reserved_at: string;
    customer_name: string;
    party_size: number;
  }>({ reserved_at: '', customer_name: '', party_size: 2 });

  // Waitlist form.
  const [waitForm, setWaitForm] = useState<{ customer_name: string; party_size: number }>({
    customer_name: '',
    party_size: 2,
  });

  // Connectivity badge (UX-02 offline state).
  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const [tablesRes, resRes, waitRes] = await Promise.all([
        getRestaurantTables(),
        getReservations({ status: 'booked' }),
        getWaitlist({ status: 'waiting' }),
      ]);
      setTables(tablesRes.items || []);
      setReservations(resRes.items || []);
      setWaitlist(waitRes.items || []);
    } catch (err: unknown) {
      // A retail merchant (or a disabled restaurant feature) is 403'd by the gate.
      const status = (err as { status?: number; response?: { status?: number } })?.status
        ?? (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) {
        setDenied(true);
      } else {
        setError(true);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function submitReservation() {
    if (!resForm.reserved_at) return;
    setSubmitting(true);
    try {
      await createReservation({
        table_id: resForm.table_id,
        reserved_at: resForm.reserved_at,
        customer_name: resForm.customer_name || undefined,
        party_size: resForm.party_size,
      });
      setResForm({ reserved_at: '', customer_name: '', party_size: 2 });
      await load();
    } catch (err) {
      console.error('Failed to create reservation:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function cancelRes(id: number) {
    try {
      await cancelReservation(id);
      await load();
    } catch (err) {
      console.error('Failed to cancel reservation:', err);
    }
  }

  async function submitWaitlist() {
    if (!waitForm.customer_name.trim()) return;
    setSubmitting(true);
    try {
      await addToWaitlist({
        customer_name: waitForm.customer_name,
        party_size: waitForm.party_size,
      });
      setWaitForm({ customer_name: '', party_size: 2 });
      await load();
    } catch (err) {
      console.error('Failed to add to waitlist:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function seatEntry(entryId: number, tableId: number) {
    try {
      await seatWaitlistEntry(entryId, tableId);
      await load();
    } catch (err) {
      console.error('Failed to seat party:', err);
    }
  }

  async function cancelWait(id: number) {
    try {
      await cancelWaitlistEntry(id);
      await load();
    } catch (err) {
      console.error('Failed to cancel waitlist entry:', err);
    }
  }

  const freeTables = tables.filter((tbl) => (tbl.state || 'free') === 'free');

  if (denied) {
    return <PermissionDenied description={t('rw_denied')} />;
  }

  return (
    <div className="animate-fade-up space-y-6 p-4 sm:p-6">
      {!online && <OfflineBanner />}

      <PageHeading
        title={t('rw_title')}
        subtitle={t('rw_subtitle')}
        icon={
          <span className="dxr-sw dxr-sw-brand h-10 w-10">
            <CalendarClock className="h-[18px] w-[18px]" />
          </span>
        }
      />

      {error ? (
        <ErrorState message={t('rw_error')} onRetry={load} />
      ) : loading ? (
        <div className="py-16 text-center text-muted-foreground" role="status">
          {t('loading')}
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* ---------- Reservations ---------- */}
          <Card className="border-brand-500/20">
            <CardContent className="space-y-4 p-5">
              <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground">
                <CalendarClock className="h-5 w-5 text-brand-600" />
                {t('rw_reservations')}
              </h2>

              {/* Book-a-table form */}
              <div className="grid gap-2 rounded-lg border border-border p-3">
                <span className="text-sm font-medium text-foreground">{t('rw_book_table')}</span>
                <Input
                  type="datetime-local"
                  aria-label={t('rw_reserved_at')}
                  value={resForm.reserved_at}
                  onChange={(e) => setResForm((f) => ({ ...f, reserved_at: e.target.value }))}
                />
                <Input
                  placeholder={t('rw_customer_name')}
                  aria-label={t('rw_customer_name')}
                  value={resForm.customer_name}
                  onChange={(e) => setResForm((f) => ({ ...f, customer_name: e.target.value }))}
                />
                <div className="flex gap-2">
                  <select
                    aria-label={t('rw_table')}
                    className="flex h-9 flex-1 rounded-md border border-input bg-background px-3 text-sm"
                    value={resForm.table_id ?? ''}
                    onChange={(e) =>
                      setResForm((f) => ({
                        ...f,
                        table_id: e.target.value ? Number(e.target.value) : undefined,
                      }))
                    }
                  >
                    <option value="">{t('rw_select_table')}</option>
                    {tables.map((tbl) => (
                      <option key={tbl.id} value={tbl.id}>
                        {tbl.name}
                      </option>
                    ))}
                  </select>
                  <Input
                    type="number"
                    min={1}
                    aria-label={t('rw_party_size')}
                    className="w-20"
                    value={resForm.party_size}
                    onChange={(e) =>
                      setResForm((f) => ({ ...f, party_size: Number(e.target.value) || 1 }))
                    }
                  />
                </div>
                <Button
                  onClick={submitReservation}
                  disabled={submitting || !resForm.reserved_at}
                >
                  <Plus className="mr-1 h-4 w-4" />
                  {t('rw_add_reservation')}
                </Button>
              </div>

              {/* Upcoming reservations list */}
              {reservations.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  {t('rw_no_reservations')}
                </p>
              ) : (
                <ul className="space-y-2">
                  {reservations.map((r) => {
                    const tbl = tables.find((x) => x.id === r.table_id);
                    return (
                      <li
                        key={r.id}
                        className="flex items-center justify-between rounded-lg border border-border p-3"
                      >
                        <div className="min-w-0">
                          <p className="truncate font-medium text-foreground">
                            {r.customer_name || t('rw_walk_in')}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {tbl ? tbl.name : '—'} · {r.reserved_at?.replace('T', ' ').slice(0, 16)}{' '}
                            · <Users className="inline h-3 w-3" /> {r.party_size ?? '—'}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge className={STATUS_BADGE[r.status || 'booked']}>
                            {statusLabel(t, r.status)}
                          </Badge>
                          <Button
                            variant="ghost"
                            size="sm"
                            aria-label={`${t('rw_status_cancelled')} ${r.id}`}
                            onClick={() => cancelRes(r.id)}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>

          {/* ---------- Waitlist ---------- */}
          <Card className="border-brand-500/20">
            <CardContent className="space-y-4 p-5">
              <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground">
                <ListOrdered className="h-5 w-5 text-brand-600" />
                {t('rw_waitlist')}
              </h2>

              {/* Add walk-in form */}
              <div className="grid gap-2 rounded-lg border border-border p-3">
                <span className="text-sm font-medium text-foreground">{t('rw_walk_in')}</span>
                <div className="flex gap-2">
                  <Input
                    placeholder={t('rw_customer_name')}
                    aria-label={t('rw_customer_name')}
                    className="flex-1"
                    value={waitForm.customer_name}
                    onChange={(e) => setWaitForm((f) => ({ ...f, customer_name: e.target.value }))}
                  />
                  <Input
                    type="number"
                    min={1}
                    aria-label={t('rw_party_size')}
                    className="w-20"
                    value={waitForm.party_size}
                    onChange={(e) =>
                      setWaitForm((f) => ({ ...f, party_size: Number(e.target.value) || 1 }))
                    }
                  />
                </div>
                <Button
                  onClick={submitWaitlist}
                  disabled={submitting || !waitForm.customer_name.trim()}
                >
                  <Plus className="mr-1 h-4 w-4" />
                  {t('rw_add_party')}
                </Button>
              </div>

              {/* Live queue */}
              {waitlist.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  {t('rw_no_waitlist')}
                </p>
              ) : (
                <ul className="space-y-2">
                  {waitlist.map((w, idx) => (
                    <li key={w.id} className="rounded-lg border border-border p-3">
                      <div className="flex items-center justify-between">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-500/15 text-xs font-semibold text-brand-600">
                            {idx + 1}
                          </span>
                          <div className="min-w-0">
                            <p className="truncate font-medium text-foreground">
                              {w.customer_name || t('rw_walk_in')}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              <Users className="inline h-3 w-3" /> {w.party_size ?? '—'}
                            </p>
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`${t('rw_status_cancelled')} ${w.id}`}
                          onClick={() => cancelWait(w.id)}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                      {/* Seat to a free table */}
                      <div className="mt-2 flex items-center gap-2">
                        <Armchair className="h-4 w-4 text-muted-foreground" />
                        <select
                          aria-label={`${t('rw_seat_at')} ${w.id}`}
                          className="flex h-9 flex-1 rounded-md border border-input bg-background px-3 text-sm"
                          defaultValue=""
                          onChange={(e) => {
                            if (e.target.value) seatEntry(w.id, Number(e.target.value));
                          }}
                          disabled={freeTables.length === 0}
                        >
                          <option value="">{t('rw_seat')}…</option>
                          {freeTables.map((tbl) => (
                            <option key={tbl.id} value={tbl.id}>
                              {tbl.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
