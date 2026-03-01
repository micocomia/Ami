import ReactMarkdown from 'react-markdown';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui';
import { QuizPanel } from '@/components/learning/QuizPanel';
import { cn } from '@/lib/cn';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/hooks/useActiveGoal';
import { useAppConfig } from '@/api/endpoints/config';
import { useGoalRuntimeState } from '@/api/endpoints/goals';
import {
  useGetLearningContent,
  useGenerateLearningContent,
  useDeleteLearningContent,
  useSessionActivity,
  useCompleteSession,
  useSubmitContentFeedback,
} from '@/api/endpoints/content';
import { useChatWithTutor } from '@/api/endpoints/chat';
import type { MasteryEvaluationResponse, ContentSection } from '@/types';

interface LocationState {
  goalId: number;
  sessionIndex: number;
}

function absolutizeUrl(url: string | null | undefined): string {
  if (!url) return '';
  if (url.startsWith('http')) return url;
  const base = ((import.meta.env as Record<string, string>).VITE_API_BASE_URL ?? '').replace(/\/$/, '');
  return `${base}${url.startsWith('/') ? '' : '/'}${url}`;
}

function parseSections(doc: string | Record<string, unknown> | undefined): ContentSection[] {
  if (!doc) return [];
  const text = typeof doc === 'string' ? doc : '';
  if (!text) return [{ title: 'Content', markdown: JSON.stringify(doc, null, 2) }];
  const indices: Array<{ title: string; index: number }> = [];
  const headingRe = /^(#{1,3})\s+(.+)$/gm;
  let m: RegExpExecArray | null;
  while ((m = headingRe.exec(text)) !== null) {
    indices.push({ title: m[2].trim(), index: m.index });
  }
  if (indices.length === 0) return [{ title: 'Content', markdown: text }];
  return indices.map((h, i) => ({
    title: h.title,
    markdown: text.slice(h.index, indices[i + 1]?.index ?? text.length).trim(),
  }));
}

export function LearningSessionPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { userId } = useAuthContext();
  const { updateGoal } = useGoalsContext();
  const { data: config } = useAppConfig();
  const activeGoal = useActiveGoal();

  const state = location.state as LocationState | null;
  const goalId = state?.goalId;
  const sessionIndex = state?.sessionIndex;

  useEffect(() => {
    if (goalId == null || sessionIndex == null) navigate('/learning-path', { replace: true });
  }, [goalId, sessionIndex, navigate]);

  const { data: runtimeStateData } = useGoalRuntimeState(userId ?? undefined, goalId ?? undefined);
  const runtimeSession = runtimeStateData?.sessions.find((s) => s.session_index === sessionIndex);
  const navigationMode = runtimeSession?.navigation_mode ?? 'free';

  const { data: contentCacheResult, isLoading: isCheckingCache } = useGetLearningContent(
    userId ?? undefined,
    goalId ?? undefined,
    sessionIndex ?? undefined,
  );

  const generateMutation = useGenerateLearningContent();
  const deleteMutation = useDeleteLearningContent();
  const sessionActivityMutation = useSessionActivity();
  const completeSessionMutation = useCompleteSession();
  const submitFeedbackMutation = useSubmitContentFeedback();
  const chatMutation = useChatWithTutor();

  type ContentData = NonNullable<typeof contentCacheResult>['data'];
  const [content, setContent] = useState<ContentData>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const hasTriggeredGenRef = useRef(false);

  useEffect(() => {
    if (isCheckingCache) return;
    if (!contentCacheResult) return;
    if (contentCacheResult.status === 200 && contentCacheResult.data) {
      setContent(contentCacheResult.data);
      return;
    }
    if (contentCacheResult.status !== 404) return;
    if (hasTriggeredGenRef.current) return;
    if (!userId || goalId == null || sessionIndex == null || !activeGoal) return;
    const pathSession = activeGoal.learning_path?.[sessionIndex];
    if (!pathSession) return;
    hasTriggeredGenRef.current = true;
    setIsGenerating(true);
    generateMutation.mutate(
      {
        learner_profile: JSON.stringify(activeGoal.learner_profile ?? {}),
        learning_path: JSON.stringify(activeGoal.learning_path ?? []),
        learning_session: JSON.stringify(pathSession),
        use_search: true,
        allow_parallel: true,
        with_quiz: true,
        goal_context: activeGoal.goal_context ? JSON.stringify(activeGoal.goal_context) : undefined,
        user_id: userId,
        goal_id: goalId,
        session_index: sessionIndex,
      },
      {
        onSuccess: (data) => { setContent(data); setIsGenerating(false); },
        onError: () => { setGenerateError('Failed to generate content. Please try again.'); setIsGenerating(false); },
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isCheckingCache, contentCacheResult?.status]);

  const sections: ContentSection[] = content?.view_model?.sections?.length
    ? content.view_model.sections
    : parseSections(content?.document);

  const [currentSectionIdx, setCurrentSectionIdx] = useState(0);
  const [quizUnlocked, setQuizUnlocked] = useState(false);

  useEffect(() => {
    if (sections.length > 0 && currentSectionIdx >= sections.length - 1) setQuizUnlocked(true);
  }, [currentSectionIdx, sections.length]);

  useEffect(() => { setCurrentSectionIdx(0); setQuizUnlocked(false); }, [content]);

  // Heartbeat
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (!userId || goalId == null || sessionIndex == null) return;
    const interval = (config?.motivational_trigger_interval_secs ?? 30) * 1000;
    heartbeatRef.current = setInterval(() => {
      sessionActivityMutation.mutate({
        user_id: userId, goal_id: goalId, session_index: sessionIndex, event_type: 'heartbeat',
      });
    }, interval);
    return () => { if (heartbeatRef.current) clearInterval(heartbeatRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, goalId, sessionIndex, config?.motivational_trigger_interval_secs]);

  const [masteryResult, setMasteryResult] = useState<MasteryEvaluationResponse | null>(null);
  const canComplete = runtimeSession?.can_complete ?? true;
  const linearMasteryGate = navigationMode === 'linear' && masteryResult != null && !masteryResult.is_mastered;
  const isCompleteEnabled = canComplete && !linearMasteryGate;

  // Chat
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const [chatInput, setChatInput] = useState('');
  const [isChatOpen, setIsChatOpen] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chatMessages]);

  const handleSendChat = useCallback(async () => {
    if (!chatInput.trim() || !userId || goalId == null) return;
    const userMsg = { role: 'user' as const, content: chatInput.trim() };
    const updated = [...chatMessages, userMsg];
    setChatMessages(updated);
    setChatInput('');
    const last20 = updated.slice(-20);
    try {
      const res = await chatMutation.mutateAsync({
        messages: JSON.stringify(last20),
        learner_profile: JSON.stringify(activeGoal?.learner_profile ?? {}),
        user_id: userId,
        goal_id: goalId,
        session_index: sessionIndex,
        learner_information: activeGoal?.learner_profile?.learner_information as string | undefined,
      });
      setChatMessages((prev) => [...prev, { role: 'assistant', content: res.response }]);
      if (res.updated_learner_profile && activeGoal && goalId != null) {
        updateGoal(goalId, { ...activeGoal, learner_profile: res.updated_learner_profile });
      }
    } catch {
      setChatMessages((prev) => [...prev, { role: 'assistant', content: 'Sorry, I encountered an error.' }]);
    }
  }, [chatInput, chatMessages, userId, goalId, sessionIndex, activeGoal, chatMutation, updateGoal]);

  // Feedback
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [clarityRating, setClarityRating] = useState(0);
  const [relevanceRating, setRelevanceRating] = useState(0);
  const [depthRating, setDepthRating] = useState(0);
  const [feedbackComments, setFeedbackComments] = useState('');

  const handleSubmitFeedback = useCallback(async () => {
    if (!userId || goalId == null) return;
    try {
      const res = await submitFeedbackMutation.mutateAsync({
        user_id: userId,
        goal_id: goalId,
        feedback: { clarity: clarityRating, relevance: relevanceRating, depth: depthRating, comments: feedbackComments, session_index: sessionIndex },
      });
      setFeedbackSubmitted(true);
      if (res.goal) updateGoal(goalId, res.goal);
    } catch { /* ignore */ }
  }, [userId, goalId, clarityRating, relevanceRating, depthRating, feedbackComments, sessionIndex, submitFeedbackMutation, updateGoal]);

  const handleBack = useCallback(async () => {
    if (userId && goalId != null && sessionIndex != null) {
      await sessionActivityMutation.mutateAsync({
        user_id: userId, goal_id: goalId, session_index: sessionIndex, event_type: 'end',
      }).catch(() => {});
    }
    navigate('/learning-path');
  }, [userId, goalId, sessionIndex, sessionActivityMutation, navigate]);

  const handleRegenerate = useCallback(async () => {
    if (!userId || goalId == null || sessionIndex == null) return;
    await sessionActivityMutation.mutateAsync({
      user_id: userId, goal_id: goalId, session_index: sessionIndex, event_type: 'end',
    }).catch(() => {});
    setContent(null);
    setGenerateError(null);
    setMasteryResult(null);
    hasTriggeredGenRef.current = false;
    deleteMutation.mutate({ userId, goalId, sessionIndex });
  }, [userId, goalId, sessionIndex, sessionActivityMutation, deleteMutation]);

  const handleComplete = useCallback(async () => {
    if (!userId || goalId == null || sessionIndex == null) return;
    try {
      const res = await completeSessionMutation.mutateAsync({ user_id: userId, goal_id: goalId, session_index: sessionIndex });
      if (res.goal) updateGoal(goalId, res.goal);
      navigate('/learning-path');
    } catch { /* ignore */ }
  }, [userId, goalId, sessionIndex, completeSessionMutation, updateGoal, navigate]);

  if (goalId == null || sessionIndex == null) return null;

  const pathSession = activeGoal?.learning_path?.[sessionIndex];
  const sessionTitle = (pathSession?.title as string | undefined) ?? `Session ${sessionIndex + 1}`;

  if (isCheckingCache || isGenerating) {
    return (
      <div className="flex flex-col items-center justify-center min-h-96 space-y-4 text-slate-500">
        <div className="w-8 h-8 border-4 border-primary-400 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm">
          {isGenerating ? 'Generating personalised content… this may take a minute.' : 'Loading content…'}
        </p>
      </div>
    );
  }

  if (generateError) {
    return (
      <div className="max-w-3xl space-y-4">
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">{generateError}</div>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={handleBack}>Back</Button>
          <Button onClick={() => { setGenerateError(null); handleRegenerate(); }}>Retry</Button>
        </div>
      </div>
    );
  }

  if (!content) return (
    <div className="flex flex-col items-center justify-center min-h-96 text-slate-400 text-sm">
      No content available.
    </div>
  );

  const currentSection = sections[currentSectionIdx];
  const references = content.view_model?.references ?? [];
  const audioUrl = absolutizeUrl(content.audio_url);

  return (
    <div className="flex gap-6 max-w-6xl">
      {/* Left TOC */}
      {sections.length > 1 && (
        <aside className="hidden lg:block w-52 shrink-0">
          <div className="sticky top-4 space-y-1">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Contents</p>
            {sections.map((s, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setCurrentSectionIdx(i)}
                className={cn(
                  'w-full text-left text-xs px-3 py-2 rounded-lg transition-all',
                  i === currentSectionIdx
                    ? 'bg-primary-50 text-primary-700 font-medium'
                    : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50',
                )}
              >
                {s.title}
              </button>
            ))}
          </div>
        </aside>
      )}

      {/* Main */}
      <div className="flex-1 min-w-0 space-y-6">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <button type="button" onClick={handleBack} className="text-sm text-slate-500 hover:text-slate-700 flex items-center gap-1 mb-2">
              ← Back to Learning Path
            </button>
            <h2 className="text-xl font-semibold text-slate-800">{sessionTitle}</h2>
          </div>
          <div className="flex gap-2 shrink-0 flex-wrap">
            <Button size="sm" variant="secondary" onClick={handleRegenerate}>Regenerate</Button>
            <button
              type="button"
              onClick={() => setIsChatOpen((v) => !v)}
              className="px-3 py-2 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 text-sm flex items-center gap-1.5"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
              </svg>
              Ask Ami
            </button>
          </div>
        </div>

        {content.content_format === 'audio_enhanced' && audioUrl && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-2">
            <p className="text-sm text-blue-700 font-medium">Audio version available</p>
            <audio controls src={audioUrl} className="w-full" />
          </div>
        )}
        {content.content_format === 'visual_enhanced' && (
          <div className="bg-purple-50 border border-purple-200 rounded-lg px-4 py-3 text-sm text-purple-800">
            This content includes enhanced visual elements.
          </div>
        )}

        {currentSection && (
          <div className="bg-white border border-slate-200 rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-800">{currentSection.title}</h3>
              <span className="text-xs text-slate-400">{currentSectionIdx + 1} / {sections.length}</span>
            </div>
            <div className="prose prose-sm prose-slate max-w-none">
              <ReactMarkdown>{currentSection.markdown}</ReactMarkdown>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between">
          <Button variant="secondary" size="sm" disabled={currentSectionIdx === 0} onClick={() => setCurrentSectionIdx((i) => Math.max(0, i - 1))}>
            ← Previous
          </Button>
          <Button variant="secondary" size="sm" disabled={currentSectionIdx >= sections.length - 1} onClick={() => setCurrentSectionIdx((i) => Math.min(sections.length - 1, i + 1))}>
            Next →
          </Button>
        </div>

        {references.length > 0 && (
          <details className="text-sm border border-slate-200 rounded-lg">
            <summary className="px-4 py-3 cursor-pointer text-slate-600 font-medium select-none">
              References ({references.length})
            </summary>
            <ol className="px-6 pb-4 pt-1 space-y-1 text-xs text-slate-500 list-decimal">
              {references.map((ref) => <li key={ref.index}>{ref.label}</li>)}
            </ol>
          </details>
        )}

        {quizUnlocked && content.quizzes && (
          <div className="border-t border-slate-200 pt-6">
            <QuizPanel
              quiz={content.quizzes}
              userId={userId!}
              goalId={goalId}
              sessionIndex={sessionIndex}
              onMasteryResult={(r) => setMasteryResult(r)}
            />
          </div>
        )}

        {quizUnlocked && !feedbackSubmitted && (
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-4">
            <h3 className="font-semibold text-slate-700">Rate this session</h3>
            {[
              { label: 'Clarity', value: clarityRating, set: setClarityRating },
              { label: 'Relevance', value: relevanceRating, set: setRelevanceRating },
              { label: 'Depth', value: depthRating, set: setDepthRating },
            ].map(({ label, value, set }) => (
              <div key={label} className="flex items-center gap-3">
                <span className="text-sm text-slate-600 w-20">{label}</span>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((star) => (
                    <button key={star} type="button" onClick={() => set(star)}
                      className={cn('text-xl', star <= value ? 'text-amber-400' : 'text-slate-300 hover:text-amber-300')}>
                      ★
                    </button>
                  ))}
                </div>
              </div>
            ))}
            <textarea
              value={feedbackComments}
              onChange={(e) => setFeedbackComments(e.target.value)}
              rows={2}
              placeholder="Any other comments? (optional)"
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-400 resize-none"
            />
            <Button size="sm" onClick={handleSubmitFeedback} loading={submitFeedbackMutation.isPending}
              disabled={clarityRating === 0 || relevanceRating === 0 || depthRating === 0 || submitFeedbackMutation.isPending}>
              Submit Feedback
            </Button>
          </div>
        )}
        {feedbackSubmitted && (
          <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-700">
            Thank you for your feedback!
          </div>
        )}

        <div className="flex justify-end pt-2 pb-8">
          <Button size="lg" onClick={handleComplete} loading={completeSessionMutation.isPending}
            disabled={!isCompleteEnabled || completeSessionMutation.isPending}>
            {completeSessionMutation.isPending ? 'Completing…' : 'Complete Session'}
          </Button>
        </div>
      </div>

      {/* Inline chatbot */}
      {isChatOpen && (
        <aside className="w-80 shrink-0 hidden xl:flex flex-col">
          <div className="sticky top-4 flex flex-col h-[calc(100vh-8rem)] border border-slate-200 rounded-xl bg-white overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
              <p className="font-semibold text-slate-800 text-sm">Ask Ami</p>
              <button type="button" onClick={() => setIsChatOpen(false)} className="text-slate-400 hover:text-slate-600">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {chatMessages.length === 0 && (
                <p className="text-xs text-slate-400 text-center">Ask me anything about this session!</p>
              )}
              {chatMessages.map((msg, i) => (
                <div key={i} className={cn('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
                  <div className={cn(
                    'max-w-[85%] rounded-xl px-3 py-2 text-sm',
                    msg.role === 'user' ? 'bg-primary-600 text-white' : 'bg-slate-100 text-slate-800',
                  )}>
                    {msg.content}
                  </div>
                </div>
              ))}
              {chatMutation.isPending && (
                <div className="flex justify-start">
                  <div className="bg-slate-100 rounded-xl px-3 py-2 text-sm text-slate-400">Thinking…</div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
            <div className="p-3 border-t border-slate-100 flex gap-2">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendChat(); } }}
                placeholder="Ask a question…"
                className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-400"
              />
              <Button size="sm" onClick={handleSendChat} disabled={!chatInput.trim() || chatMutation.isPending}>
                Send
              </Button>
            </div>
          </div>
        </aside>
      )}
    </div>
  );
}
