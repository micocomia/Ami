import { useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, InputField } from '@/components/ui';
import { cn } from '@/lib/cn';
import { usePersonas } from '@/api/endpoints/config';
import { useExtractPdfText } from '@/api/endpoints/pdf';

export function OnboardingPage() {
  const navigate = useNavigate();
  const { data: personasData, isLoading: personasLoading } = usePersonas();
  const extractPdf = useExtractPdfText();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [learningGoal, setLearningGoal] = useState('');
  const [selectedPersonaKey, setSelectedPersonaKey] = useState<string | null>(null);
  const [resumeText, setResumeText] = useState('');
  const [pdfFilename, setPdfFilename] = useState<string | null>(null);

  const personas = personasData?.personas ?? {};
  const personaKeys = Object.keys(personas);

  function buildLearnerInformation(personaKey: string | null, resumeTxt: string): string {
    let prefix = '';
    if (personaKey && personas[personaKey]) {
      const dims = personas[personaKey].fslsm_dimensions;
      const dimStr = Object.entries(dims)
        .map(([k, v]) => `${k}=${v}`)
        .join(', ');
      prefix = `Learning Persona: ${personaKey} (initial FSLSM: ${dimStr}). `;
    }
    return prefix + resumeTxt;
  }

  const handleFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setPdfFilename(file.name);
      try {
        const result = await extractPdf.mutateAsync(file);
        setResumeText((result as { text?: string }).text ?? '');
      } catch {
        setResumeText('');
      }
    },
    [extractPdf],
  );

  const canBeginLearning = learningGoal.trim().length > 0 && selectedPersonaKey !== null;

  const handleBeginLearning = useCallback(() => {
    if (!canBeginLearning) return;
    const learnerInformation = buildLearnerInformation(selectedPersonaKey, resumeText);
    navigate('/skill-gap', {
      state: {
        goal: learningGoal.trim(),
        personaKey: selectedPersonaKey,
        learnerInformation,
        isGoalManagementFlow: false,
      },
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canBeginLearning, learningGoal, selectedPersonaKey, resumeText, navigate]);

  return (
    <div className="flex flex-col min-h-0 flex-1">
      <div className="flex-1 min-h-0 overflow-y-auto">
        {/* Hero */}
        <section className="text-center pt-8 pb-6 px-4">
          <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight">
            Welcome to <span className="text-primary-600">Ami</span>
          </h1>
          <p className="mt-3 text-lg text-slate-500 max-w-lg mx-auto leading-relaxed">
            Your personal adaptive learning companion.
            <br />
            No setup required — we&apos;ll adapt to you as we go.
          </p>
        </section>

        <section className="max-w-2xl w-full mx-auto px-4 space-y-6 pb-8">
          {/* Goal input */}
          <div>
            <p className="text-center text-sm font-medium text-slate-700 mb-2">
              What would you like to learn today?
            </p>
            <InputField
              placeholder="eg: learn english, python, data ..."
              value={learningGoal}
              onChange={(e) => setLearningGoal(e.target.value)}
            />
            <p className="mt-1 text-xs text-slate-500">
              Enter any topic you want to learn. The system will automatically refine your goal if
              needed and generate personalised content for you.
            </p>
          </div>

          {/* Persona cards */}
          <div>
            <p className="text-sm font-medium text-slate-700 mb-3">Select your learning persona</p>
            {personasLoading ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="h-24 bg-slate-100 rounded-xl animate-pulse" />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {personaKeys.map((key) => {
                  const persona = personas[key];
                  const isSelected = selectedPersonaKey === key;
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setSelectedPersonaKey(isSelected ? null : key)}
                      className={cn(
                        'text-left rounded-xl border-2 p-4 transition-all text-sm',
                        'hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400',
                        isSelected
                          ? 'border-primary-500 bg-primary-50 text-primary-800'
                          : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300',
                      )}
                    >
                      <span className="font-semibold block mb-1">{key}</span>
                      <span className="text-xs text-slate-500 leading-snug">{persona.description}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Resume upload */}
          <div>
            <p className="text-sm font-medium text-slate-700 mb-2">
              Upload your resume for a more personalised experience{' '}
              <span className="text-slate-400 font-normal">(optional)</span>
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={handleFileChange}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="w-full flex items-center gap-3 text-left px-4 py-3 rounded-lg border border-dashed border-slate-300 bg-white hover:bg-slate-50 transition-colors"
            >
              <svg className="w-5 h-5 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
              </svg>
              <span className="text-sm text-slate-600">
                {extractPdf.isPending
                  ? 'Extracting text…'
                  : pdfFilename
                  ? pdfFilename
                  : 'Click to upload PDF resume'}
              </span>
            </button>
            {resumeText && (
              <p className="mt-1 text-xs text-green-600">Resume text extracted successfully.</p>
            )}
          </div>

          {/* Data transparency */}
          <details className="text-sm border border-slate-200 rounded-lg">
            <summary className="px-4 py-3 cursor-pointer text-slate-600 font-medium select-none">
              How your data is used
            </summary>
            <div className="px-4 pb-4 pt-2 text-xs text-slate-500 space-y-2">
              <p><strong>What we collect:</strong> Your learning goal, selected persona, and optionally your resume text. During learning, we also record quiz scores and session timing.</p>
              <p><strong>AI-generated assessments:</strong> Skill levels, learner profiles, and learning content are generated by AI. They are estimates and may not fully reflect your actual abilities.</p>
              <p><strong>External services:</strong> Your learning goal and background are sent to an LLM provider to generate personalised content.</p>
              <p><strong>Your control:</strong> You can delete your account and all associated data at any time from the My Profile page.</p>
            </div>
          </details>
        </section>
      </div>

      {/* Bottom action bar */}
      <div className="border-t border-slate-100 px-4 py-4 bg-white">
        <div className="max-w-2xl mx-auto">
          <Button
            size="lg"
            onClick={handleBeginLearning}
            disabled={!canBeginLearning}
            className="w-full"
          >
            Begin Learning
          </Button>
          {!canBeginLearning && (
            <p className="mt-2 text-center text-xs text-slate-400">
              Please enter a learning goal and select a learning persona to continue.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
