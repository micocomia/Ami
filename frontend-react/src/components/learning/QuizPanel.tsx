import { useState, useCallback } from 'react';
import { Button } from '@/components/ui';
import { cn } from '@/lib/cn';
import { apiClient } from '@/api/client';
import type { DocumentQuiz, MasteryEvaluationResponse } from '@/types';

interface QuizPanelProps {
  quiz: DocumentQuiz;
  userId: string;
  goalId: number;
  sessionIndex: number;
  onMasteryResult: (result: MasteryEvaluationResponse) => void;
  ensureCached?: () => Promise<void>;
  onCompleteSession?: () => void;
  completeSessionLoading?: boolean;
  completeSessionDisabled?: boolean;
  completeSessionHint?: string | null;
}

export function QuizPanel({
  quiz,
  userId,
  goalId,
  sessionIndex,
  onMasteryResult,
  ensureCached,
  onCompleteSession,
  completeSessionLoading = false,
  completeSessionDisabled = true,
  completeSessionHint = null,
}: QuizPanelProps) {
  const scQs = quiz.single_choice_questions ?? [];
  const mcQs = quiz.multiple_choice_questions ?? [];
  const tfQs = quiz.true_false_questions ?? [];
  const saQs = quiz.short_answer_questions ?? [];
  const oeQs = quiz.open_ended_questions ?? [];
  const totalQuestions = scQs.length + mcQs.length + tfQs.length + saQs.length + oeQs.length;

  const [scAnswers, setScAnswers] = useState<(number | null)[]>(() => scQs.map(() => null));
  const [mcAnswers, setMcAnswers] = useState<Set<number>[]>(() => mcQs.map(() => new Set()));
  const [tfAnswers, setTfAnswers] = useState<(boolean | null)[]>(() => tfQs.map(() => null));
  const [saAnswers, setSaAnswers] = useState<string[]>(() => saQs.map(() => ''));
  const [oeAnswers, setOeAnswers] = useState<string[]>(() => oeQs.map(() => ''));

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<MasteryEvaluationResponse | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showExplanations, setShowExplanations] = useState(false);

  const handleSubmit = useCallback(async () => {
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      if (ensureCached) await ensureCached();

      const payload = {
        user_id: userId,
        goal_id: goalId,
        session_index: sessionIndex,
        quiz_answers: {
          single_choice_questions: scAnswers.map((a, i) =>
            a != null ? quizOptions(scQs[i])[a] ?? null : null,
          ),
          multiple_choice_questions: mcAnswers.map((s, i) =>
            Array.from(s).map((idx) => quizOptions(mcQs[i])[idx]).filter(Boolean),
          ),
          true_false_questions: tfAnswers.map((a) =>
            a == null ? null : a ? 'True' : 'False',
          ),
          short_answer_questions: saAnswers.map((a) => a || null),
          open_ended_questions: oeAnswers.map((a) => a || null),
        },
      };
      const { data } = await apiClient.post<MasteryEvaluationResponse>('evaluate-mastery', payload);
      setResult(data);
      onMasteryResult(data);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Failed to submit quiz. Please try again.';
      setSubmitError(msg);
    } finally {
      setIsSubmitting(false);
    }
  }, [userId, goalId, sessionIndex, ensureCached, scQs, mcQs, scAnswers, mcAnswers, tfAnswers, saAnswers, oeAnswers, onMasteryResult]);

  const handleRetake = useCallback(() => {
    setScAnswers(scQs.map(() => null));
    setMcAnswers(mcQs.map(() => new Set()));
    setTfAnswers(tfQs.map(() => null));
    setSaAnswers(saQs.map(() => ''));
    setOeAnswers(oeQs.map(() => ''));
    setResult(null);
    setSubmitError(null);
    setShowExplanations(false);
  }, [scQs, mcQs, tfQs, saQs, oeQs]);

  if (totalQuestions === 0) return null;

  const quizExplanationText = (q: unknown): string | null => {
    const e = (q as { explanation?: unknown })?.explanation;
    if (typeof e === 'string' && e.trim()) return e;
    return null;
  };
  const quizOptions = (q: { options?: unknown }): string[] =>
    Array.isArray(q.options)
      ? (q.options as unknown[]).filter((x): x is string => typeof x === 'string')
      : [];

  const soloColors: Record<string, string> = {
    Prestructural: 'text-red-600',
    Unistructural: 'text-orange-600',
    Multistructural: 'text-yellow-600',
    Relational: 'text-blue-600',
    'Extended Abstract': 'text-green-600',
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-slate-800 text-lg">Knowledge Check</h3>
        <span className="text-xs text-slate-400">
          {totalQuestions} question{totalQuestions !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Single choice */}
      {scQs.map((q, qi) => (
        <div key={`sc-${qi}`} className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
          <p className="font-medium text-slate-800 text-sm">
            {qi + 1}. {q.question}
          </p>
          <div className="space-y-2">
            {quizOptions(q).map((opt, oi) => {
              const opts = quizOptions(q);
              const isSelected = scAnswers[qi] === oi;
              const correctIdx = typeof q.correct_option === 'number'
                ? q.correct_option
                : opts.indexOf(q.correct_option as string);
              const isCorrect = result != null && correctIdx === oi;
              const isWrong = result != null && isSelected && correctIdx !== oi;
              return (
                <button
                  key={oi}
                  type="button"
                  disabled={!!result}
                  onClick={() => setScAnswers((prev) => prev.map((a, i) => (i === qi ? oi : a)))}
                  className={cn(
                    'w-full text-left px-4 py-2.5 rounded-lg border text-sm transition-all',
                    result
                      ? isCorrect
                        ? 'border-green-400 bg-green-50 text-green-800'
                        : isWrong
                        ? 'border-red-400 bg-red-50 text-red-800'
                        : 'border-slate-200 text-slate-400'
                      : isSelected
                      ? 'border-primary-500 bg-primary-50 text-primary-800'
                      : 'border-slate-200 hover:border-slate-300 text-slate-700',
                  )}
                >
                  {opt}
                </button>
              );
            })}
          </div>
          {result && showExplanations && quizExplanationText(q) && (
            <p className="text-xs text-slate-500 italic">{quizExplanationText(q)}</p>
          )}
        </div>
      ))}

      {/* Multiple choice */}
      {mcQs.map((q, qi) => (
        <div key={`mc-${qi}`} className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
          <p className="font-medium text-slate-800 text-sm">
            {scQs.length + qi + 1}. {q.question}{' '}
            <span className="text-xs text-slate-400 font-normal">(select all that apply)</span>
          </p>
          <div className="space-y-2">
            {quizOptions(q).map((opt, oi) => {
              const opts = quizOptions(q);
              const isSelected = mcAnswers[qi].has(oi);
              const rawCorrect = (q as { correct_options?: unknown; correct_answers?: unknown })
                .correct_options ??
                (q as { correct_answers?: unknown }).correct_answers ??
                [];
              const rawList: (string | number)[] = Array.isArray(rawCorrect)
                ? (rawCorrect as (string | number)[])
                : [];
              const correctIndices = new Set(
                rawList.map((c) => (typeof c === 'number' ? c : opts.indexOf(String(c)))),
              );
              const isCorrect = result != null && correctIndices.has(oi);
              const isWrong = result != null && isSelected && !correctIndices.has(oi);
              return (
                <button
                  key={oi}
                  type="button"
                  disabled={!!result}
                  onClick={() =>
                    setMcAnswers((prev) =>
                      prev.map((s, i) => {
                        if (i !== qi) return s;
                        const ns = new Set(s);
                        if (ns.has(oi)) ns.delete(oi);
                        else ns.add(oi);
                        return ns;
                      }),
                    )
                  }
                  className={cn(
                    'w-full text-left px-4 py-2.5 rounded-lg border text-sm transition-all flex items-center gap-2',
                    result
                      ? isCorrect
                        ? 'border-green-400 bg-green-50 text-green-800'
                        : isWrong
                        ? 'border-red-400 bg-red-50 text-red-800'
                        : 'border-slate-200 text-slate-400'
                      : isSelected
                      ? 'border-primary-500 bg-primary-50 text-primary-800'
                      : 'border-slate-200 hover:border-slate-300 text-slate-700',
                  )}
                >
                  <span
                    className={cn(
                      'w-4 h-4 rounded border-2 flex items-center justify-center shrink-0',
                      isSelected ? 'bg-primary-500 border-primary-500' : 'border-slate-300',
                    )}
                  >
                    {isSelected && (
                      <svg
                        className="w-2.5 h-2.5 text-white"
                        fill="none"
                        viewBox="0 0 10 10"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <path d="M2 5l2.5 2.5L8 3" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </span>
                  {opt}
                </button>
              );
            })}
          </div>
          {result && showExplanations && quizExplanationText(q) && (
            <p className="text-xs text-slate-500 italic">{quizExplanationText(q)}</p>
          )}
        </div>
      ))}

      {/* True/False */}
      {tfQs.map((q, qi) => (
        <div key={`tf-${qi}`} className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
          <p className="font-medium text-slate-800 text-sm">
            {scQs.length + mcQs.length + qi + 1}. {q.question}
          </p>
          <div className="flex gap-3">
            {([true, false] as const).map((val) => {
              const isSelected = tfAnswers[qi] === val;
              const isCorrect = result != null && q.correct_answer === val;
              const isWrong = result != null && isSelected && q.correct_answer !== val;
              return (
                <button
                  key={String(val)}
                  type="button"
                  disabled={!!result}
                  onClick={() => setTfAnswers((prev) => prev.map((a, i) => (i === qi ? val : a)))}
                  className={cn(
                    'flex-1 py-2.5 rounded-lg border text-sm font-medium transition-all',
                    result
                      ? isCorrect
                        ? 'border-green-400 bg-green-50 text-green-800'
                        : isWrong
                        ? 'border-red-400 bg-red-50 text-red-800'
                        : 'border-slate-200 text-slate-400'
                      : isSelected
                      ? 'border-primary-500 bg-primary-50 text-primary-800'
                      : 'border-slate-200 hover:border-slate-300 text-slate-700',
                  )}
                >
                  {val ? 'True' : 'False'}
                </button>
              );
            })}
          </div>
          {result && showExplanations && quizExplanationText(q) && (
            <p className="text-xs text-slate-500 italic">{quizExplanationText(q)}</p>
          )}
        </div>
      ))}

      {/* Short answer */}
      {saQs.map((q, qi) => {
        const feedback = result?.short_answer_feedback?.[qi];
        return (
          <div key={`sa-${qi}`} className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
            <p className="font-medium text-slate-800 text-sm">
              {scQs.length + mcQs.length + tfQs.length + qi + 1}. {q.question}
            </p>
            <input
              type="text"
              disabled={!!result}
              value={saAnswers[qi]}
              onChange={(e) => setSaAnswers((prev) => prev.map((a, i) => (i === qi ? e.target.value : a)))}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-400 disabled:bg-slate-50 disabled:text-slate-500"
              placeholder="Your answer…"
            />
            {feedback && (
              <p className={cn('text-xs', feedback.is_correct ? 'text-green-600' : 'text-red-600')}>
                {feedback.feedback}
              </p>
            )}
          </div>
        );
      })}

      {/* Open-ended */}
      {oeQs.map((q, qi) => {
        const feedback = result?.open_ended_feedback?.[qi];
        const soloColor = feedback ? soloColors[feedback.solo_level] ?? 'text-slate-600' : '';
        return (
          <div key={`oe-${qi}`} className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
            <p className="font-medium text-slate-800 text-sm">
              {scQs.length + mcQs.length + tfQs.length + saQs.length + qi + 1}. {q.question}
            </p>
            <textarea
              disabled={!!result}
              value={oeAnswers[qi]}
              onChange={(e) => setOeAnswers((prev) => prev.map((a, i) => (i === qi ? e.target.value : a)))}
              rows={4}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-400 disabled:bg-slate-50 disabled:text-slate-500 resize-none"
              placeholder="Your answer…"
            />
            {feedback && (
              <div className="space-y-0.5">
                <p className={cn('text-xs font-medium', soloColor)}>
                  SOLO Level: {feedback.solo_level} ({Math.round(feedback.score * 100)}%)
                </p>
                <p className="text-xs text-slate-500">{feedback.feedback}</p>
              </div>
            )}
          </div>
        );
      })}

      {/* Result banner */}
      {result && (
        <div
          className={cn(
            'rounded-xl border px-5 py-4 space-y-3',
            result.is_mastered ? 'bg-green-50 border-green-300' : 'bg-amber-50 border-amber-300',
          )}
        >
          <p className="font-semibold text-slate-800">
            Score: {result.correct_count}/{result.total_count} ({Math.round(result.score_percentage)}%)
          </p>
          <p className={cn('text-sm font-medium', result.is_mastered ? 'text-green-700' : 'text-amber-700')}>
            {result.is_mastered
              ? 'Mastered! You can now complete this session.'
              : `Not yet mastered. Threshold: ${Math.round(result.threshold)}%`}
          </p>
          <div className="flex gap-2">
            {!result.is_mastered && (
              <Button size="sm" variant="secondary" onClick={handleRetake}>
                Retake Quiz
              </Button>
            )}
            <Button size="sm" variant="secondary" onClick={() => setShowExplanations((v) => !v)}>
              {showExplanations ? 'Hide Explanations' : 'Show Explanations'}
            </Button>
          </div>
        </div>
      )}

      {submitError && (
        <div className="rounded-xl border border-red-300 bg-red-50 px-5 py-4 space-y-2">
          <p className="text-sm font-medium text-red-700">{submitError}</p>
          <Button size="sm" variant="secondary" onClick={handleSubmit} loading={isSubmitting}>
            Retry
          </Button>
        </div>
      )}

      <div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
          {!result && !submitError && (
            <Button className="w-full sm:flex-1" onClick={handleSubmit} loading={isSubmitting} disabled={isSubmitting}>
              Submit Answers
            </Button>
          )}
          {onCompleteSession && (
          <div className="w-full sm:flex-1 text-center">
              <Button
                className="w-full"
                variant="secondary"
                onClick={onCompleteSession}
                loading={completeSessionLoading}
                disabled={completeSessionDisabled || completeSessionLoading}
              >
                {completeSessionLoading ? 'Completing…' : 'Complete Session'}
              </Button>
              {completeSessionHint && (
                <p className="mt-1 text-xs text-slate-400">{completeSessionHint}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

