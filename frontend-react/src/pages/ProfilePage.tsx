import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { ProfileFairnessPanel } from '@/components/ethics';
import { Button, Modal } from '@/components/ui';
import { cn } from '@/lib/cn';
import { useAuthContext } from '@/context/AuthContext';
import { useSidebarCollapse } from '@/context/SidebarCollapseContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/context/GoalsContext';
import { useDeleteUserData, useUpdateLearnerInformation, useUpdateLearningPreferences } from '@/api/endpoints/content';
import { useBehavioralMetrics } from '@/api/endpoints/metrics';
import { useDeleteUser, useAuthMe } from '@/api/endpoints/auth';
import { useAppConfig, usePersonas } from '@/api/endpoints/config';
import { useExtractPdfText } from '@/api/endpoints/pdf';
import {
  getLearningStylePreference,
  setLearningStylePreference,
  type LearningStyleOption,
} from '@/lib/learningStylePreference';
import {
  getMemberSinceIso,
  formatMemberSinceDisplay,
  earliestGoalTimestampIso,
} from '@/lib/memberSince';
import {
  getAvatarDataUrl,
  setAvatarFromFile,
  clearAvatar,
} from '@/lib/avatarStorage';
import {
  getStoredResumeFileName,
  setStoredResume,
  clearStoredResume,
} from '@/lib/resumeStorage';
import type { LearnerProfile } from '@/types';

/**
 * Goals / profile APIs sometimes return `learner_profile` as a JSON string.
 * Without this, `learner_information` never updates in the UI after resume upload.
 */
function normalizeLearnerProfile(raw: unknown): LearnerProfile | undefined {
  if (raw == null) return undefined;
  if (typeof raw === 'string') {
    const s = raw.trim();
    if (!s) return undefined;
    try {
      const p = JSON.parse(s) as unknown;
      if (typeof p === 'object' && p !== null && !Array.isArray(p)) return p as LearnerProfile;
    } catch {
      return undefined;
    }
    return undefined;
  }
  if (typeof raw === 'object' && raw !== null && !Array.isArray(raw)) {
    return raw as LearnerProfile;
  }
  return undefined;
}

/** POST bodies expect JSON text; list APIs may return `learner_profile` already as a JSON string — avoid double-encoding. */
function serializeLearnerProfileForApi(raw: unknown): string {
  if (raw == null) return '{}';
  if (typeof raw === 'string') {
    const s = raw.trim();
    if (!s) return '{}';
    try {
      JSON.parse(s);
      return s;
    } catch {
      return JSON.stringify({ learner_information: s });
    }
  }
  return JSON.stringify(raw);
}

/** Backend may store `learner_information` as structured JSON; UI and edit payloads need a string. */
function learnerInformationToString(raw: unknown): string {
  if (raw == null) return '';
  if (typeof raw === 'string') return raw;
  if (typeof raw === 'object') {
    try {
      return JSON.stringify(raw, null, 2);
    } catch {
      return String(raw);
    }
  }
  return String(raw);
}

