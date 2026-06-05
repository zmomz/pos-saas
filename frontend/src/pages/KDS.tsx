import { useEffect, useState, useCallback, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  getPrepStations,
  getKdsTickets,
  createPrepStation,
  bumpKdsTicket,
  recallKdsTicket,
  getKdsKot,
  kdsStreamUrl,
  type PrepStation,
  type KdsCard,
} from '@/lib/api';
import { printEscPos, isThermalPrintSupported } from '@/lib/thermalPrint';
import { useLanguage } from '@/lib/i18n';
import {
  ChefHat,
  Plus,
  WifiOff,
  AlertTriangle,
  Lock,
  Clock,
  Check,
  RotateCcw,
  Printer,
  Radio,
} from 'lucide-react';

// A short mm:ss elapsed-timer label from an ISO timestamp.
function elapsedLabel(fromIso?: string | null, now = Date.now()): string {
  if (!fromIso) return '0:00';
  const start = new Date(fromIso).getTime();
  const secs = Math.max(0, Math.floor((now - start) / 1000));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

// A card is "late" once it has been cooking for more than ten minutes.
function isLate(fromIso?: string | null, now = Date.now()): boolean {
  if (!fromIso) return false;
  return now - new Date(fromIso).getTime() > 10 * 60 * 1000;
}

export default function KDS() {
  const { t } = useLanguage();

  const [stations, setStations] = useState<PrepStation[]>([]);
  const [cards, setCards] = useState<KdsCard[]>([]);
  const [activeStation, setActiveStation] = useState<number | 'all'>('all');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);
  const [streamLive, setStreamLive] = useState(false);

  const [addStationOpen, setAddStationOpen] = useState(false);
  const [stationForm, setStationForm] = useState<{ name: string; name_ar: string }>({
    name: '',
    name_ar: '',
  });
  const [submitting, setSubmitting] = useState(false);

  // Re-render every second so the on-card timers tick.
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  // Connectivity badge (UX-02 offline state).
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const [st, tk] = await Promise.all([getPrepStations(), getKdsTickets({ status: 'active' })]);
      setStations(Array.isArray(st) ? st : []);
      setCards(Array.isArray(tk?.items) ? tk.items : []);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
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

  // Real-time channel (F-057): subscribe to the SSE stream so fired/bumped/
  // recalled cards reflect on the board within ~1s. The browser EventSource
  // auto-reconnects; a poll fallback keeps the board fresh if SSE is unavailable.
  useEffect(() => {
    if (denied) return;
    const url = kdsStreamUrl();
    if (!url || typeof EventSource === 'undefined') return;

    const es = new EventSource(url);
    const upsert = (card: KdsCard) =>
      setCards((prev) => [...prev.filter((c) => c.id !== card.id), card]);
    const remove = (card: KdsCard) =>
      setCards((prev) => prev.filter((c) => c.id !== card.id));

    es.addEventListener('open', () => setStreamLive(true));
    es.addEventListener('snapshot', (e) => {
      setStreamLive(true);
      try {
        const data = JSON.parse((e as MessageEvent).data);
        setCards(Array.isArray(data.items) ? data.items : []);
      } catch {
        /* ignore malformed frame */
      }
    });
    es.addEventListener('fired', (e) => {
      try {
        upsert(JSON.parse((e as MessageEvent).data).card);
      } catch {
        /* ignore */
      }
    });
    es.addEventListener('recalled', (e) => {
      try {
        upsert(JSON.parse((e as MessageEvent).data).card);
      } catch {
        /* ignore */
      }
    });
    es.addEventListener('bumped', (e) => {
      try {
        remove(JSON.parse((e as MessageEvent).data).card);
      } catch {
        /* ignore */
      }
    });
    es.onerror = () => setStreamLive(false);

    return () => es.close();
  }, [denied]);

  // Poll fallback: when the live stream isn't connected, refresh on a timer so
  // the board never goes stale (the SSE path makes this a no-op while connected).
  useEffect(() => {
    if (denied || streamLive) return;
    const id = setInterval(() => {
      getKdsTickets({ status: 'active' })
        .then((tk) => setCards(Array.isArray(tk?.items) ? tk.items : []))
        .catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, [denied, streamLive]);

  async function handleAddStation() {
    setSubmitting(true);
    try {
      await createPrepStation({
        name: stationForm.name,
        name_ar: stationForm.name_ar || undefined,
      });
      setAddStationOpen(false);
      setStationForm({ name: '', name_ar: '' });
      await load();
    } catch (err) {
      console.error('Failed to create prep station:', err);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleBump(card: KdsCard) {
    // Optimistic: drop it from the active board immediately, reconcile on error.
    setCards((prev) => prev.filter((c) => c.id !== card.id));
    try {
      await bumpKdsTicket(card.id);
    } catch (err) {
      console.error(t('kds_bump_error'), err);
      await load();
    }
  }

  async function handleRecall(card: KdsCard) {
    try {
      await recallKdsTicket(card.id);
      await load();
    } catch (err) {
      console.error(t('kds_recall_error'), err);
    }
  }

  async function handlePrintKot(card: KdsCard) {
    try {
      const kot = await getKdsKot(card.id);
      await printEscPos(kot.kot_base64);
    } catch (err) {
      console.error('Failed to print KOT:', err);
    }
  }

  const stationName = useCallback(
    (id?: number | null) => {
      if (id == null) return t('unrouted_station');
      const s = stations.find((st) => st.id === id);
      return s ? s.name : t('unrouted_station');
    },
    [stations, t]
  );

  // Columns: one per defined station plus an unrouted (expo) column when needed.
  const columns = useMemo(() => {
    const cols: { id: number | null; name: string }[] = stations.map((s) => ({
      id: s.id,
      name: s.name,
    }));
    if (cards.some((c) => c.station_id == null)) {
      cols.push({ id: null, name: t('unrouted_station') });
    }
    return activeStation === 'all' ? cols : cols.filter((c) => c.id === activeStation);
  }, [stations, cards, activeStation, t]);

  const visibleCards = useMemo(
    () => (activeStation === 'all' ? cards : cards.filter((c) => c.station_id === activeStation)),
    [cards, activeStation]
  );

  // All-day count (F-055/F-057): total outstanding fired item quantity on the board.
  const allDayQty = useMemo(
    () =>
      visibleCards.reduce(
        (sum, c) => sum + c.items.reduce((s, it) => s + (it.qty || 0), 0),
        0
      ),
    [visibleCards]
  );

  // ---- Loading state ----
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-white animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  // ---- Permission-denied state (restaurant mode off / retail business_type) ----
  if (denied) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="bg-slate-800 border-slate-700 max-w-md">
          <CardContent className="p-8 text-center">
            <Lock className="h-12 w-12 text-slate-500 mx-auto mb-3" />
            <h3 className="text-white font-semibold mb-2">{t('restaurant_disabled')}</h3>
            <p className="text-slate-400 text-sm">{t('restaurant_disabled_desc')}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ---- Error state (distinct from empty) ----
  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="bg-slate-800 border-slate-700 max-w-md">
          <CardContent className="p-8 text-center">
            <AlertTriangle className="h-12 w-12 text-red-400 mx-auto mb-3" />
            <p className="text-slate-300 mb-4">{t('kds_load_error')}</p>
            <Button onClick={load} className="bg-blue-600 hover:bg-blue-700 text-white">
              {t('retry')}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Offline banner (UX-02) */}
      {!online && (
        <div className="flex items-center gap-2 rounded-md border border-amber-600/40 bg-amber-500/10 px-4 py-2 text-amber-300 text-sm">
          <WifiOff className="h-4 w-4" />
          <span>{t('you_are_offline')}</span>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <ChefHat className="h-6 w-6 text-blue-400" />
            {t('kds')}
          </h2>
          <p className="text-slate-400 text-sm mt-1">{t('kds_desc')}</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Live/reconnecting indicator for the real-time channel */}
          <Badge
            className={
              streamLive
                ? 'bg-green-500/20 text-green-400 gap-1'
                : 'bg-amber-500/20 text-amber-400 gap-1'
            }
          >
            <Radio className="h-3 w-3" />
            {streamLive ? t('kds_live') : t('kds_reconnecting')}
          </Badge>
          <Badge className="bg-slate-700 text-slate-200 gap-1">
            <ChefHat className="h-3 w-3" /> {allDayQty}
          </Badge>
          <Dialog open={addStationOpen} onOpenChange={setAddStationOpen}>
            <DialogTrigger asChild>
              <Button className="bg-blue-600 hover:bg-blue-700 text-white">
                <Plus className="h-4 w-4 mr-2" /> {t('add_station')}
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-slate-800 border-slate-700 text-white">
              <DialogHeader>
                <DialogTitle className="text-white">{t('add_station')}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-slate-400 mb-1 block">{t('station_name')}</label>
                  <Input
                    value={stationForm.name}
                    onChange={(e) => setStationForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="Grill"
                    className="bg-slate-700 border-slate-600 text-white"
                  />
                </div>
                <div>
                  <label className="text-sm text-slate-400 mb-1 block">
                    {t('station_name_ar')}
                  </label>
                  <Input
                    value={stationForm.name_ar}
                    onChange={(e) => setStationForm((f) => ({ ...f, name_ar: e.target.value }))}
                    dir="rtl"
                    placeholder="الشواية"
                    className="bg-slate-700 border-slate-600 text-white"
                  />
                </div>
                <Button
                  onClick={handleAddStation}
                  disabled={submitting || !stationForm.name}
                  className="w-full bg-blue-600 hover:bg-blue-700 text-white"
                >
                  {submitting ? t('loading') : t('create_station')}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Station filter tabs */}
      {stations.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setActiveStation('all')}
            className={`px-3 py-1 rounded-md text-sm ${activeStation === 'all' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'}`}
          >
            {t('all_stations')}
          </button>
          {stations.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveStation(s.id)}
              className={`px-3 py-1 rounded-md text-sm ${activeStation === s.id ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'}`}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}

      {/* No prep-stations yet */}
      {stations.length === 0 ? (
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-10 text-center">
            <ChefHat className="h-12 w-12 text-slate-600 mx-auto mb-3" />
            <h3 className="text-white font-semibold mb-1">{t('no_stations')}</h3>
            <p className="text-slate-400 text-sm">{t('no_stations_desc')}</p>
          </CardContent>
        </Card>
      ) : visibleCards.length === 0 ? (
        /* Empty board (stations exist, nothing fired) */
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="p-10 text-center">
            <ChefHat className="h-12 w-12 text-slate-600 mx-auto mb-3" />
            <h3 className="text-white font-semibold mb-1">{t('no_kds_tickets')}</h3>
            <p className="text-slate-400 text-sm">{t('no_kds_tickets_desc')}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {columns.map((col) => {
            const colCards = visibleCards.filter((c) => c.station_id === col.id);
            return (
              <div key={col.id ?? 'unrouted'} className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-white font-semibold">{col.name}</h3>
                  <Badge className="bg-slate-700 text-slate-300">{colCards.length}</Badge>
                </div>
                {colCards.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-slate-700 p-4 text-center text-slate-500 text-xs">
                    {t('no_kds_tickets')}
                  </div>
                ) : (
                  colCards.map((card) => {
                    const late = isLate(card.fired_at, now);
                    return (
                      <Card
                        key={card.id}
                        className={`border ${late ? 'border-red-600/50 bg-red-500/5' : 'border-slate-700 bg-slate-800'}`}
                      >
                        <CardContent className="p-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-white text-sm font-semibold">
                              {t('kds_order')} #{card.order_ticket_id}
                              {card.table_id ? ` · ${t('kds_table')} ${card.table_id}` : ''}
                            </span>
                            <span
                              className={`flex items-center gap-1 text-xs ${late ? 'text-red-400' : 'text-slate-400'}`}
                            >
                              <Clock className="h-3 w-3" />
                              {elapsedLabel(card.fired_at, now)}
                            </span>
                          </div>
                          {card.course && (
                            <Badge className="bg-blue-500/20 text-blue-300">{card.course}</Badge>
                          )}
                          <ul className="space-y-1">
                            {card.items.map((it) => (
                              <li key={it.item_id} className="text-sm text-slate-200">
                                <span className="text-white font-medium">{it.qty}×</span> {it.name}
                                {it.modifiers?.length > 0 && (
                                  <div className="text-xs text-amber-300 ms-4">
                                    {it.modifiers.map((m) => `+ ${m}`).join('  ')}
                                  </div>
                                )}
                                {it.notes && (
                                  <div className="text-xs text-slate-400 ms-4">» {it.notes}</div>
                                )}
                              </li>
                            ))}
                          </ul>
                          <div className="flex gap-2 pt-1">
                            <Button
                              size="sm"
                              onClick={() => handleBump(card)}
                              className="flex-1 bg-green-600 hover:bg-green-700 text-white"
                            >
                              <Check className="h-4 w-4 mr-1" /> {t('bump')}
                            </Button>
                            {isThermalPrintSupported() && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handlePrintKot(card)}
                                className="border-slate-600 text-slate-300 hover:bg-slate-700"
                                title={t('print_kot')}
                              >
                                <Printer className="h-4 w-4" />
                              </Button>
                            )}
                            {card.status === 'bumped' && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleRecall(card)}
                                className="border-slate-600 text-slate-300 hover:bg-slate-700"
                                title={t('recall')}
                              >
                                <RotateCcw className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
