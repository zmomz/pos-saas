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
import PageHeading from '@/components/dashboard/rx/PageHeading';
import {
  ChefHat,
  Plus,
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
  // Which board the kitchen is looking at: the live line ('active') or the
  // recently-bumped cards ('bumped') it can recall back (ISSUE-073).
  const [boardStatus, setBoardStatus] = useState<'active' | 'bumped'>('active');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);
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

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const [st, tk] = await Promise.all([
        getPrepStations(),
        getKdsTickets({ status: boardStatus }),
      ]);
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
  }, [boardStatus]);

  useEffect(() => {
    load();
  }, [load]);

  // Real-time channel (F-057): subscribe to the SSE stream so fired/bumped/
  // recalled cards reflect on the board within ~1s. The browser EventSource
  // auto-reconnects; a poll fallback keeps the board fresh if SSE is unavailable.
  useEffect(() => {
    // The live channel only feeds the active line; the bumped (completed) board
    // is read on demand via load/poll, so don't subscribe while viewing it.
    if (denied || boardStatus !== 'active') {
      setStreamLive(false);
      return;
    }
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
  }, [denied, boardStatus]);

  // Poll fallback: when the live stream isn't connected, refresh on a timer so
  // the board never goes stale (the SSE path makes this a no-op while connected).
  useEffect(() => {
    if (denied || streamLive) return;
    const id = setInterval(() => {
      getKdsTickets({ status: boardStatus })
        .then((tk) => setCards(Array.isArray(tk?.items) ? tk.items : []))
        .catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, [denied, streamLive, boardStatus]);

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
        <div className="text-foreground animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  // ---- Permission-denied state (restaurant mode off / retail business_type) ----
  if (denied) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="bg-card border-border max-w-md">
          <CardContent className="p-8 text-center">
            <Lock className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <h3 className="text-foreground font-semibold mb-2">{t('restaurant_disabled')}</h3>
            <p className="text-muted-foreground text-sm">{t('restaurant_disabled_desc')}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ---- Error state (distinct from empty) ----
  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <Card className="bg-card border-border max-w-md">
          <CardContent className="p-8 text-center">
            <AlertTriangle className="h-12 w-12 text-danger mx-auto mb-3" />
            <p className="text-foreground/90 mb-4">{t('kds_load_error')}</p>
            <Button onClick={load}>
              {t('retry')}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-6">
      {/* Header */}
      <PageHeading
        title={t('kds')}
        subtitle={t('kds_desc')}
        icon={
          <span className="dxr-sw dxr-sw-brand h-10 w-10">
            <ChefHat className="h-[18px] w-[18px]" />
          </span>
        }
      >
        <div className="flex items-center gap-2">
          {/* Live/reconnecting indicator for the real-time channel */}
          <Badge className={streamLive ? 'pill-success gap-1' : 'pill-warning gap-1'}>
            <Radio className="h-3 w-3" />
            {streamLive ? t('kds_live') : t('kds_reconnecting')}
          </Badge>
          <Badge className="bg-muted text-foreground gap-1">
            <ChefHat className="h-3 w-3" /> {allDayQty}
          </Badge>
          <Dialog open={addStationOpen} onOpenChange={setAddStationOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" /> {t('add_station')}
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-card border-border text-foreground">
              <DialogHeader>
                <DialogTitle className="text-foreground">{t('add_station')}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-muted-foreground mb-1 block">{t('station_name')}</label>
                  <Input
                    value={stationForm.name}
                    onChange={(e) => setStationForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="Grill"
                    className="bg-muted border-input text-foreground"
                  />
                </div>
                <div>
                  <label className="text-sm text-muted-foreground mb-1 block">
                    {t('station_name_ar')}
                  </label>
                  <Input
                    value={stationForm.name_ar}
                    onChange={(e) => setStationForm((f) => ({ ...f, name_ar: e.target.value }))}
                    dir="rtl"
                    placeholder="الشواية"
                    className="bg-muted border-input text-foreground"
                  />
                </div>
                <Button
                  onClick={handleAddStation}
                  disabled={submitting || !stationForm.name}
                  className="w-full"
                >
                  {submitting ? t('loading') : t('create_station')}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </PageHeading>

      {/* Board view: live line vs. recently-bumped cards to recall (ISSUE-073) */}
      <div className="dxr-seg">
        <button onClick={() => setBoardStatus('active')} data-active={boardStatus === 'active'}>
          {t('kds_active')}
        </button>
        <button onClick={() => setBoardStatus('bumped')} data-active={boardStatus === 'bumped'}>
          {t('kds_completed')}
        </button>
      </div>

      {/* Station filter tabs */}
      {stations.length > 0 && (
        <div className="dxr-seg flex-wrap">
          <button onClick={() => setActiveStation('all')} data-active={activeStation === 'all'}>
            {t('all_stations')}
          </button>
          {stations.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveStation(s.id)}
              data-active={activeStation === s.id}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}

      {/* No prep-stations yet */}
      {stations.length === 0 ? (
        <Card className="bg-card border-border">
          <CardContent className="p-10 text-center">
            <ChefHat className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <h3 className="text-foreground font-semibold mb-1">{t('no_stations')}</h3>
            <p className="text-muted-foreground text-sm">{t('no_stations_desc')}</p>
          </CardContent>
        </Card>
      ) : visibleCards.length === 0 ? (
        /* Empty board (stations exist, nothing fired / nothing bumped) */
        <Card className="bg-card border-border">
          <CardContent className="p-10 text-center">
            <ChefHat className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <h3 className="text-foreground font-semibold mb-1">
              {boardStatus === 'bumped' ? t('no_bumped_tickets') : t('no_kds_tickets')}
            </h3>
            <p className="text-muted-foreground text-sm">
              {boardStatus === 'bumped' ? t('no_bumped_tickets_desc') : t('no_kds_tickets_desc')}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {columns.map((col) => {
            const colCards = visibleCards.filter((c) => c.station_id === col.id);
            return (
              <div key={col.id ?? 'unrouted'} className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-foreground font-semibold">{col.name}</h3>
                  <Badge className="bg-muted text-foreground/90">{colCards.length}</Badge>
                </div>
                {colCards.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border p-4 text-center text-muted-foreground text-xs">
                    {t('no_kds_tickets')}
                  </div>
                ) : (
                  colCards.map((card) => {
                    const late = isLate(card.fired_at, now);
                    return (
                      <Card
                        key={card.id}
                        className={`border ${late ? 'border-danger/50 bg-danger/5' : 'border-border bg-card'}`}
                      >
                        <CardContent className="p-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-foreground text-sm font-semibold">
                              {t('kds_order')} #{card.order_ticket_id}
                              {card.table_id ? ` · ${t('kds_table')} ${card.table_id}` : ''}
                            </span>
                            <span
                              className={`flex items-center gap-1 text-xs ${late ? 'text-danger' : 'text-muted-foreground'}`}
                            >
                              <Clock className="h-3 w-3" />
                              {elapsedLabel(card.fired_at, now)}
                            </span>
                          </div>
                          {card.course && (
                            <Badge className="bg-brand-500/20 text-brand-600">{card.course}</Badge>
                          )}
                          <ul className="space-y-1">
                            {card.items.map((it) => (
                              <li key={it.item_id} className="text-sm text-foreground">
                                <span className="text-foreground font-medium">{it.qty}×</span> {it.name}
                                {it.modifiers?.length > 0 && (
                                  <div className="text-xs text-warning ms-4">
                                    {it.modifiers.map((m) => `+ ${m}`).join('  ')}
                                  </div>
                                )}
                                {it.notes && (
                                  <div className="text-xs text-muted-foreground ms-4">» {it.notes}</div>
                                )}
                              </li>
                            ))}
                          </ul>
                          <div className="flex gap-2 pt-1">
                            {card.status !== 'bumped' && (
                              <Button
                                size="sm"
                                onClick={() => handleBump(card)}
                                className="flex-1 bg-success hover:opacity-90 text-white"
                              >
                                <Check className="h-4 w-4 mr-1" /> {t('bump')}
                              </Button>
                            )}
                            {isThermalPrintSupported() && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handlePrintKot(card)}
                                className="border-input text-foreground/90 hover:bg-muted"
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
                                className="flex-1 border-input text-foreground/90 hover:bg-muted"
                                title={t('recall')}
                              >
                                <RotateCcw className="h-4 w-4 mr-1" /> {t('recall')}
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
