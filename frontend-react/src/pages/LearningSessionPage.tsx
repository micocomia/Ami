import { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Button } from '@/components/ui';
import { cn } from '@/lib/cn';
import { BREADCRUMB_GOAL, DEFAULT_SESSION_ID, getSessionById } from '@/mock/learningPath';

/* ------------------------------------------------------------------ */
/*  Types & mock data                                                 */
/* ------------------------------------------------------------------ */

interface VocabItem {
  word: string;
  translation: string;
}

interface ModuleItem {
  id: string;
  title: string;
}

interface SessionModule {
  id: string;
  title: string;
  mediaTitle: string;
  duration: string;
  tags: string[];
  contentHeading: string;
  intro: string;
  insight: string;
  vocab: VocabItem[];
  practice: string;
}

const MODULES: SessionModule[] = [
  {
    id: 'm1',
    title: 'Module 1 — Les Nombres (Numbers)',
    mediaTitle: 'French Numbers 1-100 — Beginner Guide',
    duration: '12 min',
    tags: ['Interactive quiz included', 'Covers +8% Oral skill'],
    contentHeading: 'Module 1 — Les Nombres (Numbers)',
    intro:
      'In French, numbers follow a logical system up to 60, after which they become compound. Mastering these early is key — you\'ll use them for prices, addresses, and scheduling.',
    insight:
      'French numbers 70-99 are built from 60. Soixante-dix (70) literally means "sixty-ten." Once you understand the pattern, everything clicks.',
    vocab: [
      { word: 'un / une', translation: 'one (m/f)' },
      { word: 'deux', translation: 'two' },
      { word: 'cinq', translation: 'five' },
      { word: 'dix', translation: 'ten' },
      { word: 'vingt', translation: 'twenty' },
      { word: 'soixante', translation: 'sixty' },
    ],
    practice:
      'Practice saying these aloud. The silent letters in French can be tricky — for example, the x in deux is silent.',
  },
  {
    id: 'm2',
    title: 'Module 2 — Les Dates',
    mediaTitle: 'French Dates & Calendar — Beginner Guide',
    duration: '10 min',
    tags: ['Covers +5% Listening skill'],
    contentHeading: 'Module 2 — Les Dates',
    intro:
      'Talking about dates in French is essential for travel. Unlike English, French uses cardinal numbers for most dates — only the first of the month uses "premier."',
    insight:
      'In French, the date format is day/month/year. Say "le quinze juillet" for July 15th. "Le premier" is the sole exception using an ordinal.',
    vocab: [
      { word: 'janvier', translation: 'January' },
      { word: 'juillet', translation: 'July' },
      { word: 'lundi', translation: 'Monday' },
      { word: 'samedi', translation: 'Saturday' },
      { word: 'aujourd\'hui', translation: 'today' },
      { word: 'demain', translation: 'tomorrow' },
    ],
    practice:
      'Try reading today\'s date aloud in French. Combine the day, month, and year using the patterns above.',
  },
  {
    id: 'm3',
    title: "Module 3 — L'heure (Time)",
    mediaTitle: 'Telling Time in French — Complete Guide',
    duration: '8 min',
    tags: ['Interactive quiz included', 'Covers +6% Speaking skill'],
    contentHeading: "Module 3 — L'heure (Time)",
    intro:
      'Telling time in French uses a 24-hour clock in formal contexts, but everyday speech typically uses a 12-hour format with "du matin" (morning) and "du soir" (evening).',
    insight:
      '"Il est midi" means noon; "Il est minuit" means midnight. For quarter-past use "et quart," for half-past use "et demie," and for quarter-to use "moins le quart."',
    vocab: [
      { word: 'il est…', translation: 'it is…' },
      { word: 'midi', translation: 'noon' },
      { word: 'minuit', translation: 'midnight' },
      { word: 'et quart', translation: 'quarter past' },
      { word: 'et demie', translation: 'half past' },
      { word: 'moins le quart', translation: 'quarter to' },
    ],
    practice:
      'Ask a partner "Quelle heure est-il?" (What time is it?) and practice responding with different hours.',
  },
];