function formatDuration(secs: number): string {
  if (secs <= 0 || !Number.isFinite(secs)) return '—';
  if (secs < 60) return `${Math.round(secs)}s`;
  if (secs < 3600) return `${Math.round(secs / 60)}m`;
  const h = Math.floor(secs / 3600);
  const m = Math.round((secs % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

/** Right column card titles (Activity Summary, How You Learn, Talent Assets, Data & Account) — same level. */
const PROFILE_PAGE_SECTION_TITLE =
  'text-sm font-semibold uppercase tracking-wider text-slate-900';

/** Left column subsection labels (Education, Experience, …) — match weight/case; compact size for narrow column. */
const PROFILE_SIDEBAR_SECTION_LABEL =
  'text-xs font-semibold uppercase tracking-wider text-slate-900';

/** Strip onboarding/system prefixes so the profile reads as a bio. */
function displayLearnerInformationBody(text: string): string {
  let t = text.trim();
  t = t.replace(/^Learning style preference:\s*[^.]+\.\s*/i, '');
  t = t.replace(/^Learning Persona:\s[^.]+\([^)]*\)\.\s*/, '');
  return t.trim();
}

function normalizeBackgroundSnippet(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === 'string') {
    const s = value.trim();
    return s.length ? s : null;
  }
  if (Array.isArray(value)) {
    const parts = value
      .map((x) => (typeof x === 'string' ? x.trim() : JSON.stringify(x)))
      .filter(Boolean);
    return parts.length ? parts.join('\n') : null;
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
  return null;
}

const EDU_HINT =
  /\b(Master|Bachelor|B\.?\s*S\.?|B\.?\s*A\.?|M\.?\s*S\.?|M\.?\s*A\.?|Ph\.?\s*D|Doctorate|University|College|degree|diploma|concentration|School of|Faculty of|undergraduate|graduate|coursework|student at)\b/i;
const WORK_HINT =
  /\b(worked|employment|intern(?:ship)?|engineer|developer|manager|analyst|consultant|software|full[\s-]?time|part[\s-]?time|Corporation|Corp\.|Ltd\.|Inc\.|LLC|years? (?:of |at )|role as|position|Co-?op)\b/i;

/** Heuristic extraction from free-text learner_information (no LLM). */
function parseLearnerInformationSections(body: string): { education: string[]; work: string[] } {
  const education: string[] = [];
  const work: string[] = [];
  const t = body.trim();
  if (!t) return { education, work };

  const pushUnique = (arr: string[], item: string) => {
    const s = item.trim();
    if (s.length < 16) return;
    if (!arr.includes(s)) arr.push(s);
  };

  const paragraphs = t.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  const blocks = paragraphs.length > 0 ? paragraphs : [t];

  const classify = (p: string) => {
    const edu = EDU_HINT.test(p);
    const wo = WORK_HINT.test(p);
    if (edu && !wo) pushUnique(education, p);
    else if (wo && !edu) pushUnique(work, p);
    else if (edu && wo) {
      if (/\b(University|College|School of|Bachelor|Master|Ph\.?\s*D|concentration)\b/i.test(p)) pushUnique(education, p);
      else pushUnique(work, p);
    }
  };

  for (const p of blocks) {
    if (p.length > 400) {
      p.split(/(?<=[.!?])\s+/).forEach((s) => classify(s.trim()));
    } else {
      classify(p);
    }
  }

  if (education.length === 0 && work.length === 0 && t.length > 40) {
    t.split(/(?<=[.!?])\s+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 20)
      .forEach((s) => {
        const edu = EDU_HINT.test(s);
        const wo = WORK_HINT.test(s);
        if (edu && !wo) pushUnique(education, s);
        else if (wo && !edu) pushUnique(work, s);
        else if (edu && wo) {
          if (/\b(University|College|Master|Bachelor|Ph\.?\s*D)\b/i.test(s)) pushUnique(education, s);
          else pushUnique(work, s);
        }
      });
  }

  return { education, work };
}

/** Raw strings → timeline entries (title / subtitle / optional status). */
interface ProfileTimelineEntry {
  title: string;
  subtitle?: string;
  status?: string;
  /** Full-width narrative (no ellipsis); sidebar scrolls when long. */
  subtitleFull?: boolean;
}

function shortenLine(s: string, max: number): string {
  const t = s.replace(/\s+/g, ' ').trim();
  if (t.length <= max) return t;
  const cut = t.slice(0, max);
  const sp = cut.lastIndexOf(' ');
  return `${sp > max * 0.5 ? cut.slice(0, sp) : cut}…`;
}

/** Optional date / range for timeline status line (portfolio-style: shown when parse finds it). */
function extractResumeTimeMarker(text: string): string | undefined {
  const t = text.replace(/\s+/g, ' ').trim();
  if (!t) return undefined;

  const range = t.match(
    /\b((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2}|present|current|now|today)\b/i,
  );
  if (range) {
    const end = /present|current|now|today/i.test(range[2]) ? 'Present' : range[2];
    return `${range[1]}–${end}`;
  }

  const monthRange = t.match(
    /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\s*[-–—]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b/i,
  );
  if (monthRange) return monthRange[0].replace(/\s+/g, ' ');
  const monthToPresent = t.match(
    /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\s*[-–—]\s*(?:Present|Current|Now)\b/i,
  );
  if (monthToPresent) return monthToPresent[0].replace(/\s+/g, ' ');

  const slash = t.match(/\b\d{1,2}\/\d{4}\s*[-–—]\s*\d{1,2}\/\d{4}\b/);
  if (slash) return slash[0];

  const cof = t.match(/\bclass of\s+((?:19|20)\d{2})\b/i);
  if (cof) return `Class of ${cof[1]}`;

  const grad = t.match(/\b(?:graduated|grad\.?)\s+((?:19|20)\d{2})\b/i);
  if (grad) return `Graduated ${grad[1]}`;

  const exp = t.match(/\b(?:expected|exp\.?)\s*(?:graduation|to graduate)?\s*[:.]?\s*((?:19|20)\d{2})\b/i);
  if (exp) return `Expected ${exp[1]}`;

  return undefined;
}

function inferDegreeLabel(text: string): string | undefined {
  const structured = extractEducationDegreeLine(text);
  if (structured?.trim()) return structured.trim();
  const t = text.replace(/\s+/g, ' ').trim();
  const m = t.match(
    /\b((?:Bachelor|Master|Ph\.?\s*D|Doctorate|Associate|Diploma|Certificate|MBA|B\.?A\.?|B\.?S\.?|M\.?S\.?|M\.?A\.?)\s+(?:of|in)\s+[^.;]{2,62})/i,
  );
  if (m) return m[1].trim().replace(/\s+/g, ' ');
  const m2 = t.match(/\b(Ph\.?\s*D\.?\s*(?:in\s+)?[A-Za-z][^.;]{2,44})/i);
  if (m2) return m2[1].trim().replace(/\s+/g, ' ');
  return undefined;
}

/** Strip resume-style lead-ins before a role (e.g. "having worked as a Data Analyst" → "Data Analyst"). */
function stripNarrativeWorkPrefix(s: string): string {
  let t = s.replace(/\s+/g, ' ').trim();
  let prev = '';
  while (prev !== t) {
    prev = t;
    t = t
      .replace(/^having\s+worked\s+as\s+(?:a\s+)?/i, '')
      .replace(/^worked\s+as\s+(?:a\s+)?/i, '')
      .replace(/^and\s+as\s+a\s+/i, '')
      .replace(/^as\s+a\s+/i, '')
      .replace(/^and\s+/i, '')
      .trim();
  }
  return t;
}

/** Split "… at X and as a Senior … at Y" into clauses so each can match Role at Company. */
function splitWorkRoleClauses(lines: string[]): string[] {
  const out: string[] = [];
  for (const line of lines) {
    const t = line.replace(/\s+/g, ' ').trim();
    if (!t) continue;
    const parts = t.split(/\s+and\s+as\s+a\s+/i).map((s) => s.trim()).filter(Boolean);
    if (parts.length <= 1) {
      out.push(t);
      continue;
    }
    out.push(parts[0]);
    for (let i = 1; i < parts.length; i += 1) {
      out.push(`as a ${parts[i]}`);
    }
  }
  return out;
}

/** Degree / program line only (no institution, no narrative). */
function extractEducationDegreeLine(text: string): string | undefined {
  const t = text.replace(/\s+/g, ' ').trim();

  const concPair = t.match(
    /\b(?:Master|Bachelor|PhD|Doctorate)\s+of\s+(.+?)\s+with\s+a\s+concentration\s+in\s+([A-Za-z0-9&\s-]+?)(?:\s+at\s+the|\s+at\s+[A-Z]|\s*$|\.)/i,
  );
  if (concPair) {
    const prog = concPair[1].trim().replace(/\s+/g, ' ');
    const conc = concPair[2].trim();
    const progShort = prog.length > 44 ? `${prog.split(/\s+/).slice(0, 6).join(' ')}…` : prog;
    return `${progShort} · ${conc}`;
  }

  const bsc = t.match(/\bBachelor\s+of\s+Science\s+in\s+([^.,]+?)(?:\s+from\s|\s+at\s|$|\.)/i);
  if (bsc) return `BSc · ${bsc[1].trim()}`;

  const ba = t.match(/\bBachelor\s+of\s+(Arts|Science)\s+in\s+([^.,]+)/i);
  if (ba) return `${ba[1] === 'Arts' ? 'BA' : 'BSc'} · ${ba[2].trim()}`;

  const mShort = t.match(
    /\b(?:Master|Bachelor|PhD|Doctorate)\s+of\s+([^.,]+?)(?:\s+at\s+the\s|\s+at\s+[A-Z]|\s+from\s|$|\.)/i,
  );
  if (mShort) return shortenLine(mShort[1].trim(), 76);

  const phd = t.match(/\bPh\.?\s*D\.?\s+(?:in\s+)?([^.,]+)/i);
  if (phd) return shortenLine(`PhD · ${phd[1].trim()}`, 80);

  return undefined;
}

/**
 * Portfolio-style education row: school (title) + major/degree (subtitle) required; dates in status when found.
 */
function parseEducationEntryStrict(raw: string): ProfileTimelineEntry | null {
  const text = raw.replace(/\s+/g, ' ').trim();
  if (text.length < 16) return null;

  const atInst = text.match(
    /\b(?:at)\s+(?:the\s+)?((?:[A-Za-z][A-Za-z0-9&.'\s-]*?)?(?:University|College|Institute|School)(?:\s+of\s+[A-Za-z0-9&.'\s-]+)*)(?=\s*[,\.;)\]]|\s|$)/i,
  );
  const fromInst = text.match(
    /\bfrom\s+(?:the\s+)?((?:[A-Za-z][A-Za-z0-9&.'\s-]*?)?(?:University|College|Institute|UP\s+[A-Za-z]+)(?:\s+of\s+[A-Za-z0-9&.'\s-]+)*)(?=\s*[,\.;)\]]|\s|$)/i,
  );
  const upOnly = text.match(/\b(UP\s+[A-Za-z]+)\b/);

  let institution: string | undefined;
  if (atInst) institution = atInst[1].replace(/[,.]$/, '').trim();
  else if (fromInst) institution = fromInst[1].replace(/[,.]$/, '').trim();
  else if (upOnly) institution = upOnly[1];
  if (!institution || institution.length < 3) return null;

  const degree = inferDegreeLabel(text);
  if (!degree || degree.length < 3) return null;

  const time = extractResumeTimeMarker(text);

  return {
    title: institution,
    subtitle: degree,
    status: time,
  };
}

