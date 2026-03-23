import { cn } from '@/lib/cn';

type ParsedPlanQuality = {
  refinement_iterations: number;
  evaluation: {
    pass: boolean;
    issues: unknown[];
    feedback_summary: Record<string, unknown>;
  };
};

function coerceMetadata(raw: unknown): ParsedPlanQuality | null {
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const meta = raw as Record<string, unknown>;
  if (Object.keys(meta).length === 0) return null;

  const refinement_iterations =
    typeof meta.refinement_iterations === 'number' && Number.isFinite(meta.refinement_iterations)
      ? meta.refinement_iterations
      : 1;

  const ev = meta.evaluation;
  let evaluation: ParsedPlanQuality['evaluation'];
  if (ev && typeof ev === 'object' && !Array.isArray(ev)) {
    const e = ev as Record<string, unknown>;
    const issues = Array.isArray(e.issues) ? e.issues : [];
    const fs = e.feedback_summary;
    const feedback_summary =
      fs && typeof fs === 'object' && !Array.isArray(fs) ? (fs as Record<string, unknown>) : {};
    evaluation = {
      pass: typeof e.pass === 'boolean' ? e.pass : true,
      issues,
      feedback_summary,
    };
  } else {
    evaluation = { pass: true, issues: [], feedback_summary: {} };
  }

  return { refinement_iterations, evaluation };
}

/** Set to `true` to show the three feedback cards (Progression, Engagement, Personalization, …) again. */
const SHOW_PLAN_QUALITY_FEEDBACK_CARDS = false;

/**
 * Read-only Plan Quality block — mirrors Streamlit `render_plan_quality_section` / backend
 * `learning_plan_pipeline.schedule_learning_path_agentic` metadata:
 * `refinement_iterations`, `evaluation.pass`, `evaluation.issues`, `evaluation.feedback_summary`.
 */
export function PlanQualityPanel({
  planAgentMetadata,
  className,
}: {
  planAgentMetadata: unknown;
  className?: string;
}) {
  const parsed = coerceMetadata(planAgentMetadata);
  if (!parsed) return null;

  const { evaluation, refinement_iterations = 1 } = parsed;
  const passed = evaluation.pass !== false;
  const issues = (evaluation.issues ?? []).map((x) => (typeof x === 'string' ? x : String(x)));
  const feedbackSummary = evaluation.feedback_summary ?? {};
  const summaryKeys = Object.keys(feedbackSummary);

  return (
    <details
      className={cn(
        'group rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden open:shadow-md',
        className,
      )}
    >
      <summary
        className={cn(
          'cursor-pointer list-none px-4 py-3 text-sm font-semibold text-slate-800',
          'hover:bg-slate-50 transition-colors flex items-center justify-between gap-2',
          '[&::-webkit-details-marker]:hidden',
        )}
      >
        <span>Plan Quality (Auto-Evaluated)</span>
        <svg
          className="h-4 w-4 text-slate-400 shrink-0 transition-transform group-open:rotate-180"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </summary>

      <div className="border-t border-slate-100 px-4 pb-4 pt-2 space-y-3 text-sm">
        {passed ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-900 text-sm">
            Plan Quality: PASS (after {refinement_iterations} iteration{refinement_iterations !== 1 ? 's' : ''})
          </div>
        ) : (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-950 text-sm space-y-2">
            <p>
              Plan Quality: NEEDS REVIEW ({issues.length} issue{issues.length !== 1 ? 's' : ''},{' '}
              {refinement_iterations} iteration{refinement_iterations !== 1 ? 's' : ''})
            </p>
            {issues.length > 0 && (
              <ul className="list-disc list-inside text-xs space-y-0.5 text-amber-950/90">
                {issues.map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {SHOW_PLAN_QUALITY_FEEDBACK_CARDS && summaryKeys.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {summaryKeys.map((key) => {
              const val = feedbackSummary[key];
              const display = typeof val === 'string' ? val : JSON.stringify(val);
              return (
                <div key={key} className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2">
                  <p className="text-xs font-semibold text-slate-700">
                    {key
                      .split('_')
                      .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
                      .join(' ')}
                  </p>
                  <p className="mt-1 text-xs text-slate-600 leading-snug">{display}</p>
                </div>
              );
            })}
          </div>
        )}

        <p className="text-[11px] text-slate-500">Refinement iterations: {refinement_iterations}</p>
      </div>
    </details>
  );
}
