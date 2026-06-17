import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import PageHeading from '@/components/dashboard/rx/PageHeading';
import {
  issueGiftCard,
  listGiftCards,
  reloadGiftCard,
  voidGiftCard,
  type GiftCard,
} from '@/lib/api';
import { useLanguage } from '@/lib/i18n';
import { formatMoney } from '@/lib/format';
import { Gift, Plus, RefreshCw } from 'lucide-react';

// Gift-card status → pill styling. A card walks active → redeemed / expired / void.
const STATUS_PILL: Record<string, string> = {
  active: 'pill-success',
  redeemed: 'pill-muted',
  expired: 'pill-warning',
  void: 'pill-danger',
};

export default function GiftCardManagement() {
  const { t, language } = useLanguage();

  const PAGE_SIZE = 50;
  const [cards, setCards] = useState<GiftCard[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);

  const [amount, setAmount] = useState('');
  const [expiry, setExpiry] = useState('');
  const [issuing, setIssuing] = useState(false);
  const [issueMsg, setIssueMsg] = useState<string | null>(null);

  // Per-row management state (ISSUE-057): which card is reloading + its top-up amount.
  const [busyId, setBusyId] = useState<number | null>(null);
  const [reloadId, setReloadId] = useState<number | null>(null);
  const [reloadAmount, setReloadAmount] = useState('');
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  function patchCard(updated: GiftCard) {
    setCards((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
  }

  async function handleVoid(id: number) {
    setBusyId(id);
    setActionMsg(null);
    try {
      patchCard(await voidGiftCard(id));
      setActionMsg(t('gift_card_voided'));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setActionMsg(detail || t('gift_card_action_failed'));
    } finally {
      setBusyId(null);
    }
  }

  async function handleReload(id: number) {
    const value = Number(reloadAmount);
    if (!value || value <= 0) return;
    setBusyId(id);
    setActionMsg(null);
    try {
      patchCard(await reloadGiftCard(id, value));
      setActionMsg(t('gift_card_reloaded'));
      setReloadId(null);
      setReloadAmount('');
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setActionMsg(detail || t('gift_card_action_failed'));
    } finally {
      setBusyId(null);
    }
  }

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    setDenied(false);
    try {
      const { items, total: count } = await listGiftCards(0, PAGE_SIZE);
      setCards(items);
      setTotal(count);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      // 403 means the account is not a client tenancy (gift cards are client-scoped).
      if (status === 403) {
        setDenied(true);
      } else {
        // A real fetch failure must not masquerade as "no cards" (UX-02).
        setError(true);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // OPS-05: the list is server-side paginated; fetch the next page and append.
  async function loadMore() {
    setLoadingMore(true);
    try {
      const { items, total: count } = await listGiftCards(cards.length, PAGE_SIZE);
      setCards((prev) => [...prev, ...items]);
      setTotal(count);
    } catch {
      // Keep the rows already shown; a transient failure must not blank the list.
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleIssue() {
    const value = Number(amount);
    if (!value || value <= 0) return;
    setIssuing(true);
    setIssueMsg(null);
    try {
      const card = await issueGiftCard({
        amount: value,
        expiry_date: expiry ? new Date(expiry).toISOString() : undefined,
      });
      setIssueMsg(`${t('gift_card_issued')}: ${card.code}`);
      setAmount('');
      setExpiry('');
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setIssueMsg(detail || t('gift_card_issue_failed'));
    } finally {
      setIssuing(false);
    }
  }

  // ---- Loading state ----
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-foreground animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  // ---- Permission-denied state (not a client tenancy) ----
  if (denied) {
    return <PermissionDenied />;
  }

  // ---- Error state (distinct from empty) ----
  if (error) {
    return <ErrorState message={t('gift_cards_load_error')} onRetry={load} />;
  }

  return (
    <div className="animate-fade-up space-y-6">
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-10 w-10"><Gift className="h-[18px] w-[18px]" /></span>}
        title={t('gift_cards')}
        subtitle={t('gift_cards_desc')}
      >
        <Button
          variant="outline"
          onClick={load}
          className="h-11 rounded-[10px]"
        >
          <RefreshCw className="h-4 w-4 me-2" /> {t('refresh')}
        </Button>
      </PageHeading>

      {actionMsg && (
        <p className="text-sm text-foreground/90" role="status">
          {actionMsg}
        </p>
      )}

      {/* Issue a new card (CRM-03) */}
      <Card className="bg-card border-border">
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2 text-foreground font-semibold">
            <Plus className="h-5 w-5 text-brand" />
            {t('issue_gift_card')}
          </div>
          <p className="text-muted-foreground text-sm">{t('issue_gift_card_hint')}</p>
          <div className="flex flex-col sm:flex-row gap-2">
            <Input
              dir="ltr"
              type="number"
              min="0"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder={t('gift_card_amount')}
            />
            <Input
              dir="ltr"
              type="date"
              value={expiry}
              onChange={(e) => setExpiry(e.target.value)}
              placeholder={t('gift_card_expiry')}
            />
            <Button
              onClick={handleIssue}
              disabled={issuing || !(Number(amount) > 0)}
              className="shrink-0"
            >
              {issuing ? t('loading') : t('issue')}
            </Button>
          </div>
          {issueMsg && (
            <p className="text-sm text-foreground/90" role="status">
              {issueMsg}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Issued cards: empty state vs table */}
      {cards.length === 0 ? (
        <Card className="bg-card border-border">
          <CardContent className="p-10 text-center">
            <Gift className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <h3 className="text-foreground font-semibold mb-1">{t('no_gift_cards')}</h3>
            <p className="text-muted-foreground text-sm">{t('no_gift_cards_desc')}</p>
          </CardContent>
        </Card>
      ) : (
        <Card className="bg-card border-border">
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="text-start p-3">{t('gift_card_code')}</th>
                  <th className="text-start p-3">{t('gift_card_balance')}</th>
                  <th className="text-start p-3">{t('gift_card_initial')}</th>
                  <th className="text-start p-3">{t('status')}</th>
                  <th className="text-start p-3">{t('gift_card_expiry')}</th>
                  <th className="text-start p-3">{t('date')}</th>
                  <th className="text-end p-3">{t('gift_card_actions')}</th>
                </tr>
              </thead>
              <tbody>
                {cards.map((c) => (
                  <tr key={c.id} className="border-b border-border/50">
                    <td className="p-3 text-foreground font-mono" dir="ltr">{c.code}</td>
                    <td className="p-3 text-foreground/90 tabular-nums">
                      {formatMoney(c.balance, language)}
                    </td>
                    <td className="p-3 text-muted-foreground tabular-nums">{formatMoney(c.initial_balance, language)}</td>
                    <td className="p-3">
                      <span className={STATUS_PILL[c.status] || 'pill-muted'}>
                        {t(`gift_card_status_${c.status}`)}
                      </span>
                    </td>
                    <td className="p-3 text-muted-foreground">
                      {c.expiry_date ? new Date(c.expiry_date).toLocaleDateString() : '—'}
                    </td>
                    <td className="p-3 text-muted-foreground">
                      {c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="p-3">
                      {c.status === 'void' ? (
                        <span className="text-muted-foreground text-xs">—</span>
                      ) : reloadId === c.id ? (
                        <div className="flex items-center justify-end gap-2">
                          <Input
                            dir="ltr"
                            type="number"
                            min="0"
                            step="0.01"
                            value={reloadAmount}
                            onChange={(e) => setReloadAmount(e.target.value)}
                            placeholder={t('gift_card_reload_amount')}
                            className="h-8 w-32"
                          />
                          <Button
                            size="sm"
                            onClick={() => handleReload(c.id)}
                            disabled={busyId === c.id || !(Number(reloadAmount) > 0)}
                          >
                            {t('gift_card_reload')}
                          </Button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setReloadId(c.id);
                              setReloadAmount('');
                            }}
                            disabled={busyId === c.id}
                          >
                            {t('gift_card_reload')}
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => handleVoid(c.id)}
                            disabled={busyId === c.id}
                          >
                            {t('gift_card_void')}
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {cards.length < total && (
              <div className="flex justify-center pt-4">
                <Button
                  variant="outline"
                  onClick={loadMore}
                  disabled={loadingMore}
                >
                  {loadingMore ? t('loading') : `${t('load_more')} (${cards.length}/${total})`}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