const OVERVIEW_ITEMS: ModuleItem[] = MODULES.map((m) => ({
  id: m.id,
  title: m.title,
}));

const WELCOME_MSG = (sessionIndex: number) =>
  `Welcome to Session ${sessionIndex}! We're covering this session's content. Ready to start?`;

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export function LearningSessionPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const sessionId = (location.state as { sessionId?: string } | null)?.sessionId ?? DEFAULT_SESSION_ID;
  const session = getSessionById(sessionId) ?? getSessionById(DEFAULT_SESSION_ID)!;
  const breadcrumb = `${BREADCRUMB_GOAL} → Session ${session.index}`;
  const sessionTitle = session.title;

  const [moduleIndex, setModuleIndex] = useState(0);
  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState<{ from: 'mentor' | 'user'; text: string; time: string }[]>([
    { from: 'mentor', text: WELCOME_MSG(session.index), time: 'just now' },
  ]);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  const mod = MODULES[moduleIndex];
  const progressPct = Math.round(((moduleIndex + 1) / MODULES.length) * 100);

  const handlePrev = useCallback(() => {
    if (moduleIndex <= 0) return;
    setModuleIndex((i) => i - 1);
    contentRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, [moduleIndex]);

  const handleNext = useCallback(() => {
    if (moduleIndex >= MODULES.length - 1) {
      navigate('/learning-path');
      return;
    }
    setModuleIndex((i) => i + 1);
    contentRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, [moduleIndex, navigate]);

  const handleJumpModule = useCallback((index: number) => {
    setModuleIndex(index);
    contentRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const handleSendChat = useCallback(() => {
    const text = chatInput.trim();
    if (!text) return;
    setMessages((prev) => [...prev, { from: 'user', text, time: 'just now' }]);
    setChatInput('');
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          from: 'mentor',
          text: 'Good question! Try repeating the vocab aloud 3 times — it helps with memory.',
          time: 'just now',
        },
      ]);
    }, 600);
  }, [chatInput]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── Center content ── */}
      <div className="flex-1 flex flex-col overflow-hidden bg-white border-r border-slate-200">
        {/* Header strip */}
        <div className="shrink-0 px-6 py-3 border-b border-slate-100 bg-white">
          <p className="text-xs text-slate-500">
            {breadcrumb}
          </p>
          <div className="flex items-center justify-between mt-1 gap-4">
            <h1 className="text-xl font-bold text-slate-900">{sessionTitle}</h1>
            <div className="flex items-center gap-3 text-sm text-slate-500">
              <span>Module {moduleIndex + 1} of {MODULES.length}</span>
              <div className="flex items-center gap-2">
                <div className="w-24 h-1.5 rounded-full bg-slate-200">
                  <div
                    className="h-1.5 rounded-full bg-primary-500 transition-all duration-300"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <span className="font-semibold text-slate-700 w-8">{progressPct}%</span>
              </div>
            </div>
          </div>
        </div>

        {/* Scrollable body */}
        <div ref={contentRef} className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {/* Video / media card */}
          <div className="flex items-center gap-4 p-4 rounded-xl border border-slate-200 bg-slate-50">
            <button
              type="button"
              className="w-12 h-12 rounded-full bg-primary-600 text-white flex items-center justify-center shrink-0 hover:bg-primary-700 transition-colors"
              aria-label="Play"
            >
              <svg className="w-5 h-5 ml-0.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5.14v14l11-7-11-7z" />
              </svg>
            </button>
            <div className="min-w-0">
              <p className="font-semibold text-slate-900">{mod.mediaTitle}</p>
              <div className="flex items-center gap-3 mt-1 text-xs text-slate-500 flex-wrap">
                <span className="flex items-center gap-1">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <circle cx="12" cy="12" r="10" />
                    <path strokeLinecap="round" d="M12 6v6l4 2" />
                  </svg>
                  {mod.duration}
                </span>
                {mod.tags.map((t) => (
                  <span key={t}>{t}</span>
                ))}
              </div>
            </div>
          </div>

          {/* Module content */}
          <div className="space-y-4">
            <h2 className="text-lg font-bold text-slate-900">{mod.contentHeading}</h2>
            <p className="text-sm text-slate-600 leading-relaxed">{mod.intro}</p>
            <blockquote className="border-l-4 border-slate-300 bg-slate-100 pl-4 pr-3 py-3 rounded-r-lg text-sm text-slate-700">
              <span className="font-semibold flex items-center gap-1.5">
                <span>💡</span> Key insight:
              </span>{' '}
              {mod.insight}
            </blockquote>
            <div className="grid grid-cols-2 gap-2">
              {mod.vocab.map((v) => (
                <div
                  key={v.word}
                  className="flex items-center justify-between px-3 py-2.5 bg-slate-100 border border-slate-200 rounded-lg text-sm"
                >
                  <span className="font-semibold text-slate-900">{v.word}</span>
                  <span className="text-slate-500">{v.translation}</span>
                </div>
              ))}
            </div>
            <p className="text-sm text-slate-600 leading-relaxed">{mod.practice}</p>
          </div>
        </div>

        {/* Bottom nav */}
        <div className="shrink-0 px-6 py-4 border-t border-slate-200 bg-white flex items-center justify-between gap-4">
          <Button
            variant="secondary"
            size="sm"
            onClick={handlePrev}
            disabled={moduleIndex === 0}
          >
            <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
            </svg>
            Previous: {moduleIndex > 0 ? MODULES[moduleIndex - 1].title.split('—')[1]?.trim() ?? 'Previous' : '—'}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => navigate('/learning-path')}>
            ← Back to Path
          </Button>
          <Button variant="primary" size="sm" onClick={handleNext}>
            {moduleIndex < MODULES.length - 1 ? (
              <>
                Next Module →
              </>
            ) : (
              'Finish Session ✓'
            )}
          </Button>
        </div>
      </div>

      {/* ── Right panel ── */}
      <div className="w-72 flex flex-col bg-white border-l border-slate-200 overflow-hidden shrink-0">
        {/* Mentor AI */}
        <div className="shrink-0 px-4 py-3 border-b border-slate-200">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-primary-600 text-white flex items-center justify-center text-sm font-bold shrink-0">
              AI
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-900">Mentor AI</p>
              <p className="text-xs text-slate-500 flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                Active — adapted to your style
              </p>
            </div>
          </div>
        </div>

        {/* Session Overview */}
        <div className="shrink-0 px-4 py-3 border-b border-slate-200">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Session Overview</p>
          <ul className="space-y-1">
            {OVERVIEW_ITEMS.map((item, i) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => handleJumpModule(i)}
                  className={cn(
                    'w-full text-left px-3 py-2 rounded-lg text-sm transition-colors',
                    i === moduleIndex ? 'bg-slate-100 text-slate-900 font-medium' : 'text-slate-600 hover:bg-slate-50',
                  )}
                >
                  {item.title}
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* Chat messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={cn('flex flex-col text-sm', msg.from === 'user' ? 'items-end' : 'items-start')}
            >
              <div
                className={cn(
                  'px-3 py-2 rounded-xl max-w-[95%]',
                  msg.from === 'mentor' ? 'bg-slate-100 text-slate-700' : 'bg-primary-500 text-white',
                )}
              >
                {msg.text}
              </div>
              <span className="text-xs text-slate-400 mt-0.5">{msg.time}</span>
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>

        {/* Chat input */}
        <div className="shrink-0 p-3 border-t border-slate-200">
          <form
            className="flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              handleSendChat();
            }}
          >
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Ask anything about this module..."
              className="flex-1 text-sm px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-300 focus:border-primary-400"
            />
            <button
              type="submit"
              disabled={!chatInput.trim()}
              className="w-8 h-8 rounded-lg bg-primary-600 text-white flex items-center justify-center hover:bg-primary-700 disabled:opacity-40 shrink-0"
              aria-label="Send"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.269 20.876L5.999 12zm0 0h7.5" />
              </svg>
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
