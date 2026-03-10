import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, InputField, Modal } from '@/components/ui';
import { cn } from '@/lib/cn';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useDeleteGoal, usePatchGoal } from '@/api/endpoints/goals';
import type { LearningPathSession } from '@/types';

function getProgress(path: LearningPathSession[] | undefined): number {
  if (!path || path.length === 0) return 0;
  const learned = path.filter((s) => s.if_learned).length;
  return Math.round((learned / path.length) * 100);
}

function getStatus(path: LearningPathSession[] | undefined): 'Completed' | 'In Progress' | 'Not Started' {
  if (!path || path.length === 0) return 'Not Started';
  const learned = path.filter((s) => s.if_learned).length;
  if (learned === path.length) return 'Completed';
  if (learned > 0) return 'In Progress';
  return 'Not Started';
}

export function GoalsPage() {
  const navigate = useNavigate();
  const { userId } = useAuthContext();
  const { goals, selectedGoalId, setSelectedGoalId, refreshGoals, isLoading } = useGoalsContext();

  const [editingGoalId, setEditingGoalId] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const [deletingGoalId, setDeletingGoalId] = useState<number | null>(null);
  const [isAddGoalModalOpen, setIsAddGoalModalOpen] = useState(false);
  const [newGoalText, setNewGoalText] = useState('');

  const deleteGoalMutation = useDeleteGoal(userId ?? undefined);
  const patchGoalMutation = usePatchGoal(userId ?? undefined, editingGoalId ?? undefined);

  const activeGoals = goals.filter((g) => !g.is_deleted);
  const currentGoal = activeGoals.find((g) => g.id === selectedGoalId) ?? null;

  const handleStartEdit = useCallback((goalId: number, currentGoalText: string) => {
    setEditingGoalId(goalId);
    setEditText(currentGoalText);
    setDeletingGoalId(null);
  }, []);

  const handleSaveEdit = useCallback(async () => {
    if (!editText.trim() || editingGoalId == null) return;
    try {
      await patchGoalMutation.mutateAsync({ learning_goal: editText.trim() });
      refreshGoals();
    } catch { /* ignore */ }
    setEditingGoalId(null);
  }, [editText, editingGoalId, patchGoalMutation, refreshGoals]);

  const handleDelete = useCallback(async (goalId: number) => {
    try {
      await deleteGoalMutation.mutateAsync(goalId);
      refreshGoals();
      if (selectedGoalId === goalId) {
        const remaining = activeGoals.filter((g) => g.id !== goalId);
        if (remaining.length > 0) setSelectedGoalId(remaining[0].id);
      }
    } catch { /* ignore */ }
    setDeletingGoalId(null);
  }, [deleteGoalMutation, refreshGoals, selectedGoalId, activeGoals, setSelectedGoalId]);

  const handleSwitchGoal = useCallback((goalId: number) => {
    setSelectedGoalId(goalId);
    navigate('/learning-path');
  }, [setSelectedGoalId, navigate]);

  const handleAddGoal = useCallback(() => {
    const title = newGoalText.trim();
    if (!title) return;
    setIsAddGoalModalOpen(false);
    setNewGoalText('');
    navigate('/skill-gap', {
      state: {
        goal: title,
        personaKey: null,
        learnerInformation: activeGoals[0]?.learner_profile?.learner_information ?? '',
        isGoalManagementFlow: true,
      },
    });
  }, [newGoalText, navigate, activeGoals]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-96 space-y-4 text-slate-500">
        <div className="w-8 h-8 border-4 border-primary-400 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm">Loading goals…</p>
      </div>
    );
  }

  const currentProgress = currentGoal ? getProgress(currentGoal.learning_path) : 0;
  const currentDisplayName =
    (currentGoal?.learner_profile?.goal_display_name as string | undefined) ?? currentGoal?.learning_goal ?? '';
  const nextSession = currentGoal?.learning_path?.find((s) => !s.if_learned);

  return (
    <div className="max-w-4xl space-y-8">
      {/* Header — current goal */}
      {currentGoal && (
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <p className="text-base font-medium text-slate-600">
            Current Goal:{' '}
            <span className="font-semibold text-slate-900">
              {currentDisplayName.length > 100 ? currentDisplayName.slice(0, 100) + '…' : currentDisplayName}
            </span>
          </p>
        </div>
      )}

      {/* Currently active goal detail */}
      {currentGoal && (
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
          <div className="border-l-4 border-primary-600 pl-4">
            <h2 className="text-xl font-bold tracking-tight text-slate-900">
              {currentDisplayName.length > 80 ? currentDisplayName.slice(0, 80) + '…' : currentDisplayName}
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              {currentGoal.learning_path
                ? `${currentGoal.learning_path.filter((s) => s.if_learned).length} / ${currentGoal.learning_path.length} sessions completed`
                : 'No learning path yet'}
            </p>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <div className="flex-1 h-2 rounded-full bg-slate-200 overflow-hidden">
              <div
                className="h-full rounded-full bg-primary-600 transition-all duration-300"
                style={{ width: `${currentProgress}%` }}
              />
            </div>
            <span className="text-sm font-semibold shrink-0 w-10 text-right text-slate-900">
              {currentProgress}%
            </span>
          </div>
          {nextSession && (
            <p className="mt-3 text-sm text-slate-600">
              Next up: {(nextSession.title as string | undefined) ?? 'Untitled session'}
            </p>
          )}
          <div className="mt-5 flex flex-wrap gap-3">
            {nextSession && (
              <Button
                size="md"
                className="!bg-primary-800 !text-white hover:!bg-primary-900"
                onClick={() => {
                  const idx = currentGoal.learning_path?.findIndex((s) => s.id === nextSession.id) ?? -1;
                  if (idx >= 0) {
                    navigate('/learning-session', {
                      state: { goalId: currentGoal.id, sessionIndex: idx },
                    });
                  }
                }}
              >
                <svg className="w-4 h-4 mr-1.5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5.14v14l11-7-11-7z" />
                </svg>
                Continue Learning
              </Button>
            )}
            <Button
              variant="secondary"
              size="md"
              className="!border-primary-600 !text-primary-700 hover:!bg-primary-50 hover:!border-primary-700"
              onClick={() => navigate('/learning-path')}
            >
              View Full Path
            </Button>
          </div>
        </section>
      )}

      {/* All goals grid */}
      <section>
        <h3 className="text-base font-semibold text-slate-800 mb-4">
          ALL GOALS ({activeGoals.length})
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {activeGoals.map((goal) => {
            const progress = getProgress(goal.learning_path);
            const status = getStatus(goal.learning_path);
            const isActive = goal.id === selectedGoalId;
            const displayName =
              (goal.learner_profile?.goal_display_name as string | undefined) ?? goal.learning_goal;
            const isEditing = editingGoalId === goal.id;
            const isConfirmingDelete = deletingGoalId === goal.id;

            return (
              <div
                key={goal.id}
                className={cn(
                  'bg-white rounded-xl border p-4 flex flex-col',
                  isActive ? 'border-primary-300 ring-1 ring-primary-200' : 'border-slate-200',
                )}
              >
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={cn(
                        'text-xs font-medium px-2 py-0.5 rounded-full',
                        status === 'Completed'
                          ? 'bg-green-100 text-green-700'
                          : status === 'In Progress'
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-slate-100 text-slate-500',
                      )}
                    >
                      {status}
                    </span>
                    {isActive && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-primary-100 text-primary-700 font-medium">
                        Active
                      </span>
                    )}
                  </div>
                </div>

                {isEditing ? (
                  <div className="space-y-2 mt-1">
                    <input
                      type="text"
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleSaveEdit();
                        if (e.key === 'Escape') setEditingGoalId(null);
                      }}
                      className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-400"
                      autoFocus
                    />
                    <div className="flex gap-2">
                      <Button size="sm" onClick={handleSaveEdit} loading={patchGoalMutation.isPending}>
                        Save
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => setEditingGoalId(null)}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <h4 className="font-semibold text-slate-900 text-sm leading-snug">
                      {displayName.length > 60 ? displayName.slice(0, 60) + '…' : displayName}
                    </h4>
                    <p className="text-sm text-slate-500 mt-1">{progress}% complete</p>
                    <div className="mt-3 flex items-center gap-2">
                      <div className="flex-1 h-1.5 rounded-full bg-slate-200 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-primary-500 transition-all duration-300"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                      <span className="text-xs font-semibold text-slate-600 w-8 text-right">
                        {progress}%
                      </span>
                    </div>
                  </>
                )}

                {isConfirmingDelete && (
                  <div className="bg-red-50 border border-red-200 rounded-lg p-3 mt-3 text-sm">
                    <p className="text-red-700 mb-2">Delete this goal? This cannot be undone.</p>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={() => handleDelete(goal.id)}
                        loading={deleteGoalMutation.isPending}
                        className="!bg-red-600 hover:!bg-red-700 !text-white"
                      >
                        Delete
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => setDeletingGoalId(null)}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}

                {!isEditing && !isConfirmingDelete && (
                  <div className="mt-auto pt-3 flex gap-2">
                    {isActive ? (
                      <Button
                        size="sm"
                        className="flex-1 !bg-primary-600 hover:!bg-primary-700 !text-white"
                        onClick={() => navigate('/learning-path')}
                      >
                        View Path
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        className="flex-1 !bg-primary-600 hover:!bg-primary-700 !text-white"
                        onClick={() => handleSwitchGoal(goal.id)}
                      >
                        Switch to This
                      </Button>
                    )}
                    <button
                      type="button"
                      onClick={() => handleStartEdit(goal.id, goal.learning_goal)}
                      className="px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 transition-colors"
                      title="Edit"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeletingGoalId(goal.id)}
                      className="px-2.5 py-1.5 text-xs rounded-lg border border-red-200 text-red-400 hover:bg-red-50 transition-colors"
                      title="Delete"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                      </svg>
                    </button>
                  </div>
                )}
              </div>
            );
          })}

          {/* Add new goal card */}
          <button
            type="button"
            onClick={() => setIsAddGoalModalOpen(true)}
            className={cn(
              'relative rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 p-6',
              'flex flex-col items-center justify-center gap-2 min-h-[200px]',
              'text-slate-500 hover:border-slate-300 hover:bg-slate-100 hover:text-slate-700 transition-colors',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 focus-visible:ring-offset-2',
            )}
          >
            <svg className="w-10 h-10 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            <span className="font-semibold text-slate-700">Add a new goal</span>
            <span className="text-sm">Start a new learning journey</span>
          </button>
        </div>
      </section>

      {/* Add New Goal modal */}
      <Modal
        open={isAddGoalModalOpen}
        onClose={() => { setIsAddGoalModalOpen(false); setNewGoalText(''); }}
        title="Add New Goal"
      >
        <div className="space-y-4">
          <InputField
            placeholder="e.g. Learn Python for data analysis..."
            value={newGoalText}
            onChange={(e) => setNewGoalText(e.target.value)}
            onKeyDown={(e: React.KeyboardEvent) => { if (e.key === 'Enter') handleAddGoal(); }}
            aria-label="Goal topic"
          />
          <p className="text-xs text-slate-400">
            This will take you through skill gap analysis before adding the goal.
          </p>
          <div className="flex justify-end">
            <Button
              size="md"
              className="!bg-primary-600 hover:!bg-primary-700 !text-white"
              onClick={handleAddGoal}
              disabled={!newGoalText.trim()}
            >
              Continue
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
