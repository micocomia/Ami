import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, InputField } from '@/components/ui';
import { cn } from '@/lib/cn';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useDeleteGoal, usePatchGoal } from '@/api/endpoints/goals';
import type { LearningPathSession } from '@/types';

export function GoalsPage() {
  const navigate = useNavigate();
  const { userId } = useAuthContext();
  const { goals, selectedGoalId, setSelectedGoalId, refreshGoals } = useGoalsContext();

  const [editingGoalId, setEditingGoalId] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const [deletingGoalId, setDeletingGoalId] = useState<number | null>(null);
  const [newGoalText, setNewGoalText] = useState('');
  const deleteGoalMutation = useDeleteGoal(userId ?? undefined);
  const patchGoalMutation = usePatchGoal(userId ?? undefined, editingGoalId ?? undefined);

  const activeGoals = goals.filter((g) => !g.is_deleted);

  const handleStartEdit = useCallback((goalId: number, currentGoal: string) => {
    setEditingGoalId(goalId);
    setEditText(currentGoal);
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

  const handleAddGoal = useCallback(() => {
    if (!newGoalText.trim()) return;
    navigate('/skill-gap', {
      state: {
        goal: newGoalText.trim(),
        personaKey: null,
        learnerInformation: activeGoals[0]?.learner_profile?.learner_information ?? '',
        isGoalManagementFlow: true,
      },
    });
  }, [newGoalText, navigate, activeGoals]);

  const handleSwitchGoal = useCallback((goalId: number) => {
    setSelectedGoalId(goalId);
    navigate('/learning-path');
  }, [setSelectedGoalId, navigate]);

  function getProgress(goal: typeof goals[0]): number {
    const path = goal.learning_path ?? [];
    if (path.length === 0) return 0;
    const learned = (path as LearningPathSession[]).filter((s) => s.if_learned).length;
    return Math.round((learned / path.length) * 100);
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-800">Your Goals</h2>
        <p className="mt-1 text-sm text-slate-500">Manage your learning goals.</p>
      </div>

      {/* Goal list */}
      <div className="space-y-3">
        {activeGoals.length === 0 && (
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center text-slate-500 text-sm">
            No goals yet. Add your first learning goal below.
          </div>
        )}
        {activeGoals.map((goal) => {
          const isActive = goal.id === selectedGoalId;
          const progress = getProgress(goal);
          const displayName = (goal.learner_profile?.goal_display_name as string | undefined) ?? goal.learning_goal;
          const isEditing = editingGoalId === goal.id;
          const isConfirmingDelete = deletingGoalId === goal.id;

          return (
            <div
              key={goal.id}
              className={cn(
                'bg-white rounded-xl border p-5 space-y-3 transition-all',
                isActive ? 'border-primary-300 bg-primary-50/30' : 'border-slate-200',
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  {isEditing ? (
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') handleSaveEdit(); if (e.key === 'Escape') setEditingGoalId(null); }}
                        className="flex-1 px-3 py-1.5 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-400"
                        autoFocus
                      />
                      <Button size="sm" onClick={handleSaveEdit} loading={patchGoalMutation.isPending}>Save</Button>
                      <Button size="sm" variant="secondary" onClick={() => setEditingGoalId(null)}>Cancel</Button>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-semibold text-slate-800 text-sm leading-snug">
                          {displayName.length > 80 ? displayName.slice(0, 80) + '…' : displayName}
                        </h3>
                        {isActive && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-primary-100 text-primary-700 font-medium">
                            Active
                          </span>
                        )}
                      </div>
                      {/* Progress bar */}
                      <div className="mt-2">
                        <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                          <span>Progress</span>
                          <span>{progress}%</span>
                        </div>
                        <div className="h-1.5 bg-slate-100 rounded-full">
                          <div
                            className="h-full bg-primary-500 rounded-full transition-all"
                            style={{ width: `${progress}%` }}
                          />
                        </div>
                      </div>
                    </>
                  )}
                </div>

                {!isEditing && (
                  <div className="flex gap-1.5 shrink-0">
                    {!isActive && (
                      <button
                        type="button"
                        onClick={() => handleSwitchGoal(goal.id)}
                        className="px-3 py-1.5 text-xs rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors"
                      >
                        Switch
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => handleStartEdit(goal.id, goal.learning_goal)}
                      className="px-3 py-1.5 text-xs rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeletingGoalId(goal.id)}
                      className="px-3 py-1.5 text-xs rounded-lg border border-red-200 text-red-500 hover:bg-red-50 transition-colors"
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>

              {isConfirmingDelete && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm">
                  <p className="text-red-700 mb-2">Are you sure you want to delete this goal? This cannot be undone.</p>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => handleDelete(goal.id)} loading={deleteGoalMutation.isPending}
                      className="!bg-red-600 hover:!bg-red-700 !text-white">
                      Delete
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => setDeletingGoalId(null)}>Cancel</Button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Add new goal */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
        <h3 className="font-semibold text-slate-700 text-sm">Add a new goal</h3>
        <div className="flex gap-2">
          <div className="flex-1">
            <InputField
              placeholder="eg: learn Python, master data visualisation..."
              value={newGoalText}
              onChange={(e) => setNewGoalText(e.target.value)}
              onKeyDown={(e: React.KeyboardEvent) => { if (e.key === 'Enter') handleAddGoal(); }}
            />
          </div>
          <Button
            onClick={handleAddGoal}
            disabled={!newGoalText.trim()}
          >
            Add Goal
          </Button>
        </div>
        <p className="text-xs text-slate-400">
          This will take you through the skill gap analysis before adding the goal to your list.
        </p>
      </div>
    </div>
  );
}
