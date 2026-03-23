import { cn } from '@/lib/cn';
import {
  FALLBACK_CONTENT_BIAS_DISCLAIMER,
  FALLBACK_PROFILE_FAIRNESS_DISCLAIMER,
} from './ethicsCopy';

function severityIcon(severity: string): string {
  return ({ low: '🟡', medium: '🟠', high: '🔴' } as const)[severity as 'low' | 'medium' | 'high'] ?? '🟡';
}

export function ContentBiasAuditPanel({ audit }: { audit: Record<string, unknown> | null }) {
  const disclaimer =
    (typeof audit?.ethical_disclaimer === 'string' && audit.ethical_disclaimer.trim()) ||
    FALLBACK_CONTENT_BIAS_DISCLAIMER;

  const risk = typeof audit?.overall_bias_risk === 'string' ? audit.overall_bias_risk : 'low';
  const biasFlags = Array.isArray(audit?.bias_flags) ? audit.bias_flags : [];
  const deterministicFlags = Array.isArray(audit?.deterministic_flags) ? audit.deterministic_flags : [];

  return (
    <div className="space-y-3">
      <div
        className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-slate-800 shadow-sm"
        role="status"
      >
        {disclaimer}
      </div>

      {audit && (risk === 'medium' || risk === 'high') && (
        <div
          className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"
          role="alert"
        >
          {risk === 'medium' ? 'Moderate' : 'High'} content bias risk detected:{' '}
          {Number(audit.flagged_section_count ?? 0)} of {Number(audit.audited_section_count ?? 0)} sections
          flagged. Review the details below.
        </div>
      )}

      {audit && (biasFlags.length > 0 || deterministicFlags.length > 0) && (
        <details className="group rounded-xl border border-slate-200 bg-white text-sm shadow-sm">
          <summary className="cursor-pointer select-none px-4 py-3 font-medium text-slate-700 hover:bg-slate-50">
            View content bias audit details
          </summary>
          <div className="space-y-4 border-t border-slate-100 px-4 py-4 text-slate-700">
            {biasFlags.length > 0 && (
              <div className="space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Content bias flags</p>
                {biasFlags.map((raw, i) => {
                  const flag = raw as Record<string, unknown>;
                  const sev = String(flag.severity ?? 'low');
                  return (
                    <div key={i} className="rounded-lg border border-slate-100 bg-slate-50/80 p-3 text-xs leading-relaxed">
                      <p className="font-medium text-slate-900">
                        {severityIcon(sev)} {String(flag.section_title ?? 'Unknown')} —{' '}
                        <span className="italic">{String(flag.bias_category ?? '')}</span> ({sev})
                      </p>
                      {flag.explanation != null && (
                        <p className="mt-2 text-slate-700">{String(flag.explanation)}</p>
                      )}
                      {flag.suggestion != null && (
                        <p className="mt-1 text-slate-600">
                          <span className="font-medium">Suggestion:</span> {String(flag.suggestion)}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {deterministicFlags.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Language bias warnings
                </p>
                {deterministicFlags.map((raw, i) => {
                  const flag = raw as Record<string, unknown>;
                  return (
                    <div key={i} className="rounded-lg border border-amber-100 bg-amber-50/60 p-3 text-xs text-slate-800">
                      <p>⚠️ {String(flag.explanation ?? '')}</p>
                      {flag.suggestion != null && (
                        <p className="mt-1">
                          <span className="font-medium">Suggestion:</span> {String(flag.suggestion)}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

export function ChatbotBiasAuditPanel({ audit }: { audit: Record<string, unknown> | null }) {
  if (!audit) return null;

  const risk = typeof audit.overall_bias_risk === 'string' ? audit.overall_bias_risk : 'low';
  const biasFlags = Array.isArray(audit.bias_flags) ? audit.bias_flags : [];
  const deterministicFlags = Array.isArray(audit.deterministic_flags) ? audit.deterministic_flags : [];

  if (risk !== 'medium' && risk !== 'high' && biasFlags.length === 0 && deterministicFlags.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      {(risk === 'medium' || risk === 'high') && (
        <div
          className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[11px] leading-snug text-amber-950"
          role="alert"
        >
          {risk === 'medium' ? 'Moderate' : 'High'} bias risk detected:{' '}
          {Number(audit.flagged_message_count ?? 0)} of {Number(audit.audited_message_count ?? 0)} messages flagged.
          Review the details below.
        </div>
      )}

      {(biasFlags.length > 0 || deterministicFlags.length > 0) && (
        <details className="group rounded-lg border border-slate-200 bg-white text-[11px] shadow-sm">
          <summary className="cursor-pointer select-none px-3 py-2 font-medium text-slate-700 hover:bg-slate-50">
            View chatbot bias audit details
          </summary>
          <div className="max-h-48 space-y-3 overflow-y-auto border-t border-slate-100 px-3 py-2 text-slate-700">
            {biasFlags.length > 0 && (
              <div className="space-y-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Chatbot bias flags</p>
                {biasFlags.map((raw, i) => {
                  const flag = raw as Record<string, unknown>;
                  const sev = String(flag.severity ?? 'low');
                  return (
                    <div key={i} className="rounded-md border border-slate-100 bg-slate-50 p-2 leading-relaxed">
                      <p className="font-medium text-slate-900">
                        {severityIcon(sev)} Message {String(flag.message_index ?? 0)} —{' '}
                        <span className="italic">{String(flag.bias_category ?? '')}</span> ({sev})
                      </p>
                      {flag.explanation != null && <p className="mt-1">{String(flag.explanation)}</p>}
                      {flag.suggestion != null && (
                        <p className="mt-1 text-slate-600">
                          <span className="font-medium">Suggestion:</span> {String(flag.suggestion)}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {deterministicFlags.length > 0 && (
              <div className="space-y-2">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                  Language &amp; tone warnings
                </p>
                {deterministicFlags.map((raw, i) => {
                  const flag = raw as Record<string, unknown>;
                  return (
                    <div key={i} className="rounded-md border border-amber-100 bg-amber-50/80 p-2">
                      <p>⚠️ {String(flag.explanation ?? '')}</p>
                      {flag.suggestion != null && (
                        <p className="mt-1">
                          <span className="font-medium">Suggestion:</span> {String(flag.suggestion)}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

/** Set to `true` to show the amber banner + “View bias audit details” on Skill Gap again. */
const SHOW_SKILL_GAP_BIAS_AUDIT_UI = false;

export function SkillGapBiasAuditPanel({ audit }: { audit: Record<string, unknown> | null }) {
  if (!SHOW_SKILL_GAP_BIAS_AUDIT_UI) return null;

  if (!audit) return null;

  const risk = typeof audit.overall_bias_risk === 'string' ? audit.overall_bias_risk : 'low';
  const biasFlags = Array.isArray(audit.bias_flags) ? audit.bias_flags : [];
  const calibrationFlags = Array.isArray(audit.confidence_calibration_flags)
    ? audit.confidence_calibration_flags
    : [];

  if (risk !== 'medium' && risk !== 'high' && biasFlags.length === 0 && calibrationFlags.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {(risk === 'medium' || risk === 'high') && (
        <div
          className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"
          role="alert"
        >
          {risk === 'medium' ? 'Moderate' : 'High'} bias risk detected: {Number(audit.flagged_skill_count ?? 0)} of{' '}
          {Number(audit.audited_skill_count ?? 0)} skills flagged. Review the details below and consider adjusting
          the assessments.
        </div>
      )}

      {(biasFlags.length > 0 || calibrationFlags.length > 0) && (
        <details className="group rounded-xl border border-[#DCE7EA] bg-white text-sm shadow-sm">
          <summary className="cursor-pointer select-none px-4 py-3 font-medium text-[#16324A] hover:bg-[#F6FAFB]">
            View bias audit details
          </summary>
          <div className="space-y-4 border-t border-[#DCE7EA] px-4 py-4 text-[#16324A]">
            {biasFlags.length > 0 && (
              <div className="space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-[#7E92A3]">Bias flags</p>
                {biasFlags.map((raw, i) => {
                  const flag = raw as Record<string, unknown>;
                  const sev = String(flag.severity ?? 'low');
                  return (
                    <div key={i} className="rounded-lg border border-[#E8F0F2] bg-[#F7FBFC] p-3 text-xs leading-relaxed">
                      <p className="font-medium">
                        {severityIcon(sev)} {String(flag.skill_name ?? 'Unknown')} —{' '}
                        <span className="italic">{String(flag.bias_category ?? '')}</span> ({sev})
                      </p>
                      {flag.explanation != null && <p className="mt-2 text-[#5F7486]">{String(flag.explanation)}</p>}
                      {flag.suggestion != null && (
                        <p className="mt-1 text-[#5F7486]">
                          <span className="font-medium">Suggestion:</span> {String(flag.suggestion)}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {calibrationFlags.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-[#7E92A3]">
                  Confidence calibration warnings
                </p>
                {calibrationFlags.map((raw, i) => {
                  const flag = raw as Record<string, unknown>;
                  return (
                    <div key={i} className="rounded-lg border border-amber-100 bg-amber-50/80 px-3 py-2 text-xs text-[#16324A]">
                      ⚠️ <span className="font-medium">{String(flag.skill_name ?? 'Unknown')}</span>:{' '}
                      {String(flag.issue ?? '')}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

export function ProfileFairnessPanel({
  fairness,
  className,
  /** When true, only the ethical disclaimer box is shown (no fairness risk banner or details). */
  disclaimerOnly = false,
}: {
  fairness: Record<string, unknown> | null | undefined;
  className?: string;
  disclaimerOnly?: boolean;
}) {
  const disclaimer =
    (typeof fairness?.ethical_disclaimer === 'string' && fairness.ethical_disclaimer.trim()) ||
    FALLBACK_PROFILE_FAIRNESS_DISCLAIMER;

  const risk =
    typeof fairness?.overall_fairness_risk === 'string' ? fairness.overall_fairness_risk : 'low';
  const fairnessFlags = Array.isArray(fairness?.fairness_flags) ? fairness.fairness_flags : [];
  const deviationFlags = Array.isArray(fairness?.fslsm_deviation_flags) ? fairness.fslsm_deviation_flags : [];

  const hasElevatedRisk = fairness != null && (risk === 'medium' || risk === 'high');
  const hasDetails = fairnessFlags.length > 0 || deviationFlags.length > 0;
  const showFairnessFollowUp = !disclaimerOnly && (hasElevatedRisk || hasDetails);

  return (
    <div className={cn('space-y-3', className)}>
      <section
        className="rounded-xl border border-sky-200 bg-sky-50 px-4 pt-4 pb-3 text-sm text-slate-800 shadow-sm"
        role="status"
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-sky-900/80">Ethical disclaimer</p>
        <p className="mt-2 text-sm leading-relaxed text-slate-800">{disclaimer}</p>
      </section>

      {showFairnessFollowUp && (
        <div className="space-y-3">
          {hasElevatedRisk && (
            <div
              className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"
              role="alert"
            >
              {risk === 'medium' ? 'Moderate' : 'High'} fairness risk detected:{' '}
              {Number(fairness?.flagged_fields_count ?? 0)} of {Number(fairness?.checked_fields_count ?? 0)} fields
              flagged. Review the details below and consider adjusting the profile.
            </div>
          )}

          {hasDetails && (
            <details className="group rounded-xl border border-[#DCE7EA] bg-white text-sm shadow-sm">
              <summary className="cursor-pointer select-none px-4 py-3 font-medium text-[#16324A] hover:bg-[#F6FAFB]">
                View profile fairness details
              </summary>
              <div className="space-y-4 border-t border-[#DCE7EA] px-4 py-4 text-[#16324A]">
                {fairnessFlags.length > 0 && (
                  <div className="space-y-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-[#7E92A3]">Fairness flags</p>
                    {fairnessFlags.map((raw, i) => {
                      const flag = raw as Record<string, unknown>;
                      const sev = String(flag.severity ?? 'low');
                      return (
                        <div key={i} className="rounded-lg border border-[#E8F0F2] bg-[#F7FBFC] p-3 text-xs leading-relaxed">
                          <p className="font-medium">
                            {severityIcon(sev)} {String(flag.field_name ?? 'Unknown')} —{' '}
                            <span className="italic">{String(flag.fairness_category ?? '')}</span> ({sev})
                          </p>
                          {flag.explanation != null && (
                            <p className="mt-2 text-[#5F7486]">{String(flag.explanation)}</p>
                          )}
                          {flag.suggestion != null && (
                            <p className="mt-1 text-[#5F7486]">
                              <span className="font-medium">Suggestion:</span> {String(flag.suggestion)}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
                {deviationFlags.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-[#7E92A3]">
                      FSLSM deviation warnings
                    </p>
                    {deviationFlags.map((raw, i) => {
                      const flag = raw as Record<string, unknown>;
                      return (
                        <div key={i} className="rounded-lg border border-amber-100 bg-amber-50/80 p-3 text-xs">
                          ⚠️ <span className="font-medium">{String(flag.dimension ?? 'Unknown')}</span>: Persona
                          baseline {String(flag.persona_value ?? '?')} → Profile value{' '}
                          {String(flag.profile_value ?? '?')} (deviation: {String(flag.deviation ?? '?')})
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
