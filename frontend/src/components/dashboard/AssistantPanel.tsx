import { useState, useCallback, type FormEvent } from 'react';
import { Sparkles } from 'lucide-react';
import { useLanguage, translate } from '@/lib/i18n';
import { askAssistant, type AssistantAnswer } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

/**
 * In-app Assistant (#228, M9·AI) — the operator-facing surface over the
 * rule-based /assistant/query endpoint. A merchant types a plain-language
 * question about their own store ("what is my best seller?"); the panel routes
 * it server-side to a grounded, self-describing answer and renders it, alongside
 * one-tap suggestion chips seeded by the backend.
 *
 * The panel owns its own load/error state so a failed request surfaces a real
 * retry error (UX-02) rather than a silent no-op, mirroring ForecastInsights.
 * The first slice is deterministic and rule-based; the same surface will front
 * an LLM-backed engine later without changing this component's contract.
 */
export default function AssistantPanel() {
  const { language } = useLanguage();
  const tr = useCallback((key: string): string => translate(language, key), [language]);

  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<AssistantAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  // Suggestions come from whatever answer last returned; before the first ask we
  // seed the same three intents the backend routes so the panel is usable cold.
  const suggestions = answer?.suggestions ?? DEFAULT_SUGGESTIONS;

  const ask = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return; // the endpoint requires min_length=1 — never send blank.
    setLoading(true);
    setError(false);
    try {
      const result = await askAssistant(trimmed);
      setAnswer(result || null);
    } catch {
      setError(true);
      setAnswer(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void ask(question);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-brand-600" aria-hidden="true" />
          {tr('assistant')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={onSubmit} className="flex flex-wrap gap-2">
          <Input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={tr('assistant_placeholder')}
            aria-label={tr('assistant')}
            className="min-w-0 flex-1"
          />
          <Button type="submit" disabled={loading}>
            {loading ? tr('assistant_thinking') : tr('assistant_ask')}
          </Button>
        </form>

        {/* Grounded answer (or its loading/error/intro states). */}
        {error ? (
          <p className="text-sm text-danger">{tr('error_loading')}</p>
        ) : answer ? (
          <p className="text-sm text-foreground" role="status">
            {answer.answer}
          </p>
        ) : (
          !loading && <p className="text-sm text-muted-foreground">{tr('assistant_intro')}</p>
        )}

        {/* One-tap suggestion chips seeded by the backend's capability list. */}
        <div className="flex flex-wrap gap-2" aria-label={tr('assistant_try_asking')}>
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setQuestion(s);
                void ask(s);
              }}
              className="rounded-full border border-border bg-muted/50 px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted"
            >
              {s}
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// The backend seeds the same capabilities; mirror them so the chips render
// before the first request completes. Once an answer returns, its own
// ``suggestions`` (authoritative) replace these.
const DEFAULT_SUGGESTIONS = [
  'What is my best selling product?',
  'How much did I sell today?',
  'What is my average order value?',
  'What is my sales forecast for next week?',
  'Is business up or down this week?',
  'When are we busiest?',
  'What should I reorder?',
  'Which products will run out soon?',
  'Which products should I discount?',
  "Which products aren't selling?",
  'Which products are low on stock?',
];