/** One narrative may list multiple roles — split into company + role lines. */
function parseWorkTimelineEntries(raw: string): ProfileTimelineEntry[] {
  const text = raw.replace(/\s+/g, ' ').trim();
  const out: ProfileTimelineEntry[] = [];

  const roleAtRe =
    /\b((?:Senior\s+|Lead\s+|Principal\s+)?(?:Junior\s+)?[A-Za-z][A-Za-z\s]{0,44}?(?:Scientist|Analyst|Engineer|Developer|Designer|Architect|Manager|Director|Consultant|Intern|Researcher|Specialist|Officer))\s+at\s+(?:the\s+)?([A-Z0-9][A-Za-z0-9&.'\s-]*?(?:\s+(?:Inc\.|Ltd\.|LLC|Corp\.?|Office|Bank))?)(?=[\s,]*(?:and\s+as|and\s+|$|[.,]))/gi;
  let m: RegExpExecArray | null;
  while ((m = roleAtRe.exec(text)) !== null) {
    const subtitle = stripNarrativeWorkPrefix(m[1]).replace(/\s+/g, ' ');
    const title = m[2].trim().replace(/[,.]$/, '');
    if (title.length >= 2 && subtitle.length >= 4) out.push({ title, subtitle });
  }

  if (!out.some((e) => e.title.toLowerCase().includes('intellectual property'))) {
    const ipMatch =
      text.match(
        /\b(Data\s+Analyst)\s+(?:at\s+)?(?:the\s+)?((?:Intellectual\s+Property\s+Office|Canadian\s+IP\s+Office|IP\s+Office))/i,
      ) ?? text.match(/\b(Data\s+Analyst)\s+(Intellectual\s+Property\s+Office)/i);
    if (ipMatch) {
      out.push({ title: ipMatch[2].replace(/\s+/g, ' '), subtitle: ipMatch[1] });
    }
  }

  if (out.length > 0) return dedupeWorkEntries(out);

  const atCo = text.match(
    /\b(?:at|@)\s+(?:the\s+)?([A-Z0-9][A-Za-z0-9&.'\s-]*?(?:\s+(?:Inc\.|Ltd\.|LLC|Corp\.?|Office|Bank))?)\b/,
  );
  if (atCo) {
    const title = atCo[1].trim();
    const rest = text.replace(atCo[0], ' ').replace(/\s+/g, ' ').trim();
    const cleaned = stripNarrativeWorkPrefix(rest);
    const subtitle =
      cleaned.length > 4 && cleaned.toLowerCase() !== title.toLowerCase()
        ? shortenLine(cleaned, 88)
        : undefined;
    return [{ title, subtitle }];
  }

  const first = text.split(/(?<=[.!?])\s+/)[0]?.trim() ?? text;
  const cleanedFirst = stripNarrativeWorkPrefix(first);
  return [{ title: shortenLine(cleanedFirst || first, 52), subtitle: undefined }];
}

function dedupeWorkEntries(entries: ProfileTimelineEntry[]): ProfileTimelineEntry[] {
  const seen = new Set<string>();
  return entries.filter((e) => {
    const k = `${e.title}|${e.subtitle ?? ''}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

/** Portfolio-style work row: company + role required; dates in status when found on the same block. */
function strictWorkTimelineFromLine(raw: string): ProfileTimelineEntry[] {
  const time = extractResumeTimeMarker(raw);
  const entries = dedupeWorkEntries(parseWorkTimelineEntries(raw));
  return entries
    .filter((e) => e.title.trim().length >= 2 && (e.subtitle?.trim().length ?? 0) >= 3)
    .map((e) => ({ ...e, status: time }));
}

function splitBackgroundIntoLines(snippet: string | null, parsed: string[]): string[] {
  if (snippet?.trim()) {
    const byPara = snippet.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
    if (byPara.length > 1) return byPara;
    const bySentence = snippet.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter((s) => s.length > 20);
    return bySentence.length > 1 ? bySentence : [snippet.trim()];
  }
  return parsed;
}

function ProfileTimeline({
  entries,
  emptyLabel,
}: {
  entries: ProfileTimelineEntry[];
  /** Pass empty string to hide (e.g. when a parent hint already explains the empty state). */
  emptyLabel: string;
}) {
  if (entries.length === 0) {
    if (!emptyLabel.trim()) return null;
    return <p className="mt-1 text-xs text-slate-400">{emptyLabel}</p>;
  }

  return (
    <ul className="mt-3 space-y-0">
      {entries.map((entry, i) => {
        const isFirst = i === 0;
        const isLast = i === entries.length - 1;
        return (
          <li key={`${entry.title}-${i}`} className="flex gap-3 items-stretch">
            <div className="flex w-4 shrink-0 flex-col items-center self-stretch pt-0.5">
              <span
                className={cn(
                  'z-[1] h-2.5 w-2.5 shrink-0 rounded-full ring-2 ring-white',
                  isFirst ? 'bg-teal-500' : 'bg-slate-300',
                )}
                aria-hidden
              />
              {!isLast ? <span className="mt-0 w-px flex-1 bg-slate-200" /> : null}
            </div>
            <div className={cn('min-w-0 flex-1', !isLast ? 'pb-5' : 'pb-0')}>
              <p className="text-xs font-semibold leading-snug text-slate-900">{entry.title}</p>
              {entry.subtitle ? (
                <p
                  className={cn(
                    'mt-0.5 text-[11px] leading-snug text-slate-600',
                    entry.subtitleFull &&
                      'max-h-44 overflow-y-auto overscroll-contain pr-0.5 [scrollbar-width:thin]',
                  )}
                >
                  {entry.subtitle}
                </p>
              ) : null}
              {entry.status ? (
                <p className="mt-1 text-[10px] text-slate-500">{entry.status}</p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** Left column: when education + experience are both empty, explain resume-optional and multi-user variance. */
function ProfileBackgroundHint({
  hasSubstantialLearnerText,
  hasResumeFile,
}: {
  hasSubstantialLearnerText: boolean;
  hasResumeFile: boolean;
}) {
  let body: string;
  if (hasSubstantialLearnerText) {
    body =
      'Education needs a school and major/degree; experience needs a company and role. Dates appear when listed. Use “Learner information” below for the full text.';
  } else if (hasResumeFile) {
    body =
      'Structured education or experience is not shown yet. If you recently uploaded a resume, content may still sync; you can also try a clearer PDF on the right.';
  } else {
    body =
      'Uploading a resume (optional) on the right can enrich these sections. You can also keep learning without a resume — skills and profile text will fill in over time.';
  }
  return (
    <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50/90 px-3 py-2.5 text-[11px] leading-snug text-slate-600">
      <p className="font-medium text-slate-700">Background</p>
      <p className="mt-1 text-slate-500">{body}</p>
    </div>
  );
}

/* ── Persona definitions (aligned with OnboardingPage) ────────────── */

interface PersonaOption {
  id: string;
  personaKey: string;
  title: string;
  learningStyle: LearningStyleOption;
  description: string;
  tags: string[];
}

const PERSONA_OPTIONS: PersonaOption[] = [
  {
    id: 'hands-on',
    personaKey: 'Hands-on Explorer',
    title: 'Interactive',
    learningStyle: 'Interactive',
    description: 'Learns best by doing and practicing with examples.',
    tags: ['Active', 'Visual', 'Step-by-step'],
  },
  {
    id: 'reflective',
    personaKey: 'Reflective Reader',
    title: 'Textual',
    learningStyle: 'Textual',
    description: 'Learns through reading and reflection. Prefers detailed explanations.',
    tags: ['Reading', 'Reflection'],
  },
  {
    id: 'visual',
    personaKey: 'Visual Learner',
    title: 'Visual',
    learningStyle: 'Visual',
    description: 'Understands concepts best through visuals and diagrams.',
    tags: ['Visual', 'Diagrams'],
  },
  {
    id: 'conceptual',
    personaKey: 'Conceptual Thinker',
    title: 'Concise',
    learningStyle: 'Concise',
    description: 'Enjoys big-picture ideas, theory, and analysis.',
    tags: ['Theory', 'Analysis', 'Big-picture'],
  },
  {
    id: 'balanced',
    personaKey: 'Balanced Learner',
    title: 'Balanced',
    learningStyle: 'Balanced',
    description: 'Flexible across different learning formats.',
    tags: ['Flexible', 'Neutral'],
  },
];

/* ── FSLSM-based learning preference helpers ─────────────────────── */

const FSLSM_THRESHOLD = 0.3;
const FSLSM_STRONG = 0.7;

interface PreferenceCardData {
  type: string;
  title: string;
  description: string;
}

function deriveFslsmPreferenceCards(
  dims: Record<string, number> | undefined,
): PreferenceCardData[] {
  if (!dims) return [];
  const cards: PreferenceCardData[] = [];

  const input = dims.fslsm_input ?? 0;
  if (input <= -FSLSM_THRESHOLD)
    cards.push({ type: 'visual', title: 'Visual materials', description: 'I prefer diagrams, charts, and videos over text.' });
  else if (input >= FSLSM_THRESHOLD)
    cards.push({ type: 'text', title: 'Text-based content', description: 'I prefer written explanations and detailed narratives.' });

  const perception = dims.fslsm_perception ?? 0;
  if (perception <= -FSLSM_THRESHOLD)
    cards.push({ type: 'practical', title: 'Practical examples', description: 'I prefer seeing real-world uses before theory.' });
  else if (perception >= FSLSM_THRESHOLD)
    cards.push({ type: 'conceptual', title: 'Conceptual thinking', description: 'I prefer understanding theory and concepts first.' });

  const understanding = dims.fslsm_understanding ?? 0;
  if (understanding <= -FSLSM_THRESHOLD)
    cards.push({ type: 'sequential', title: 'Step-by-step', description: 'I prefer clear, guided, linear progression.' });
  else if (understanding >= FSLSM_THRESHOLD)
    cards.push({ type: 'global', title: 'Big-picture first', description: 'I prefer seeing the overview before diving into details.' });

  const processing = dims.fslsm_processing ?? 0;
  if (processing <= -FSLSM_THRESHOLD)
    cards.push({ type: 'interactive', title: 'Interactive exercises', description: 'I prefer quizzes, sandboxes, and hands-on tasks.' });
  else if (processing >= FSLSM_THRESHOLD)
    cards.push({ type: 'reflective', title: 'Reflective learning', description: 'I prefer reading, observation, and time to reflect.' });

  return cards;
}

function deriveFslsmBullets(dims: Record<string, number> | undefined): string[] {
  if (!dims) return [];
  const bullets: string[] = [];

  const input = dims.fslsm_input ?? 0;
  if (input <= -FSLSM_STRONG) bullets.push('Prioritizes visual content and infographics.');
  else if (input <= -FSLSM_THRESHOLD) bullets.push('Includes visual aids like diagrams and charts.');
  else if (input >= FSLSM_STRONG) bullets.push('Focuses on detailed written and narrated explanations.');
  else if (input >= FSLSM_THRESHOLD) bullets.push('Enriches content with written and narrative-style material.');

  const perception = dims.fslsm_perception ?? 0;
  if (perception <= -FSLSM_STRONG) bullets.push('Introduces concepts through concrete examples first.');
  else if (perception <= -FSLSM_THRESHOLD) bullets.push('Leads with practical examples before theoretical concepts.');
  else if (perception >= FSLSM_STRONG) bullets.push('Presents theoretical frameworks and concepts upfront.');
  else if (perception >= FSLSM_THRESHOLD) bullets.push('Emphasizes conceptual understanding before examples.');

  const understanding = dims.fslsm_understanding ?? 0;
  if (understanding <= -FSLSM_STRONG) bullets.push('Structures lessons in strict, bite-sized sequences.');
  else if (understanding <= -FSLSM_THRESHOLD) bullets.push('Organizes content in a structured, sequential order.');
  else if (understanding >= FSLSM_STRONG) bullets.push('Starts with big-picture overviews before diving into details.');
  else if (understanding >= FSLSM_THRESHOLD) bullets.push('Provides big-picture framing before sequential detail.');

  const processing = dims.fslsm_processing ?? 0;
  if (processing <= -FSLSM_STRONG) bullets.push('Integrates frequent interactive knowledge checks.');
  else if (processing <= -FSLSM_THRESHOLD) bullets.push('Includes hands-on activities and practice opportunities.');
  else if (processing >= FSLSM_STRONG) bullets.push('Allows ample time for reflection and deep thinking.');
  else if (processing >= FSLSM_THRESHOLD) bullets.push('Provides reflection time before moving to new topics.');

  if (bullets.length === 0) bullets.push('Delivers a balanced mix of content styles and activities.');
  return bullets;
}

function PreferenceIcon({ type }: { type: string }) {
  const cls = 'w-5 h-5';
  switch (type) {
    case 'visual':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z" />
        </svg>
      );
    case 'text':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
        </svg>
      );
    case 'practical':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75a4.5 4.5 0 0 1-4.884 4.484c-1.076-.091-2.264.071-2.95.904l-7.152 8.684a2.548 2.548 0 1 1-3.586-3.586l8.684-7.152c.833-.686.995-1.874.904-2.95a4.5 4.5 0 0 1 6.336-4.486l-3.276 3.276a3.004 3.004 0 0 0 2.25 2.25l3.276-3.276c.256.565.398 1.192.398 1.852Z" />
        </svg>
      );
    case 'conceptual':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 0 0 1.5-.189m-1.5.189a6.01 6.01 0 0 1-1.5-.189m3.75 7.478a12.06 12.06 0 0 1-4.5 0m3.75 2.383a14.406 14.406 0 0 1-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 1 0-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
        </svg>
      );
    case 'sequential':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 0 1 0 3.75H5.625a1.875 1.875 0 0 1 0-3.75Z" />
        </svg>
      );
    case 'global':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0 1 12 16.5a17.92 17.92 0 0 1-8.716-2.247m0 0A9.015 9.015 0 0 1 3 12c0-1.605.42-3.113 1.157-4.418" />
        </svg>
      );
    case 'interactive':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.456-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.456-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.456 2.456Z" />
        </svg>
      );
    case 'reflective':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
        </svg>
      );
    default:
      return null;
  }
}

export function ProfilePage() {
  const navigate = useNavigate();
  const { userId, logout } = useAuthContext();
  const { setCollapsed } = useSidebarCollapse();
  const { goals, refreshGoals, updateGoal, mergeLearnerProfile } = useGoalsContext();
  const { activeGoal } = useActiveGoal();
  const { data: config } = useAppConfig();

  const { data: authMe } = useAuthMe(Boolean(userId));
  const { data: metrics, isLoading: metricsLoading } = useBehavioralMetrics(
    userId ?? undefined,
    activeGoal?.id,
  );
  const { data: personasData } = usePersonas();
  const deleteUserDataMutation = useDeleteUserData();
  const deleteUserMutation = useDeleteUser();
  const updateLearnerInfoMutation = useUpdateLearnerInformation();
  const updatePreferencesMutation = useUpdateLearningPreferences();
  const extractPdf = useExtractPdfText();

  const [learningStyle, setLearningStyle] = useState(() => getLearningStylePreference());
  useEffect(() => {
    setLearningStyle(getLearningStylePreference());
  }, [activeGoal?.id]);
  const [showPreferencesModal, setShowPreferencesModal] = useState(false);
  const [selectedPersonaId, setSelectedPersonaId] = useState<string | null>(null);
  const [preferencesSaveError, setPreferencesSaveError] = useState<string | null>(null);
  const [showDeleteDataConfirm, setShowDeleteDataConfirm] = useState(false);
  const [showDeleteAccountConfirm, setShowDeleteAccountConfirm] = useState(false);
  const [resumeName, setResumeName] = useState<string | null>(() => getStoredResumeFileName());
  const [resumeStatus, setResumeStatus] = useState<string | null>(null);
  const [avatarDataUrl, setAvatarDataUrl] = useState<string | null>(null);
  const [avatarMessage, setAvatarMessage] = useState<string | null>(null);
  const avatarInputRef = useRef<HTMLInputElement>(null);

  /** localStorage filename + Talent Assets UI — clear when server data is wiped or user removes resume. */
  const clearLocalResumeUi = useCallback(() => {
    clearStoredResume();
    setResumeName(null);
    setResumeStatus(null);
  }, []);

  useEffect(() => {
    setAvatarDataUrl(getAvatarDataUrl(userId));
    setAvatarMessage(null);
  }, [userId]);

  useEffect(() => {
    setCollapsed(true);
  }, [setCollapsed]);

  /** Sync goals (and embedded learner profile) from server when opening Profile — other flows may have updated the profile. */
  useEffect(() => {
    if (!userId) return;
    void refreshGoals();
  }, [userId, refreshGoals]);

  const profileTags: string[] = [];
  if (activeGoal?.learner_profile?.goal_display_name) {
    profileTags.push('Active learner');
  }
  if (learningStyle) {
    profileTags.push(learningStyle);
  }
  if (profileTags.length === 0) profileTags.push('Learner');

  const goalDisplayName =
    (activeGoal?.learner_profile?.goal_display_name as string | undefined) ?? '';

  // Member since: prefer auth/me created_at, then first-login localStorage, then earliest goal timestamp
  const memberSinceIso =
    (authMe as { created_at?: string } | undefined)?.created_at ||
    getMemberSinceIso(userId) ||
    earliestGoalTimestampIso(goals as unknown as Array<Record<string, unknown>>);
  const memberSinceDisplay = formatMemberSinceDisplay(memberSinceIso);

  const handleRestartOnboarding = async () => {
    if (!userId) return;
    try {
      await deleteUserDataMutation.mutateAsync(userId);
      clearLocalResumeUi();
      await refreshGoals();
      navigate('/onboarding');
    } catch {
      // ignore
    } finally {
      setShowDeleteDataConfirm(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (!userId) return;
    try {
      await deleteUserMutation.mutateAsync();
      clearLocalResumeUi();
      logout();
      navigate('/login');
    } catch {
      // ignore
    } finally {
      setShowDeleteAccountConfirm(false);
    }
  };

  const handleOpenPreferencesModal = () => {
    setPreferencesSaveError(null);
    const currentPersona = PERSONA_OPTIONS.find((p) => {
      const dims = personasData?.personas?.[p.personaKey]?.fslsm_dimensions;
      if (!dims || !fslsmDims) return false;
      return Object.keys(dims).every(
        (k) => Math.abs((dims[k] ?? 0) - (fslsmDims[k] ?? 0)) < 0.15,
      );
    });
    setSelectedPersonaId(currentPersona?.id ?? null);
    setShowPreferencesModal(true);
  };

  const handleSavePreferences = async () => {
    const persona = PERSONA_OPTIONS.find((p) => p.id === selectedPersonaId);
    if (!persona || !activeGoal || !userId) return;
    const personaDims = personasData?.personas?.[persona.personaKey]?.fslsm_dimensions;
    if (!personaDims) return;

    setPreferencesSaveError(null);
    const sliderPayload = {
      update_mode: 'fslsm_slider_override',
      slider_values: personaDims,
    };

    try {
      const res = await updatePreferencesMutation.mutateAsync({
        learner_profile: serializeLearnerProfileForApi(activeGoal.learner_profile),
        learner_interactions: JSON.stringify(sliderPayload),
        user_id: userId,
        goal_id: activeGoal.id,
      });
      const mergedLp =
        normalizeLearnerProfile(res.learner_profile) ?? normalizeLearnerProfile(activeGoal.learner_profile);
      if (mergedLp) {
        updateGoal(activeGoal.id, { ...activeGoal, learner_profile: mergedLp });
      }
      await refreshGoals();
      if (mergedLp) {
        mergeLearnerProfile(activeGoal.id, mergedLp);
      }
      setLearningStylePreference(persona.learningStyle);
      setLearningStyle(persona.learningStyle);
      setShowPreferencesModal(false);
    } catch {
      setPreferencesSaveError('Failed to update preferences. Please try again.');
    }
  };

  const behavioralMetrics: any = metrics ?? {};
  const masteryHistory: number[] = behavioralMetrics.mastery_history ?? [];
  void behavioralMetrics.sessions_completed;
  void behavioralMetrics.total_sessions_in_path;
  void behavioralMetrics.total_learning_time_sec;
  void behavioralMetrics.motivational_triggers_count;

  let streakDays = 0;
  for (let i = masteryHistory.length - 1; i >= 0; i -= 1) {
    if (masteryHistory[i] > 0) streakDays += 1;
    else break;
  }

  const masteryThreshold =
    (config?.mastery_threshold_default as number | undefined) ?? 0.6;
  void masteryHistory.filter((v) => v >= masteryThreshold).length;
  void masteryHistory.length;

  const profileFairness = activeGoal?.profile_fairness as Record<string, unknown> | undefined;

  const learnerProfileNormalized = normalizeLearnerProfile(activeGoal?.learner_profile);
  const learnerInformation = learnerInformationToString(learnerProfileNormalized?.learner_information);

  const learnerProfileRecord = learnerProfileNormalized as Record<string, unknown> | undefined;
  const learnerInfoBody = learnerInformation ? displayLearnerInformationBody(learnerInformation) : '';
  const parsedFromLearnerInfo = learnerInfoBody ? parseLearnerInformationSections(learnerInfoBody) : { education: [], work: [] };
  const educationSnippet =
    normalizeBackgroundSnippet(learnerProfileRecord?.education) ??
    normalizeBackgroundSnippet(learnerProfileRecord?.education_history);
  const workSnippet =
    normalizeBackgroundSnippet(learnerProfileRecord?.work_experience) ??
    normalizeBackgroundSnippet(learnerProfileRecord?.work_history);

  const educationTimelineLines = splitBackgroundIntoLines(
    educationSnippet,
    parsedFromLearnerInfo.education,
  );
  const educationTimelineEntries = educationTimelineLines
    .map((line) => parseEducationEntryStrict(line))
    .filter((e): e is ProfileTimelineEntry => e != null);
  const workTimelineLines = splitWorkRoleClauses(
    splitBackgroundIntoLines(workSnippet, parsedFromLearnerInfo.work),
  );
  const workTimelineEntries = workTimelineLines.flatMap((line) => strictWorkTimelineFromLine(line));

  const bothTimelinesEmpty = educationTimelineEntries.length === 0 && workTimelineEntries.length === 0;
  const hasSubstantialLearnerText = learnerInfoBody.replace(/\s+/g, ' ').trim().length >= 36;
  const hasResumeFile = Boolean(resumeName);

  const showEducationSection = educationTimelineEntries.length > 0;
  const showExperienceSection = workTimelineEntries.length > 0;
  /** No parsed timeline rows — show full learner text inline (portfolio-style fallback). */
  const showLearnerInfoExpanded = bothTimelinesEmpty && Boolean(learnerInformation?.trim());
  /** Timelines present — keep detailed bio behind disclosure when long enough. */
  const showLearnerInfoCollapsible = !bothTimelinesEmpty && Boolean(learnerInformation && hasSubstantialLearnerText);
  /** Dashed hint only when there is nothing to show in learner text either. */
  const showProfileBackgroundHint = bothTimelinesEmpty && !learnerInformation?.trim();

  const fslsmDims = activeGoal?.learner_profile?.learning_preferences?.fslsm_dimensions;
  const preferenceCards = deriveFslsmPreferenceCards(fslsmDims);
  const personalizationBullets = deriveFslsmBullets(fslsmDims);

  const handleResumeUpload: React.ChangeEventHandler<HTMLInputElement> = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !userId || !activeGoal) return;
    setResumeStatus(null);
    setResumeName(file.name);
    try {
      const result = await extractPdf.mutateAsync(file);
      const pdfText = (result as { text?: string }).text ?? '';
      if (!pdfText) {
        setResumeStatus('Failed to read PDF. Please try another file.');
        return;
      }
      const parsedProfile = normalizeLearnerProfile(activeGoal.learner_profile);
      const currentProfile = (parsedProfile ?? {}) as Record<string, unknown>;
      const res = await updateLearnerInfoMutation.mutateAsync({
        learner_profile: serializeLearnerProfileForApi(activeGoal.learner_profile),
        edited_learner_information: learnerInformationToString(currentProfile.learner_information),
        resume_text: pdfText,
        user_id: userId,
        goal_id: activeGoal.id,
      });
      const mergedLp =
        normalizeLearnerProfile(res.learner_profile) ?? normalizeLearnerProfile(activeGoal.learner_profile);
      if (mergedLp) {
        updateGoal(activeGoal.id, { ...activeGoal, learner_profile: mergedLp });
      }
      await refreshGoals();
      if (mergedLp) {
        mergeLearnerProfile(activeGoal.id, mergedLp);
      }
      setStoredResume(file.name, `Resume summary: ${pdfText}`);
      setResumeStatus('Resume connected successfully.');
    } catch {
      setResumeStatus('Upload failed. Please try again.');
    } finally {
      e.target.value = '';
    }
  };

  const handleResumeRemove = async () => {
    if (!userId || !activeGoal) {
      clearLocalResumeUi();
      return;
    }
    try {
      setResumeStatus(null);
      const parsedProfile = normalizeLearnerProfile(activeGoal.learner_profile);
      const currentProfile = (parsedProfile ?? {}) as Record<string, unknown>;
      const res = await updateLearnerInfoMutation.mutateAsync({
        learner_profile: serializeLearnerProfileForApi(activeGoal.learner_profile),
        edited_learner_information: learnerInformationToString(currentProfile.learner_information),
        resume_text: '',
        user_id: userId,
        goal_id: activeGoal.id,
      });
      const mergedLp =
        normalizeLearnerProfile(res.learner_profile) ?? normalizeLearnerProfile(activeGoal.learner_profile);
      if (mergedLp) {
        updateGoal(activeGoal.id, { ...activeGoal, learner_profile: mergedLp });
      }
      await refreshGoals();
      if (mergedLp) {
        mergeLearnerProfile(activeGoal.id, mergedLp);
      }
      clearLocalResumeUi();
      setResumeStatus('Resume removed from profile.');
    } catch {
      setResumeStatus('Failed to remove resume. Please try again.');
    }
  };

  return (
    <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 pb-10">
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[280px_minmax(0,1fr)] lg:items-start lg:gap-x-10 lg:gap-y-8">
        {/* Left: identity & account (fixed width on large screens) */}
        <aside className="flex w-full min-w-0 shrink-0 flex-col rounded-xl border border-slate-200 bg-white p-4 lg:min-h-[calc(100vh-7rem)] lg:sticky lg:top-0 lg:self-start">
          {userId && (
            <input
              ref={avatarInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                e.target.value = '';
                if (!file || !userId) return;
                setAvatarMessage(null);
                const result = await setAvatarFromFile(userId, file);
                if (result.ok) {
                  setAvatarDataUrl(getAvatarDataUrl(userId));
                  setAvatarMessage('Saved on this device.');
                } else {
                  setAvatarMessage(result.error);
                }
              }}
            />
          )}
          <div className="flex flex-1 flex-col gap-4">
            <div>
              <div className="flex flex-col items-center gap-1">
          <div className="relative h-20 w-20 shrink-0 overflow-hidden rounded-full bg-slate-200 ring-2 ring-slate-100 group">
            {avatarDataUrl ? (
              <img
                src={avatarDataUrl}
                alt=""
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <svg className="w-10 h-10 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
                </svg>
              </div>
            )}
            {userId && (
              <>
                <button
                  type="button"
                  aria-label="Change profile photo"
                  className="absolute left-1/2 top-1/2 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-black/45 text-white shadow-md transition-colors hover:bg-black/55 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1"
                  onClick={() => avatarInputRef.current?.click()}
                >
                  {/* Camera icon — click opens file picker */}
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
                    />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </button>
                {avatarDataUrl && (
                  <button
                    type="button"
                    aria-label="Remove profile photo"
                    className="absolute top-0.5 right-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-black/50 text-white text-xs hover:bg-black/70"
                    onClick={(e) => {
                      e.stopPropagation();
                      clearAvatar(userId);
                      setAvatarDataUrl(null);
                      setAvatarMessage('Removed.');
                    }}
                  >
                    ×
                  </button>
                )}
              </>
            )}
          </div>
                {avatarMessage && (
                  <p className="max-w-[140px] text-center text-[10px] text-slate-500">{avatarMessage}</p>
                )}
              </div>

              <div className="mt-4 w-full text-left">
                <h2 className="text-lg font-semibold leading-tight text-slate-900">{userId ?? 'Learner'}</h2>
                {goalDisplayName ? (
                  <p className="mt-1 text-xs font-medium text-primary-700 line-clamp-2">{goalDisplayName}</p>
                ) : null}
                <p className="mt-0.5 text-sm text-slate-500">@{userId ?? 'guest'}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {profileTags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {showProfileBackgroundHint && (
              <ProfileBackgroundHint
                hasSubstantialLearnerText={hasSubstantialLearnerText}
                hasResumeFile={hasResumeFile}
              />
            )}

            {(showEducationSection || showExperienceSection) && (
              <div className="border-b border-slate-100 pb-4 space-y-4">
                {showEducationSection ? (
                  <div>
                    <p className={PROFILE_SIDEBAR_SECTION_LABEL}>Education</p>
                    <ProfileTimeline entries={educationTimelineEntries} emptyLabel="" />
                  </div>
                ) : null}
                {showExperienceSection ? (
                  <div>
                    <p className={PROFILE_SIDEBAR_SECTION_LABEL}>Experience</p>
                    <ProfileTimeline entries={workTimelineEntries} emptyLabel="" />
                  </div>
                ) : null}
              </div>
            )}

            {showLearnerInfoExpanded ? (
              <div className="rounded-lg border border-slate-200 bg-white text-left">
                <p className="px-3 py-2 text-xs font-semibold text-slate-900">Learner information</p>
                <div className="max-h-64 overflow-y-auto border-t border-slate-100 px-3 py-2 text-xs leading-relaxed text-slate-700 whitespace-pre-wrap">
                  {learnerInfoBody || learnerInformation}
                </div>
              </div>
            ) : showLearnerInfoCollapsible ? (
              <details className="group rounded-lg border border-slate-200 bg-white text-left">
                <summary className="cursor-pointer list-none px-3 py-2 text-xs font-medium text-primary-700 hover:bg-slate-50 [&::-webkit-details-marker]:hidden">
                  <span className="underline decoration-primary-300 underline-offset-2">View full learner information</span>
                  <span className="ml-1 text-slate-400 group-open:hidden">▸</span>
                  <span className="ml-1 text-slate-400 hidden group-open:inline">▾</span>
                </summary>
                <div className="max-h-56 overflow-y-auto border-t border-slate-100 px-3 py-2 text-xs leading-relaxed text-slate-700 whitespace-pre-wrap">
                  {learnerInfoBody || learnerInformation}
                </div>
              </details>
            ) : null}

            <div className="border-t border-slate-100 pt-4">
              <h3 className={PROFILE_SIDEBAR_SECTION_LABEL}>Account</h3>
              <dl className="mt-2 space-y-2.5 text-xs">
                <div>
                  <dt className="text-slate-500">Email</dt>
                  <dd className="mt-0.5 text-slate-900">{userId ? `${userId}@example` : 'Not connected'}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Member since</dt>
                  <dd className="mt-0.5 text-slate-900">
                    {memberSinceDisplay}
                    {memberSinceIso == null && userId && (
                      <span className="mt-0.5 block text-[10px] text-slate-400">
                        Shown after first sign-in on this device, or when the API returns account creation time.
                      </span>
                    )}
                  </dd>
                </div>
              </dl>
            </div>
          </div>

          <div className="mt-auto border-t border-slate-100 pt-4 space-y-4">
            <button
              type="button"
              className="w-full rounded-lg border border-slate-200 py-2 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-50"
              onClick={() => {
                logout();
                navigate('/login');
              }}
            >
              Sign out
            </button>
            <div className="space-y-3">
              {!showDeleteDataConfirm ? (
                <button
                  type="button"
                  onClick={() => setShowDeleteDataConfirm(true)}
                  className="w-full text-left text-sm text-slate-600 hover:text-slate-800 underline"
                >
                  Restart onboarding (clear all data)
                </button>
              ) : (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-2.5 space-y-2">
                  <p className="text-[11px] leading-snug text-amber-900">
                    This will delete all your goals, learning history, and profile data. Are you sure?
                  </p>
                  <div className="flex flex-col gap-1.5">
                    <Button
                      size="sm"
                      onClick={handleRestartOnboarding}
                      loading={deleteUserDataMutation.isPending}
                      className="!bg-amber-600 hover:!bg-amber-700 !text-white w-full"
                    >
                      Yes, restart
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => setShowDeleteDataConfirm(false)} className="w-full">
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
              {!showDeleteAccountConfirm ? (
                <button
                  type="button"
                  onClick={() => setShowDeleteAccountConfirm(true)}
                  className="w-full text-left text-sm text-red-500 hover:text-red-700 underline"
                >
                  Delete account
                </button>
              ) : (
                <div className="rounded-lg border border-red-200 bg-red-50 p-2.5 space-y-2">
                  <p className="text-[11px] leading-snug text-red-900">
                    This will permanently delete your account and all data. This cannot be undone.
                  </p>
                  <div className="flex flex-col gap-1.5">
                    <Button
                      size="sm"
                      onClick={handleDeleteAccount}
                      loading={deleteUserMutation?.isPending}
                      className="!bg-red-600 hover:!bg-red-700 !text-white w-full"
                    >
                      Delete account
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => setShowDeleteAccountConfirm(false)} className="w-full">
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </aside>

        {/* Right: dynamic / interactive content — grid column aligns top edge with aside */}
        <div className="min-w-0 space-y-6 lg:min-w-0">
          {activeGoal?.learner_profile && (
            <ProfileFairnessPanel fairness={profileFairness ?? null} disclaimerOnly />
          )}

        {/* ACTIVITY SUMMARY — horizontal metrics + vertical dividers; tight label/value gap */}
        <section className="bg-white rounded-xl border border-slate-200 p-5">
          <h3 className={cn(PROFILE_PAGE_SECTION_TITLE, 'mb-4')}>Activity Summary</h3>
          <dl className="flex flex-col divide-y divide-slate-200 text-sm sm:flex-row sm:divide-x sm:divide-y-0 sm:divide-slate-200">
            <div className="flex flex-1 flex-col px-0 py-3 sm:px-3 sm:py-0">
              <dt className="text-left text-slate-500 leading-snug">Goals created</dt>
              <dd className="mt-px text-left text-slate-900 font-medium tabular-nums">
                {goals.length}
              </dd>
            </div>
            <div className="flex flex-1 flex-col px-0 py-3 sm:px-3 sm:py-0">
              <dt className="text-left text-slate-500 leading-snug">Sessions completed</dt>
              <dd className="mt-px text-left text-slate-900 font-medium tabular-nums">
                {metricsLoading || !metrics
                  ? '—'
                  : `${metrics.sessions_completed} / ${metrics.total_sessions_in_path}`}
              </dd>
            </div>
            <div className="flex flex-1 flex-col px-0 py-3 sm:px-3 sm:py-0">
              <dt className="text-left text-slate-500 leading-snug">Total study time</dt>
              <dd className="mt-px text-left text-slate-900 font-bold tabular-nums">
                {metricsLoading || !metrics ? '—' : formatDuration(metrics.total_learning_time_sec)}
              </dd>
            </div>
            <div className="flex flex-1 flex-col px-0 py-3 sm:px-3 sm:py-0">
              <dt className="text-left text-slate-500 leading-snug">Motivational triggers</dt>
              <dd className="mt-px text-left text-slate-900 font-medium tabular-nums">
                {metricsLoading || !metrics ? '—' : metrics.motivational_triggers_count}
              </dd>
            </div>
          </dl>
        </section>

      {/* How You Learn + How Ami uses your profile (single card) */}
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <h3 className={PROFILE_PAGE_SECTION_TITLE}>How You Learn</h3>
          </div>
          <Button
            size="sm"
            onClick={handleOpenPreferencesModal}
          >
            Edit Preferences
          </Button>
        </div>
        <p className="mb-6 flex items-center gap-1.5 text-sm text-slate-500">
          <svg className="h-4 w-4 shrink-0 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z" />
          </svg>
          Current preference: {learningStyle ?? 'Balanced'}. Applied by default to new learning goals.
        </p>

        <div
          className={cn(
            'grid gap-6 items-start',
            personalizationBullets.length > 0 ? 'lg:grid-cols-2 lg:gap-8' : 'grid-cols-1',
          )}
        >
          <div className="min-w-0">
            {preferenceCards.length > 0 ? (
              <div className="space-y-3">
                {preferenceCards.map((card) => (
                  <div
                    key={card.type}
                    className="flex items-center gap-3 rounded-lg border border-slate-200 px-4 py-3"
                  >
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
                      <PreferenceIcon type={card.type} />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{card.title}</p>
                      <p className="text-xs text-slate-500">{card.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50/80 py-8 text-center text-slate-400">
                <p className="text-sm">No learning preferences available yet.</p>
                <p className="mt-1 text-xs">Complete onboarding to set your preferences.</p>
              </div>
            )}
          </div>

          {personalizationBullets.length > 0 && (
            <div className="min-w-0 rounded-xl border border-teal-100 bg-teal-50/60 p-4">
              <div className="mb-3 flex items-center gap-2">
                <svg
                  className="h-4 w-4 shrink-0 text-teal-600"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1.5}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0-3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.456-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0-2.456-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.456 2.456Z"
                  />
                </svg>
                <p className="text-xs font-semibold uppercase tracking-wider text-teal-800">How Ami uses your profile</p>
              </div>
              <ul className="space-y-2.5">
                {personalizationBullets.map((bullet, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-sm text-teal-900">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-500" />
                    {bullet}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>

      {/* TALENT ASSETS */}
      <section className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
        <h3 className={PROFILE_PAGE_SECTION_TITLE}>Talent Assets</h3>
        <div className="border border-slate-200 rounded-lg p-4 bg-slate-50 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-lg bg-slate-200 flex items-center justify-center shrink-0">
              <svg className="w-6 h-6 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-900 truncate">
                {resumeName ?? 'No resume connected'}
              </p>
              <p className="text-xs text-slate-500 mt-0.5">
                Upload a PDF resume to enrich your learner profile. Ami uses only the extracted text.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {resumeName ? (
              <>
                <label className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium rounded-md bg-primary-600 text-white hover:bg-primary-700 cursor-pointer">
                  <input
                    type="file"
                    accept=".pdf"
                    className="hidden"
                    onChange={handleResumeUpload}
                  />
                  {extractPdf.isPending || updateLearnerInfoMutation.isPending ? 'Uploading…' : 'Update'}
                </label>
                <button
                  type="button"
                  onClick={handleResumeRemove}
                  className="px-3 py-1.5 text-sm font-medium rounded-md border border-slate-300 text-slate-700 hover:bg-slate-100"
                >
                  Remove
                </button>
              </>
            ) : (
              <label className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium rounded-md bg-primary-600 text-white hover:bg-primary-700 cursor-pointer">
                <input
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={handleResumeUpload}
                />
                {extractPdf.isPending || updateLearnerInfoMutation.isPending ? 'Uploading…' : 'Upload PDF'}
              </label>
            )}
          </div>
        </div>
        {resumeStatus && (
          <p className="text-xs text-slate-600">
            {resumeStatus}
          </p>
        )}
      </section>

        </div>
      </div>

      {/* ── Edit Preferences Modal ── */}
      <Modal
        open={showPreferencesModal}
        onClose={() => setShowPreferencesModal(false)}
        title="Edit Learning Preferences"
        maxWidth="max-w-2xl"
      >
        <p className="text-sm text-slate-500 mb-5">Choose the learning style that fits you best.</p>

        <div className="space-y-2">
          {PERSONA_OPTIONS.map((persona) => {
            const isSelected = selectedPersonaId === persona.id;
            return (
              <button
                key={persona.id}
                type="button"
                onClick={() => setSelectedPersonaId(persona.id)}
                className={cn(
                  'w-full text-left rounded-lg border-2 px-4 py-3 transition-all',
                  isSelected
                    ? 'border-primary-500 bg-primary-50/50 ring-1 ring-primary-200'
                    : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50',
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <p
                    className={cn(
                      'text-sm font-semibold',
                      isSelected ? 'text-primary-700' : 'text-slate-900',
                    )}
                  >
                    {persona.title}
                  </p>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">{persona.description}</p>
              </button>
            );
          })}
        </div>

        {preferencesSaveError && (
          <p className="text-sm text-red-600 mt-3">{preferencesSaveError}</p>
        )}

        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-slate-100">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setShowPreferencesModal(false)}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleSavePreferences}
            disabled={!selectedPersonaId || !activeGoal}
            loading={updatePreferencesMutation.isPending}
          >
            Save
          </Button>
        </div>
      </Modal>
    </div>
  );
}
