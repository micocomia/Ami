import { useRef, useState } from 'react';
import { Button } from '@/components/ui';
import { FslsmSliders } from './FslsmSliders';
import { cn } from '@/lib/cn';
import { useUpdateLearningPreferences, useUpdateLearnerInformation } from '@/api/endpoints/content';
import { useExtractPdfText } from '@/api/endpoints/pdf';
import { useAppConfig } from '@/api/endpoints/config';
import type { GoalAggregate, LearnerProfile } from '@/types';

interface EditProfileModalProps {
  activeGoal: GoalAggregate;
  userId: string;
  onClose: () => void;
  onUpdate: (updatedGoal: GoalAggregate) => void;
}

export function EditProfileModal({ activeGoal, userId, onClose, onUpdate }: EditProfileModalProps) {
  const { data: config } = useAppConfig();
  const updatePrefsMutation = useUpdateLearningPreferences();
  const updateInfoMutation = useUpdateLearnerInformation();
  const extractPdf = useExtractPdfText();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [activeTab, setActiveTab] = useState<'preferences' | 'information'>('preferences');

  // FSLSM edit state
  const currentProfile = activeGoal.learner_profile ?? {};
  const currentDims = (currentProfile.learning_preferences?.fslsm_dimensions as Record<string, number> | undefined) ?? {};
  const [fslsmValues, setFslsmValues] = useState<Record<string, number>>(currentDims);

  // Learner information state
  const [infoText, setInfoText] = useState<string>(
    (currentProfile.learner_information as string | undefined) ?? '',
  );
  const [pdfFilename, setPdfFilename] = useState<string | null>(null);
  const [pdfText, setPdfText] = useState('');

  const handleFslsmChange = (dim: string, value: number) => {
    setFslsmValues((prev) => ({ ...prev, [dim]: value }));
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPdfFilename(file.name);
    try {
      const result = await extractPdf.mutateAsync(file);
      setPdfText((result as { text?: string }).text ?? '');
    } catch {
      setPdfText('');
    }
  };

  const handleSavePreferences = async () => {
    const updatedProfile: LearnerProfile = {
      ...currentProfile,
      learning_preferences: {
        ...(currentProfile.learning_preferences ?? {}),
        fslsm_dimensions: fslsmValues,
      },
    };
    try {
      const res = await updatePrefsMutation.mutateAsync({
        learner_profile: JSON.stringify(updatedProfile),
        learner_interactions: '{}',
        user_id: userId,
        goal_id: activeGoal.id,
      });
      onUpdate({ ...activeGoal, learner_profile: res.learner_profile });
      onClose();
    } catch { /* ignore */ }
  };

  const handleSaveInformation = async () => {
    if (!infoText.trim() && !pdfText.trim()) return;
    try {
      const res = await updateInfoMutation.mutateAsync({
        learner_profile: JSON.stringify(currentProfile),
        updated_learner_information: infoText,
        resume_text: pdfText || undefined,
        user_id: userId,
        goal_id: activeGoal.id,
      });
      onUpdate({ ...activeGoal, learner_profile: res.learner_profile });
      onClose();
    } catch { /* ignore */ }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h2 className="font-semibold text-slate-800">Edit Profile</h2>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-100 px-6">
          {(['preferences', 'information'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={cn(
                'py-3 px-1 mr-6 text-sm font-medium border-b-2 transition-colors',
                activeTab === tab
                  ? 'border-primary-500 text-primary-700'
                  : 'border-transparent text-slate-500 hover:text-slate-700',
              )}
            >
              {tab === 'preferences' ? 'Learning Preferences' : 'Learner Information'}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {activeTab === 'preferences' ? (
            <div className="space-y-4">
              <p className="text-sm text-slate-500">
                Adjust your FSLSM learning style dimensions. These affect how content is presented to you.
              </p>
              <FslsmSliders values={fslsmValues} config={config} onChange={handleFslsmChange} />
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-slate-500">
                Update your background information. This helps Ami personalise content to your experience level.
              </p>
              <textarea
                value={infoText}
                onChange={(e) => setInfoText(e.target.value)}
                rows={6}
                placeholder="Describe your background, experience, and interests…"
                className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-400 resize-none"
              />
              <input ref={fileInputRef} type="file" accept=".pdf" className="hidden" onChange={handleFileChange} />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="w-full flex items-center gap-3 text-left px-4 py-3 rounded-lg border border-dashed border-slate-300 bg-slate-50 hover:bg-slate-100 transition-colors"
              >
                <svg className="w-5 h-5 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                </svg>
                <span className="text-sm text-slate-600">
                  {extractPdf.isPending ? 'Extracting…' : pdfFilename ? pdfFilename : 'Upload PDF resume (optional)'}
                </span>
              </button>
              {pdfText && <p className="text-xs text-green-600">PDF text extracted successfully.</p>}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-100">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          {activeTab === 'preferences' ? (
            <Button onClick={handleSavePreferences} loading={updatePrefsMutation.isPending}>
              Save Preferences
            </Button>
          ) : (
            <Button
              onClick={handleSaveInformation}
              loading={updateInfoMutation.isPending}
              disabled={!infoText.trim() && !pdfText.trim()}
            >
              Save Information
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
