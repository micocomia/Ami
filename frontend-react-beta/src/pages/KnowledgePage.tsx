import { Button } from '@/components/ui';

export function KnowledgePage() {
  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Knowledge Check</h2>
        <p className="mt-1 text-sm text-slate-500">
          Test your understanding with adaptive quizzes and mastery evaluations.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-3">
          <h3 className="font-semibold text-slate-700">Quiz Mix</h3>
          <p className="text-sm text-slate-500">
            Get a personalized mix of questions based on your current progress.
          </p>
          <Button size="sm">Start Quiz</Button>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-3">
          <h3 className="font-semibold text-slate-700">Mastery Evaluation</h3>
          <p className="text-sm text-slate-500">
            Evaluate how well you&apos;ve mastered each topic in your learning path.
          </p>
          <Button size="sm" variant="secondary">Evaluate</Button>
        </div>
      </div>

      {/* Results placeholder */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="font-medium text-slate-700 mb-3">Recent Results</h3>
        <p className="text-sm text-slate-400 italic">No evaluations yet. Start a quiz to see your results.</p>
      </div>
    </div>
  );
}
