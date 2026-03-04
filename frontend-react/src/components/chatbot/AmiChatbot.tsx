import { useState, useRef, useEffect } from 'react';
import { useChatWithTutor } from '@/api/endpoints/chat';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/hooks/useActiveGoal';
import { cn } from '@/lib/cn';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

const MAX_HISTORY = 20;

export function AmiChatbot() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { userId } = useAuthContext();
  const { updateGoal } = useGoalsContext();
  const activeGoal = useActiveGoal();
  const chatMutation = useChatWithTutor();

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, open]);

  const sendMessage = () => {
    const text = input.trim();
    if (!text || chatMutation.isPending) return;

    const newMessages: Message[] = [...messages, { role: 'user', content: text }];
    setMessages(newMessages);
    setInput('');

    const last20 = newMessages.slice(-MAX_HISTORY);

    chatMutation.mutate(
      {
        messages: JSON.stringify(last20),
        learner_profile: JSON.stringify(activeGoal?.learner_profile ?? {}),
        user_id: userId ?? undefined,
        goal_id: activeGoal?.id,
        learner_information: activeGoal?.learner_profile?.learner_information,
      },
      {
        onSuccess: (res) => {
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: res.response },
          ]);
          if (res.updated_learner_profile && activeGoal) {
            updateGoal(activeGoal.id, {
              ...activeGoal,
              learner_profile: res.updated_learner_profile,
            });
          }
        },
        onError: () => {
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: 'Sorry, I ran into an error. Please try again.' },
          ]);
        },
      },
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <>
      {/* Floating button */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-primary-600 text-white shadow-lg hover:bg-primary-700 transition-colors flex items-center justify-center"
        aria-label="Open Ami chatbot"
      >
        {open ? (
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        )}
      </button>

      {/* Drawer */}
      <div
        className={cn(
          'fixed bottom-0 right-0 z-40 flex flex-col bg-white border-l border-slate-200 shadow-2xl transition-transform duration-300',
          'w-full sm:w-96 h-[560px] sm:h-[600px] sm:bottom-6 sm:right-6 sm:rounded-xl sm:border',
          open ? 'translate-x-0' : 'translate-x-full',
        )}
        style={{ maxHeight: '85vh' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-primary-600 text-white flex items-center justify-center text-sm font-bold">
              A
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-800">Ami</p>
              <p className="text-xs text-slate-500">Your AI tutor</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
          {messages.length === 0 && (
            <div className="text-center text-slate-400 text-sm mt-8">
              <p className="text-2xl mb-2">👋</p>
              <p>Hi! I&apos;m Ami, your learning tutor.</p>
              <p className="mt-1">Ask me anything about your learning goals!</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={cn(
                'max-w-[85%] rounded-xl px-3 py-2 text-sm',
                msg.role === 'user'
                  ? 'ml-auto bg-primary-600 text-white rounded-br-sm'
                  : 'mr-auto bg-slate-100 text-slate-800 rounded-bl-sm',
              )}
            >
              {msg.content}
            </div>
          ))}
          {chatMutation.isPending && (
            <div className="mr-auto bg-slate-100 text-slate-500 rounded-xl rounded-bl-sm px-3 py-2 text-sm">
              <span className="inline-flex gap-1">
                <span className="animate-bounce" style={{ animationDelay: '0ms' }}>•</span>
                <span className="animate-bounce" style={{ animationDelay: '150ms' }}>•</span>
                <span className="animate-bounce" style={{ animationDelay: '300ms' }}>•</span>
              </span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="px-3 py-3 border-t border-slate-200 shrink-0">
          <div className="flex gap-2 items-end">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask Ami anything..."
              rows={1}
              className="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent max-h-32 overflow-y-auto"
              style={{ minHeight: '38px' }}
            />
            <button
              type="button"
              onClick={sendMessage}
              disabled={!input.trim() || chatMutation.isPending}
              className="shrink-0 w-9 h-9 rounded-lg bg-primary-600 text-white flex items-center justify-center hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              aria-label="Send"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
              </svg>
            </button>
          </div>
          <p className="text-xs text-slate-400 mt-1.5 text-center">Press Enter to send · Shift+Enter for newline</p>
        </div>
      </div>
    </>
  );
}
