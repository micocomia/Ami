import { useState } from 'react';
import { Button, InputField, TextArea } from '@/components/ui';
import {
  useRefineLearningGoal,
  refineLearningGoalRequestSchema,
  type RefineLearningGoalResponse,
} from '@/api/endpoints/refineLearningGoal';

function formatResponse(data: RefineLearningGoalResponse): string {
  if (typeof data === 'string') return data;
  if (data && typeof data === 'object' && 'refined_goal' in data) {
    return String((data as { refined_goal?: string }).refined_goal ?? JSON.stringify(data));
  }
  return JSON.stringify(data);
}

export function RefineGoalExamplePage() {
  const [learningGoal, setLearningGoal] = useState('');
  const [learnerInfo, setLearnerInfo] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);

  const { mutate, data, isPending, error, isError, reset } = useRefineLearningGoal();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError(null);
    const payload = {
      learning_goal: learningGoal.trim(),
      learner_information: learnerInfo.trim() || undefined,
    };
    const parsed = refineLearningGoalRequestSchema.safeParse(payload);
    if (!parsed.success) {
      const first = parsed.error.flatten().fieldErrors.learning_goal?.[0] ?? parsed.error.message;
      setValidationError(first);
      return;
    }
    mutate(parsed.data);
  };

  return (
    <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
      <div className="max-w-xl space-y-6">
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <h2 className="text-xl font-semibold text-slate-900">Refine Learning Goal</h2>
          <p className="mt-1 text-sm text-slate-600">
            Calls <code className="text-xs bg-slate-100 px-1 py-0.5 rounded text-slate-800">POST /refine-learning-goal</code> and
            displays the refined goal. Use this page to test the API; onboarding &quot;AI Refinement&quot; currently uses mock data.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm ring-1 ring-slate-900/5 space-y-4">
          <InputField
            label="Learning goal"
            placeholder="e.g. Learn Python for data science"
            value={learningGoal}
            onChange={(e) => setLearningGoal(e.target.value)}
            disabled={isPending}
            error={validationError ?? undefined}
            required
          />
          <TextArea
            label="Learner information (optional)"
            placeholder="e.g. I have some experience with Excel"
            value={learnerInfo}
            onChange={(e) => setLearnerInfo(e.target.value)}
            disabled={isPending}
            rows={2}
          />
          <div className="flex gap-3">
            <Button type="submit" loading={isPending} className="!bg-primary-600 hover:!bg-primary-700 !text-white">
              Refine goal
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={isPending}
              onClick={() => { reset(); setValidationError(null); }}
            >
              Clear result
            </Button>
          </div>
        </form>

        {isError && (
          <div className="rounded-lg border border-danger-500/30 bg-danger-50 p-4 text-sm text-slate-800">
            <strong className="text-danger-700">Error:</strong>{' '}
            <span className="text-slate-700">{error instanceof Error ? error.message : String(error)}</span>
          </div>
        )}

        {data !== undefined && !isError && (
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm border-l-4 border-l-primary-500">
            <p className="text-sm font-semibold text-slate-900">Refined goal</p>
            <pre className="whitespace-pre-wrap mt-2 text-sm text-slate-700">{formatResponse(data)}</pre>
          </div>
        )}
      </div>
    </div>
  );
}
