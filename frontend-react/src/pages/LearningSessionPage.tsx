import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui';
import { QuizPanel } from '@/components/learning/QuizPanel';
import { cn } from '@/lib/cn';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { useActiveGoal } from '@/context/GoalsContext';
import { useAppConfig } from '@/api/endpoints/config';
import { useGoalRuntimeState } from '@/api/endpoints/goals';
import {
  useGetLearningContent,
  useGenerateLearningContent,
  useDeleteLearningContent,
  useSessionActivity,
  useCompleteSession,
  useSubmitContentFeedback,
  generateLearningContentApi,
  reportDiagramRenderFailureApi,
} from '@/api/endpoints/content';
import { auditContentBiasApi, auditChatbotBiasApi } from '@/api/endpoints/audits';
import { useChatWithTutor } from '@/api/endpoints/chat';
import { ContentBiasAuditPanel, ChatbotBiasAuditPanel } from '@/components/ethics';
import { SessionLoadingPanel } from '@/components/learning/SessionLoadingPanel';
import type { MasteryEvaluationResponse, ContentSection } from '@/types';

interface LocationState {
  goalId: number;
  sessionIndex: number;
}

function transformSectionMarkdown(markdown: string): string {
  if (!markdown) return markdown;

  let text = markdown;

  // Normalize common "0." / "0)" ordered-list artifacts (often from PDF extraction or LLM output).
  // Markdown will auto-number when each item is "1.", so this removes visible "0." markers.
  text = text.replace(/^0[.)]\s+/gm, '1. ');

  // Normalize diagram fence variants to mermaid (e.g. ```DIAGRAM, ```diagram mermaid)
  text = text.replace(/^```[ \t]*diagram(?:\b[^\n]*)?$/gim, '```mermaid');

  // Mirror Streamlit behavior: make backend /static assets absolute so media (video/image) loads correctly
  const staticBase = absolutizeUrl('/static/');
  if (staticBase) text = text.replace(/\/static\//g, staticBase);

  // Fix unfenced mermaid blocks: detect bare mermaid keywords that aren't inside code fences
  // Pattern: optional "MERMAID" label line, then mermaid syntax (graph/flowchart/sequenceDiagram/etc.)
  const mermaidKeywords = '(?:graph\\s+(?:TD|LR|RL|BT|TB)|flowchart\\s+(?:TD|LR|RL|BT|TB)|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|gitGraph|journey|mindmap)';
  const unfencedMermaidRe = new RegExp(
    `(?:^|\\n)\\s*(?:MERMAID|mermaid|Mermaid)\\s*\\n(\\s*${mermaidKeywords}[\\s\\S]*?)(?=\\n#{1,4}\\s|\\n\\n[A-Z]|$)`,
    'gm',
  );
  text = text.replace(unfencedMermaidRe, (_match, body: string) =>
    `\n\n\`\`\`mermaid\n${body.trim()}\n\`\`\`\n`,
  );

  // Also handle case where mermaid syntax appears directly without any label
  const bareMermaidRe = new RegExp(
    `(?:^|\\n)(\\s*${mermaidKeywords}(?:;|\\n)[\\s\\S]*?)(?=\\n#{1,4}\\s|\\n\\n(?:[A-Z*\\-\\d])|$)`,
    'gm',
  );
  // Only wrap if not already inside a code fence
  text = text.replace(bareMermaidRe, (match, body: string, offset: number) => {
    const before = text.slice(0, offset);
    const openFences = (before.match(/```/g) || []).length;
    if (openFences % 2 !== 0) return match;
    return `\n\n\`\`\`mermaid\n${body.trim()}\n\`\`\`\n`;
  });

  return text;
}

function normalizeGoalContext(value: unknown): Record<string, unknown> | undefined {
  if (!value) return undefined;
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value) as unknown;
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed as Record<string, unknown>;
      return undefined;
    } catch {
      return undefined;
    }
  }
  if (typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>;
  return undefined;
}

function absolutizeUrl(url: string | null | undefined): string {
  if (!url) return '';
  if (url.startsWith('http')) return url;
  const base = (((import.meta.env as Record<string, string>).VITE_API_BASE_URL ?? '') as string)
    .replace(/\/$/, '')
    .replace(/\/v1$/, '');
  return `${base}${url.startsWith('/') ? '' : '/'}${url}`;
}

/** Backend emits [![thumb](thumb)](youtube_url) — embed YouTube without backend changes */
function youtubeEmbedUrl(href: string): string | null {
  try {
    const u = new URL(href);
    if (u.hostname === 'youtu.be' || u.hostname.endsWith('.youtu.be')) {
      const id = u.pathname.replace(/^\//, '').split('/')[0];
      if (id && /^[\w-]{11}$/.test(id)) return `https://www.youtube.com/embed/${id}`;
    }
    if (u.hostname.includes('youtube.com')) {
      const v = u.searchParams.get('v');
      if (v && /^[\w-]{11}$/.test(v)) return `https://www.youtube.com/embed/${v}`;
      const m = u.pathname.match(/\/embed\/([\w-]+)/);
      if (m && m[1]) return `https://www.youtube.com/embed/${m[1]}`;
    }
  } catch {
    /* ignore */
  }
  return null;
}

function isDirectVideoUrl(href: string): boolean {
  try {
    const u = new URL(href);
    const path = u.pathname.toLowerCase();
    return /\.(webm|mp4|ogg|ogv)(\?|$)/i.test(path);
  } catch {
    return false;
  }
}

/** Video id from embed URL for thumbnail poster */
function youtubeIdFromEmbed(embed: string): string | null {
  const m = embed.match(/\/embed\/([\w-]{11})/);
  return m?.[1] ?? null;
}

/**
 * Defer iframe src until near viewport or user clicks — avoids loading every
 * YouTube player at once (slow). Shows poster + play until then.
 */
function LazyYouTubeEmbed({ embedUrl, watchUrl }: { embedUrl: string; watchUrl: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [posterFailed, setPosterFailed] = useState(false);
  const [iframeReady, setIframeReady] = useState(false);
  const videoId = youtubeIdFromEmbed(embedUrl);
  // maxresdefault often blank/404 for shorts; hqdefault is more reliable
  const posterUrl =
    videoId && !posterFailed
      ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`
      : null;

  useEffect(() => {
    const el = containerRef.current;
    if (!el || src) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setSrc(embedUrl);
          setIframeReady(false);
          obs.disconnect();
        }
      },
      { rootMargin: '400px 0px', threshold: 0.01 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [embedUrl, src]);

  // If iframe never fires onLoad (cross-origin quirks), clear overlay after a few seconds
  useEffect(() => {
    if (!src) return;
    const t = window.setTimeout(() => setIframeReady(true), 8000);
    return () => clearTimeout(t);
  }, [src]);

  const loadPlayer = useCallback(() => {
    const withAutoplay = `${embedUrl}${embedUrl.includes('?') ? '&' : '?'}autoplay=1`;
    setSrc(withAutoplay);
    setIframeReady(false);
  }, [embedUrl]);

  return (
    <div
      ref={containerRef}
      className="relative block aspect-video w-full overflow-hidden rounded-b-lg bg-slate-100 ring-1 ring-inset ring-slate-200/80"
    >
      {src ? (
        <>
          <iframe
            title="Video"
            src={src}
            className={cn(
              'absolute inset-0 h-full w-full transition-opacity duration-500',
              iframeReady ? 'opacity-100' : 'opacity-0',
            )}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
            loading="lazy"
            onLoad={() => setIframeReady(true)}
          />
          {/* Cover black iframe paint with light placeholder until ready */}
          {!iframeReady && (
            <div
              className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-slate-100"
              aria-hidden
            >
              <div className="h-10 w-10 rounded-full border-2 border-primary-200 border-t-primary-500 animate-spin" />
              <span className="text-xs font-medium text-slate-500">Loading player…</span>
            </div>
          )}
        </>
      ) : (
        <button
          type="button"
          onClick={loadPlayer}
          className={cn(
            'absolute inset-0 flex flex-col items-center justify-center gap-2 outline-none focus-visible:ring-2 focus-visible:ring-primary-400',
            posterUrl
              ? 'text-white'
              : 'bg-gradient-to-b from-slate-100 to-slate-200 text-slate-700',
          )}
        >
          {posterUrl && (
            <>
              <img
                src={posterUrl}
                alt=""
                className="absolute inset-0 h-full w-full object-cover"
                loading="eager"
                decoding="async"
                onError={() => setPosterFailed(true)}
              />
              {/* So play button stays readable on any thumbnail */}
              <div className="absolute inset-0 bg-slate-900/35" aria-hidden />
            </>
          )}
          <span className="relative z-10 flex h-14 w-14 items-center justify-center rounded-full bg-red-600 shadow-lg transition-transform hover:scale-105">
            <svg className="ml-1 h-7 w-7 text-white" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <path d="M8 5v14l11-7z" />
            </svg>
          </span>
          <span
            className={cn(
              'relative z-10 text-xs font-medium drop-shadow',
              posterUrl ? 'text-white' : 'text-slate-600',
            )}
          >
            Click to load video
          </span>
          <a
            href={watchUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              'relative z-10 mt-1 text-[11px] underline',
              posterUrl ? 'text-white/85 hover:text-white' : 'text-slate-500 hover:text-slate-700',
            )}
            onClick={(e) => e.stopPropagation()}
          >
            Don&apos;t want to wait? Open in new window
          </a>
        </button>
      )}
    </div>
  );
}

/**
 * Render diagram via Kroki API (same service the backend uses in diagram_renderer.py).
 * Kroki handles mermaid, plantuml, graphviz etc. with full Unicode support.
 */
const KROKI_URL = 'https://kroki.io';
const diagramCache = new Map<string, string>();
const diagramFailureReported = new Set<string>();
const diagramReportContext: { userId?: string; goalId?: number; sessionIndex?: number } = {};
const MERMAID_HEAD_RE = /^\s*(graph\s+(?:TD|LR|RL|BT|TB)|flowchart\s+(?:TD|LR|RL|BT|TB)|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|gitGraph|journey|mindmap)\b/i;

function normalizeDiagramSource(code: string): string {
  let c = code.trim();
  // Some generators include a leading "DIAGRAM" / "MERMAID" marker line inside the block.
  c = c.replace(/^\s*(diagram|mermaid)\s*\n/i, '');
  return c.trim();
}

function sanitizeMermaidForKroki(code: string): string {
  let c = normalizeDiagramSource(code).replace(/\r\n/g, '\n');
  // If the whole diagram was flattened to one line with semicolons, expand it.
  if (!c.includes('\n') && c.includes(';')) {
    c = c.split(';').map((s) => s.trim()).filter(Boolean).join(';\n');
  }
  // Quote [] node labels containing non-ASCII/punctuation to avoid parser edge cases.
  c = c.replace(/\b([A-Za-z_][A-Za-z0-9_]*)\[([^\]\n]+)\]/g, (_m, id: string, label: string) => {
    const t = label.trim();
    const stripped = t.replace(/^['"]+|['"]+$/g, '').trim();
    // Replace stray inner double quotes to avoid broken Mermaid strings.
    const normalized = stripped.replace(/"/g, "'");
    const needsQuote = /[^A-Za-z0-9 _-]/.test(normalized) || normalized !== t;
    if (!needsQuote) return `${id}[${normalized}]`;
    return `${id}["${normalized}"]`;
  });
  // Normalize edge labels with broken quotes: A -->|foo "bar| B  => A -->|foo 'bar| B
  c = c.replace(/\|([^|\n]*)\|/g, (_m, edgeLabel: string) => `|${edgeLabel.replace(/"/g, "'")}|`);
  return c.trim();
}

function detectDiagramType(langLower: string | undefined, code: string): 'mermaid' | 'plantuml' | 'graphviz' | null {
  const lang = (langLower ?? '').toLowerCase();
  const compact = lang.replace(/[^a-z]/g, '');
  const source = normalizeDiagramSource(code);

  if (compact.includes('diagram') || compact === 'mermaid') return 'mermaid';
  if (compact === 'plantuml') return 'plantuml';
  if (compact === 'graphviz' || compact === 'dot') return 'graphviz';

  // Fallback: no/unknown lang but code body is clearly mermaid syntax
  if (MERMAID_HEAD_RE.test(source)) return 'mermaid';
  return null;
}

function hashSnippet(text: string): string {
  let h = 0;
  for (let i = 0; i < text.length; i += 1) h = ((h << 5) - h + text.charCodeAt(i)) | 0;
  return String(h);
}

function redactSnippet(text: string): string {
  return text
    .replace(/https?:\/\/\S+/gi, '[url]')
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, '[email]')
    .replace(/\b\d{6,}\b/g, '[number]')
    .slice(0, 1800);
}

async function renderDiagramViaKroki(code: string, type = 'mermaid'): Promise<string> {
  const normalized = normalizeDiagramSource(code);
  const key = `${type}:${normalized}`;
  const cached = diagramCache.get(key);
  if (cached) return cached;
  const candidates = type === 'mermaid'
    ? [normalized, sanitizeMermaidForKroki(normalized)]
    : [normalized];
  let lastError = 'Kroki request failed';
  for (const candidate of candidates) {
    const resp = await fetch(`${KROKI_URL}/${type}/svg`, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: candidate,
    });
    if (resp.ok) {
      const svg = await resp.text();
      diagramCache.set(key, svg);
      return svg;
    }
    const detail = await resp.text().catch(() => '');
    lastError = `Kroki ${resp.status}${detail ? `: ${detail.slice(0, 180)}` : ''}`;
  }
  throw new Error(lastError);
}

function DiagramBlock({ chart, type = 'mermaid' }: { chart: string; type?: string }) {
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    renderDiagramViaKroki(normalizeDiagramSource(chart), type).then(
      (rendered) => { if (!cancelled) setSvg(rendered); },
      (err: unknown) => {
        if (!cancelled) {
          setError(true);
          const msg = err instanceof Error ? err.message : String(err);
          if (import.meta.env.DEV) {
            console.warn(`Diagram rendering failed: type=${type}; ${msg}; chart=${chart.slice(0, 500)}`);
          }
          const normalized = normalizeDiagramSource(chart);
          const snippetHash = hashSnippet(`${type}:${normalized}`);
          if (!diagramFailureReported.has(snippetHash)) {
            diagramFailureReported.add(snippetHash);
            void reportDiagramRenderFailureApi({
              user_id: diagramReportContext.userId,
              goal_id: diagramReportContext.goalId,
              session_index: diagramReportContext.sessionIndex,
              diagram_type: type,
              snippet: redactSnippet(normalized),
              error: msg.slice(0, 500),
              page_url: window.location.pathname,
            }).catch(() => {
              /* non-blocking telemetry */
            });
          }
        }
      },
    );
    return () => { cancelled = true; };
  }, [chart, type]);

  if (error) {
    return (
      <div className="not-prose my-5 overflow-hidden rounded-xl border border-slate-200 bg-slate-900 shadow-sm">
        <div className="border-b border-slate-700/50 bg-slate-800/80 px-4 py-1.5">
          <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">{type}</span>
        </div>
        <pre className="overflow-x-auto p-4 text-[13px] leading-relaxed text-slate-100 whitespace-pre-wrap"><code>{chart}</code></pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="not-prose my-6 flex justify-center rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <div className="h-4 w-4 rounded-full border-2 border-slate-200 border-t-slate-500 animate-spin" />
          Rendering diagram…
        </div>
      </div>
    );
  }

  return (
    <div className="not-prose my-6 flex justify-center overflow-x-auto rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="[&>svg]:max-w-full" dangerouslySetInnerHTML={{ __html: svg }} />
    </div>
  );
}

function isSpecialBlock(children: React.ReactNode): 'checkpoint' | 'reflection' | null {
  const text = React.Children.toArray(children)
    .map((c) => (typeof c === 'string' ? c : ''))
    .join('');
  if (/checkpoint\s+challenge/i.test(text)) return 'checkpoint';
  if (/reflection\s+pause/i.test(text)) return 'reflection';
  return null;
}

/** Markdown components with product-grade styling */
const lessonMarkdownComponents: Components = {
  a({ href, children, ...props }) {
    if (!href) return <a {...props}>{children}</a>;
    const embed = youtubeEmbedUrl(href);
    if (embed) {
      const hasThumb = React.isValidElement(children) && children.type === 'img';
      return (
        <span className="not-prose my-6 block w-full overflow-hidden rounded-xl border border-slate-200 bg-slate-50 shadow-sm">
          {hasThumb && (
            <div className="flex justify-center bg-slate-100/80 px-3 py-2 border-b border-slate-200">
              <span className="inline-block max-h-40 rounded-lg overflow-hidden ring-1 ring-slate-200/80 [&_img]:max-h-40 [&_img]:w-auto [&_img]:object-contain">
                {children}
              </span>
            </div>
          )}
          <LazyYouTubeEmbed embedUrl={embed} watchUrl={href} />
          <div className="px-3 py-2 border-t border-slate-200 bg-white">
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-primary-600 hover:text-primary-700 hover:underline">
              Open in new window
            </a>
          </div>
        </span>
      );
    }
    if (isDirectVideoUrl(href)) {
      const hasThumb = React.isValidElement(children) && children.type === 'img';
      return (
        <span className="not-prose my-6 block w-full overflow-hidden rounded-xl border border-slate-200 bg-black">
          {hasThumb && (
            <div className="flex justify-center bg-slate-900/50 px-2 py-2 [&_img]:max-h-36 [&_img]:object-contain">{children}</div>
          )}
          <video src={href} controls className="max-h-[480px] w-full" playsInline>
            <a href={href} target="_blank" rel="noopener noreferrer">Open in new window</a>
          </video>
          <div className="bg-slate-900 px-3 py-2">
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-primary-300 hover:text-primary-200 hover:underline">
              Open in new window
            </a>
          </div>
        </span>
      );
    }
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary-600 underline decoration-primary-300 underline-offset-2 hover:text-primary-700 hover:decoration-primary-500 transition-colors" {...props}>
        {children}
      </a>
    );
  },

  blockquote({ children }) {
    const kind = isSpecialBlock(children);
    if (kind === 'checkpoint') {
      return (
        <div className="not-prose my-6 rounded-xl border border-amber-200 bg-gradient-to-br from-amber-50 to-orange-50 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-400 text-white text-xs font-bold">?</span>
            <span className="text-sm font-semibold text-amber-800 uppercase tracking-wide">Checkpoint Challenge</span>
          </div>
          <div className="text-sm text-amber-900 leading-relaxed [&>p:first-child]:mt-0">{children}</div>
        </div>
      );
    }
    if (kind === 'reflection') {
      return (
        <div className="not-prose my-6 rounded-xl border border-violet-200 bg-gradient-to-br from-violet-50 to-purple-50 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-violet-400 text-white text-xs">
              <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5"><path d="M10 2a8 8 0 100 16 8 8 0 000-16zM9 7a1 1 0 112 0v4a1 1 0 11-2 0V7zm1 8a1 1 0 100-2 1 1 0 000 2z" /></svg>
            </span>
            <span className="text-sm font-semibold text-violet-800 uppercase tracking-wide">Reflection Pause</span>
          </div>
          <div className="text-sm text-violet-900 leading-relaxed [&>p:first-child]:mt-0">{children}</div>
        </div>
      );
    }
    return (
      <blockquote className="not-prose my-5 rounded-lg border-l-4 border-primary-400 bg-primary-50/60 py-3 px-5 text-sm text-slate-700 leading-relaxed [&>p]:my-1">
        {children}
      </blockquote>
    );
  },

  code({ className, children, ...props }) {
    const match = /language-([^\s]+)/.exec(className || '');
    const lang = match?.[1];
    const code = String(children).replace(/\n$/, '');
    const langLower = lang?.toLowerCase();
    const diagramType = detectDiagramType(langLower, code);
    if (diagramType) {
      return <DiagramBlock chart={code} type={diagramType} />;
    }
    const node = (props as Record<string, unknown>).node as Record<string, unknown> | undefined;
    const pos = node?.position as Record<string, Record<string, number>> | undefined;
    const isBlock = (pos?.start?.line !== pos?.end?.line) || code.includes('\n');
    if (isBlock || lang) {
      return (
        <div className="not-prose group relative my-5 overflow-hidden rounded-xl border border-slate-200 bg-slate-900 shadow-sm">
          {lang && (
            <div className="flex items-center justify-between border-b border-slate-700/50 bg-slate-800/80 px-4 py-1.5">
              <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">{lang}</span>
            </div>
          )}
          <pre className="overflow-x-auto p-4 text-[13px] leading-relaxed text-slate-100">
            <code className={className}>{children}</code>
          </pre>
        </div>
      );
    }
    return (
      <code className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[13px] font-medium text-slate-800 ring-1 ring-inset ring-slate-200">
        {children}
      </code>
    );
  },

  pre({ children }) {
    return <>{children}</>;
  },

  table({ children }) {
    return (
      <div className="not-prose my-6 overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
        <table className="min-w-full divide-y divide-slate-200 text-sm">{children}</table>
      </div>
    );
  },
  thead({ children }) {
    return <thead className="bg-slate-50">{children}</thead>;
  },
  th({ children }) {
    return <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">{children}</th>;
  },
  td({ children }) {
    return <td className="px-4 py-2.5 text-slate-700 border-t border-slate-100">{children}</td>;
  },

  img({ src, alt, ...props }) {
    return (
      <span className="not-prose my-6 block overflow-hidden rounded-xl border border-slate-200 bg-slate-50 shadow-sm">
        <img src={src} alt={alt || ''} className="mx-auto max-h-96 w-auto object-contain" loading="lazy" {...props} />
        {alt && <span className="block px-4 py-2 text-center text-xs text-slate-500 italic">{alt}</span>}
      </span>
    );
  },

  hr() {
    return (
      <div className="not-prose my-8 flex items-center justify-center gap-2">
        <span className="h-1 w-1 rounded-full bg-slate-300" />
        <span className="h-1 w-1 rounded-full bg-slate-300" />
        <span className="h-1 w-1 rounded-full bg-slate-300" />
      </div>
    );
  },

  ul({ children }) {
    return <ul className="my-3 space-y-1.5 pl-1 [&>li]:flex [&>li]:gap-2 [&>li]:items-start">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="my-3 space-y-1.5 pl-1 list-none counter-reset-[li] [&>li]:flex [&>li]:gap-2 [&>li]:items-start [&>li]:before:content-[counter(li)_'.'] [&>li]:before:counter-increment-[li] [&>li]:before:text-xs [&>li]:before:font-semibold [&>li]:before:text-primary-500 [&>li]:before:mt-0.5 [&>li]:before:shrink-0">{children}</ol>;
  },
  li({ children, ...props }) {
    const liNode = (props as Record<string, unknown>).node as Record<string, Record<string, unknown>> | undefined;
    const isOrdered = liNode?.parent?.type === 'list' && liNode?.parent?.ordered;
    return (
      <li>
        {!isOrdered && <span className="mt-1.5 flex h-1.5 w-1.5 shrink-0 rounded-full bg-primary-400" aria-hidden />}
        <span className="min-w-0">{children}</span>
      </li>
    );
  },
};

/** Build a set of character indices that fall inside fenced code blocks */
function fencedRanges(text: string): Array<[number, number]> {
  const ranges: Array<[number, number]> = [];
  const re = /^(`{3,})[^\n]*$/gm;
  let open: { index: number; ticks: string } | null = null;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (!open) {
      open = { index: m.index, ticks: m[1] };
    } else if (m[1].length >= open.ticks.length) {
      ranges.push([open.index, m.index + m[0].length]);
      open = null;
    }
  }
  if (open) ranges.push([open.index, text.length]);
  return ranges;
}

function isInsideFence(idx: number, ranges: Array<[number, number]>): boolean {
  return ranges.some(([a, b]) => idx >= a && idx < b);
}

function parseSections(doc: string | Record<string, unknown> | undefined): ContentSection[] {
  if (!doc) return [];
  const text = typeof doc === 'string' ? doc : '';
  if (!text) return [{ title: 'Content', markdown: JSON.stringify(doc, null, 2) }];
  const ranges = fencedRanges(text);
  const indices: Array<{ title: string; index: number }> = [];
  const headingRe = /^(#{1,3})\s+(.+)$/gm;
  let m: RegExpExecArray | null;
  while ((m = headingRe.exec(text)) !== null) {
    if (!isInsideFence(m.index, ranges)) {
      indices.push({ title: m[2].trim(), index: m.index });
    }
  }
  if (indices.length === 0) return [{ title: 'Content', markdown: text }];
  return indices.map((h, i) => ({
    title: h.title,
    markdown: text.slice(h.index, indices[i + 1]?.index ?? text.length).trim(),
  }));
}

function parseSubsections(markdown: string): Array<{ title: string; markdown: string }> {
  if (!markdown?.trim()) return [{ title: '', markdown: '' }];
  const ranges = fencedRanges(markdown);
  const h3Re = /^###\s+(.+)$/gm;
  const subs: Array<{ title: string; start: number; endOfLine: number }> = [];
  let match: RegExpExecArray | null;
  while ((match = h3Re.exec(markdown)) !== null) {
    if (!isInsideFence(match.index, ranges)) {
      subs.push({
        title: match[1].trim(),
        start: match.index,
        endOfLine: match.index + match[0].length,
      });
    }
  }
  if (subs.length === 0) return [{ title: '', markdown: markdown.trim() }];
  const result: Array<{ title: string; markdown: string }> = [];
  const intro = markdown.slice(0, subs[0].start).trim();
  if (intro) result.push({ title: '', markdown: intro });
  for (let i = 0; i < subs.length; i++) {
    const end = subs[i + 1]?.start ?? markdown.length;
    const content = markdown.slice(subs[i].endOfLine, end).trim();
    result.push({ title: subs[i].title, markdown: content });
  }
  return result;
}

export function LearningSessionPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { userId } = useAuthContext();
  const { updateGoal } = useGoalsContext();
  const { data: config } = useAppConfig();
  const { activeGoal } = useActiveGoal();

  const state = location.state as LocationState | null;

  const resolvedGoalId = (() => {
    if (state?.goalId != null) return state.goalId;
    return activeGoal?.id ?? null;
  })();

  const resolvedSessionIndex = (() => {
    if (state?.sessionIndex != null) return state.sessionIndex;
    if (!activeGoal?.learning_path) return null;
    const idx = activeGoal.learning_path.findIndex(
      (s) => !s.if_learned,
    );
    return idx >= 0 ? idx : null;
  })();

  const goalId = resolvedGoalId as number;
  const sessionIndex = resolvedSessionIndex as number;

  useEffect(() => {
    diagramReportContext.userId = userId ?? undefined;
    diagramReportContext.goalId = goalId;
    diagramReportContext.sessionIndex = sessionIndex;
  }, [userId, goalId, sessionIndex]);

  useEffect(() => {
    if (resolvedGoalId == null || resolvedSessionIndex == null) {
      navigate('/learning-path', { replace: true });
    }
  }, [resolvedGoalId, resolvedSessionIndex, navigate]);

  const { data: _runtimeStateData, refetch: refetchRuntime } = useGoalRuntimeState(userId ?? undefined, goalId ?? undefined);

  const { data: contentCacheResult, isLoading: isCheckingCache } = useGetLearningContent(
    userId ?? undefined,
    goalId ?? undefined,
    sessionIndex ?? undefined,
  );

  useEffect(() => {
    if (contentCacheResult) {
      console.log('contentCacheResult:', contentCacheResult);
      // 方便直接复制
      (window as Window & { __contentCacheResult?: unknown }).__contentCacheResult = contentCacheResult;
    }
  }, [contentCacheResult]);

  const generateMutation = useGenerateLearningContent();
  const deleteMutation = useDeleteLearningContent();
  const sessionActivityMutation = useSessionActivity();
  const completeSessionMutation = useCompleteSession();
  const submitFeedbackMutation = useSubmitContentFeedback();
  const chatMutation = useChatWithTutor();

  type ContentData = NonNullable<typeof contentCacheResult>['data'];
  const [content, setContent] = useState<ContentData>(null);

  useEffect(() => {
    if (content) {
      console.log('final content used by page:', content);
      (window as Window & { __learningContent?: unknown }).__learningContent = content;
    }
  }, [content]);
  
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
        goal_context: normalizeGoalContext(activeGoal.goal_context),
        user_id: userId,
        goal_id: goalId,
        session_index: sessionIndex,
      },
      {
        onSuccess: (data) => {
          setContent(data);
          setIsGenerating(false);
        },
        onError: () => {
          setGenerateError('Failed to generate content. Please try again.');
          setIsGenerating(false);
        },
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isCheckingCache, contentCacheResult?.status]);

  const sections: ContentSection[] = content?.view_model?.sections?.length
    ? content.view_model.sections
    : parseSections(content?.document);

  const [currentSectionIdx, setCurrentSectionIdx] = useState(0);
  const [quizUnlocked, setQuizUnlocked] = useState(false);
  const [isOnQuiz, setIsOnQuiz] = useState(false);

  useEffect(() => {
    if (sections.length > 0 && currentSectionIdx >= sections.length - 1) setQuizUnlocked(true);
  }, [currentSectionIdx, sections.length]);

  useEffect(() => {
    setCurrentSectionIdx(0);
    setQuizUnlocked(false);
    setIsOnQuiz(false);
    setIsFeedbackOpen(false);
  }, [content]);

  // Heartbeat
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (!userId || goalId == null || sessionIndex == null) return;
    const interval = (config?.motivational_trigger_interval_secs ?? 30) * 1000;
    heartbeatRef.current = setInterval(() => {
      sessionActivityMutation.mutate({
        user_id: userId,
        goal_id: goalId,
        session_index: sessionIndex,
        event_type: 'heartbeat',
      });
    }, interval);
    return () => {
      if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, goalId, sessionIndex, config?.motivational_trigger_interval_secs]);

  const [masteryResult, setMasteryResult] = useState<MasteryEvaluationResponse | null>(null);
  const [sessionCompleted, setSessionCompleted] = useState(false);
  const hasMastered = masteryResult?.is_mastered === true;
  const isCompleteEnabled = hasMastered;
  const [isFeedbackOpen, setIsFeedbackOpen] = useState(false);

  const [contentBiasAudit, setContentBiasAudit] = useState<Record<string, unknown> | null>(null);
  const [chatbotBiasAudit, setChatbotBiasAudit] = useState<Record<string, unknown> | null>(null);

  const learnerInformationForAudit =
    (activeGoal?.learner_profile as { learner_information?: string } | undefined)?.learner_information ?? '';

  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const [chatInput, setChatInput] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);
  const quizRef = useRef<HTMLDivElement | null>(null);
  const sectionRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!content) {
      setContentBiasAudit(null);
      return;
    }
    const doc =
      typeof content.document === 'string'
        ? content.document
        : JSON.stringify(content.document ?? '');
    let cancelled = false;
    auditContentBiasApi({
      generated_content: doc,
      learner_information: learnerInformationForAudit,
    })
      .then((r) => {
        if (!cancelled) setContentBiasAudit(r);
      })
      .catch(() => {
        if (!cancelled) setContentBiasAudit(null);
      });
    return () => {
      cancelled = true;
    };
  }, [content, learnerInformationForAudit]);

  useEffect(() => {
    setChatMessages([]);
    setChatbotBiasAudit(null);
  }, [goalId, sessionIndex]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

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
      });
      setChatMessages((prev) => [...prev, { role: 'assistant', content: res.response }]);
      try {
        const audit = await auditChatbotBiasApi({
          tutor_responses: res.response,
          learner_information: learnerInformationForAudit,
        });
        setChatbotBiasAudit(audit);
      } catch {
        setChatbotBiasAudit(null);
      }
    } catch {
      setChatMessages((prev) => [...prev, { role: 'assistant', content: 'Sorry, I encountered an error.' }]);
      setChatbotBiasAudit(null);
    }
  }, [
    chatInput,
    chatMessages,
    userId,
    goalId,
    sessionIndex,
    activeGoal,
    chatMutation,
    updateGoal,
    learnerInformationForAudit,
  ]);

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
        feedback: {
          clarity: clarityRating,
          relevance: relevanceRating,
          depth: depthRating,
          comments: feedbackComments,
          session_index: sessionIndex,
        },
      });
      setFeedbackSubmitted(true);
      if (res.goal) updateGoal(goalId, res.goal);
    } catch {
      /* ignore */
    }
  }, [
    userId,
    goalId,
    clarityRating,
    relevanceRating,
    depthRating,
    feedbackComments,
    sessionIndex,
    submitFeedbackMutation,
    updateGoal,
  ]);

  const handleBack = useCallback(async () => {
    if (userId && goalId != null && sessionIndex != null) {
      await sessionActivityMutation
        .mutateAsync({
          user_id: userId,
          goal_id: goalId,
          session_index: sessionIndex,
          event_type: 'end',
        })
        .catch(() => {});
    }
    navigate('/learning-path');
  }, [userId, goalId, sessionIndex, sessionActivityMutation, navigate]);

  const ensureCached = useCallback(async () => {
    if (!userId || goalId == null || sessionIndex == null || !activeGoal) return;
    const pathSession = activeGoal.learning_path?.[sessionIndex];
    if (!pathSession) return;
    await generateLearningContentApi({
      learner_profile: JSON.stringify(activeGoal.learner_profile ?? {}),
      learning_path: JSON.stringify(activeGoal.learning_path ?? []),
      learning_session: JSON.stringify(pathSession),
      use_search: true,
      allow_parallel: true,
      with_quiz: true,
      goal_context: normalizeGoalContext(activeGoal.goal_context),
      user_id: userId,
      goal_id: goalId,
      session_index: sessionIndex,
    });
  }, [userId, goalId, sessionIndex, activeGoal]);

  const handleRegenerate = useCallback(async () => {
    if (!userId || goalId == null || sessionIndex == null) return;
    await sessionActivityMutation
      .mutateAsync({
        user_id: userId,
        goal_id: goalId,
        session_index: sessionIndex,
        event_type: 'end',
      })
      .catch(() => {});
    setContent(null);
    setGenerateError(null);
    setMasteryResult(null);
    setContentBiasAudit(null);
    hasTriggeredGenRef.current = false;
    deleteMutation.mutate({ userId, goalId, sessionIndex });
  }, [userId, goalId, sessionIndex, sessionActivityMutation, deleteMutation]);

  const handleComplete = useCallback(async () => {
    if (!userId || goalId == null || sessionIndex == null) return;
    try {
      const res = await completeSessionMutation.mutateAsync({
        user_id: userId,
        goal_id: goalId,
        session_index: sessionIndex,
      });
      if (res.goal) updateGoal(goalId, res.goal);
      setSessionCompleted(true);
      void refetchRuntime();
    } catch {
      /* ignore */
    }
  }, [userId, goalId, sessionIndex, completeSessionMutation, updateGoal, refetchRuntime]);

  const totalSessions = activeGoal?.learning_path?.length ?? 0;
  const hasNextSession = sessionIndex != null && sessionIndex + 1 < totalSessions;

  const handleNextSession = useCallback(() => {
    if (goalId == null || sessionIndex == null || !hasNextSession) return;
    const nextIdx = sessionIndex + 1;
    if (userId) {
      sessionActivityMutation
        .mutateAsync({ user_id: userId, goal_id: goalId, session_index: nextIdx, event_type: 'start' })
        .catch(() => {});
    }
    navigate('/learning-session', { state: { goalId, sessionIndex: nextIdx } });
  }, [goalId, sessionIndex, hasNextSession, userId, sessionActivityMutation, navigate]);

  if (goalId == null || sessionIndex == null) return null;

  const pathSession = activeGoal?.learning_path?.[sessionIndex];
  const sessionTitle = (pathSession?.title as string | undefined) ?? `Session ${sessionIndex + 1}`;

  if (isCheckingCache || isGenerating) {
    return <SessionLoadingPanel sessionTitle={sessionTitle} />;
  }

  if (generateError) {
    return (
      <div className="max-w-3xl space-y-4">
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          {generateError}
        </div>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={handleBack}>
            Back
          </Button>
          <Button
            onClick={() => {
              setGenerateError(null);
              handleRegenerate();
            }}
          >
            Retry
          </Button>
        </div>
      </div>
    );
  }

  if (!content)
    return (
      <div className="flex flex-col items-center justify-center min-h-96 text-slate-400 text-sm">
        No content available.
      </div>
    );

  const currentSection = sections[currentSectionIdx];
  const references = content.view_model?.references ?? [];
  const audioUrl = absolutizeUrl(content.audio_url);

  const showQuiz = quizUnlocked && Boolean(content.quizzes);

  return (
    <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 pb-12">
      <div className="pt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px] items-start">
        <div className="min-w-0 space-y-5 pl-2">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="space-y-1 min-w-0">
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <button type="button" onClick={handleBack} className="hover:text-slate-600 transition-colors">Learning path</button>
                <svg className="h-3 w-3 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                <span className="text-slate-500">Session {sessionIndex + 1}</span>
              </div>
              <h2 className="text-2xl font-bold tracking-tight text-slate-900">{sessionTitle}</h2>
              <p className="text-sm text-slate-500">
                Work through each section, then take the quiz to complete this session.
              </p>
            </div>
            <div className="flex gap-2 shrink-0 items-center">
              <Button size="sm" variant="secondary" onClick={handleRegenerate} className="gap-1.5">
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                Regenerate
              </Button>
            </div>
          </div>

          {content.content_format === 'audio_enhanced' && audioUrl && (
            <div className="rounded-xl border border-blue-200 bg-gradient-to-r from-blue-50 to-indigo-50 p-4 shadow-sm">
              <div className="flex items-center gap-2 mb-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-100">
                  <svg className="h-4 w-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15.536 8.464a5 5 0 010 7.072M18.364 5.636a9 9 0 010 12.728M9 12h.01M12 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                </span>
                <p className="text-sm font-semibold text-blue-800">Audio version available</p>
              </div>
              <audio controls src={audioUrl} className="w-full rounded-lg" />
            </div>
          )}
          {content.content_format === 'visual_enhanced' && (
            <div className="flex items-center gap-2 rounded-xl border border-purple-200 bg-gradient-to-r from-purple-50 to-pink-50 px-4 py-3 shadow-sm">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-100">
                <svg className="h-4 w-4 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
              </span>
              <p className="text-sm font-medium text-purple-800">This session includes enhanced visual elements.</p>
            </div>
          )}

          <ContentBiasAuditPanel audit={contentBiasAudit} />

          {/* ── Progress bar ── */}
          {sections.length > 1 && !isOnQuiz && (
            <div className="flex items-center gap-1.5">
              {sections.map((_, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => { setIsOnQuiz(false); setCurrentSectionIdx(i); }}
                  className="group relative flex-1 h-1.5 rounded-full overflow-hidden"
                  aria-label={`Go to section ${i + 1}`}
                >
                  <span className={cn(
                    'absolute inset-0 rounded-full transition-colors duration-300',
                    i < currentSectionIdx ? 'bg-primary-500' : i === currentSectionIdx ? 'bg-primary-400' : 'bg-slate-200 group-hover:bg-slate-300',
                  )} />
                </button>
              ))}
              {showQuiz && (
                <button
                  type="button"
                  onClick={() => { setIsOnQuiz(true); queueMicrotask(() => quizRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })); }}
                  className="group relative flex-1 h-1.5 rounded-full overflow-hidden"
                  aria-label="Go to quiz"
                >
                  <span className="absolute inset-0 rounded-full bg-slate-200 group-hover:bg-slate-300 transition-colors" />
                </button>
              )}
            </div>
          )}

          {/* ── Content card ── */}
          {(currentSection || (showQuiz && isOnQuiz && content.quizzes)) && (
            <div
              ref={isOnQuiz ? quizRef : sectionRef}
              className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
            >
              {!isOnQuiz && currentSection && (
                <>
                  {/* Section header */}
                  <div className="border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white px-6 py-5 md:px-8">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-100 text-sm font-bold text-primary-700">
                          {currentSectionIdx + 1}
                        </span>
                        <div>
                          <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
                            Section {currentSectionIdx + 1} of {sections.length}
                          </p>
                          <h3 className="text-lg font-semibold text-slate-900 leading-snug">{currentSection.title}</h3>
                        </div>
                      </div>
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                        Reading
                      </span>
                    </div>
                  </div>

                  {/* Section body */}
                  <div className="px-6 py-6 md:px-8 md:py-8">
                    <div className="prose prose-slate max-w-none prose-headings:text-slate-900 prose-p:text-slate-700 prose-p:leading-[1.8] prose-li:text-slate-700 prose-strong:text-slate-900">
                      {parseSubsections(transformSectionMarkdown(currentSection.markdown)).map((sub, subIdx) => (
                        <div key={subIdx} className={subIdx > 0 ? 'mt-10 pt-8 border-t border-slate-100' : ''}>
                          {sub.title && (
                            <div className="flex items-center gap-2.5 mb-4">
                              <span className="h-5 w-1 rounded-full bg-primary-400" aria-hidden />
                              <h3 className="text-base font-semibold text-slate-800 m-0">{sub.title}</h3>
                            </div>
                          )}
                          <ReactMarkdown remarkPlugins={[remarkGfm]} components={lessonMarkdownComponents}>
                            {sub.markdown}
                          </ReactMarkdown>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Section footer nav */}
                  <div className="border-t border-slate-100 bg-slate-50/60 px-6 py-4 md:px-8">
                    <div className="flex items-center justify-between">
                      <button
                        type="button"
                        disabled={currentSectionIdx === 0}
                        onClick={() => {
                          setCurrentSectionIdx((i) => {
                            const next = Math.max(0, i - 1);
                            queueMicrotask(() => sectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
                            return next;
                          });
                        }}
                        className={cn(
                          'flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                          currentSectionIdx === 0
                            ? 'text-slate-300 cursor-not-allowed'
                            : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                        )}
                      >
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
                        Previous
                      </button>
                      <span className="text-xs tabular-nums text-slate-400">
                        {currentSectionIdx + 1} / {sections.length}
                      </span>
                      {currentSectionIdx >= sections.length - 1 && showQuiz ? (
                        <button
                          type="button"
                          onClick={() => { setIsOnQuiz(true); queueMicrotask(() => quizRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })); }}
                          className="flex items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-700 transition-colors"
                        >
                          Take Quiz
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                        </button>
                      ) : (
                        <button
                          type="button"
                          disabled={sections.length === 0 || currentSectionIdx >= sections.length - 1}
                          onClick={() => {
                            setCurrentSectionIdx((i) => {
                              const next = Math.min(sections.length - 1, i + 1);
                              queueMicrotask(() => sectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
                              return next;
                            });
                          }}
                          className={cn(
                            'flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                            currentSectionIdx >= sections.length - 1
                              ? 'text-slate-300 cursor-not-allowed'
                              : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                          )}
                        >
                          Next
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                        </button>
                      )}
                    </div>
                  </div>
                </>
              )}

              {showQuiz && isOnQuiz && content.quizzes && (
                <div className="p-6 md:p-8 space-y-6">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-100 text-sm font-bold text-indigo-700">
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                      </span>
                      <div>
                        <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Knowledge check</p>
                        <h3 className="text-lg font-semibold text-slate-900">{sessionTitle}</h3>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => { setIsOnQuiz(false); setCurrentSectionIdx(Math.max(0, sections.length - 1)); }}
                      className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 transition-colors"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
                      Back to lesson
                    </button>
                  </div>
                  <QuizPanel
                    quiz={content.quizzes}
                    userId={userId!}
                    goalId={goalId}
                    sessionIndex={sessionIndex}
                    onMasteryResult={(r) => {
                      setMasteryResult(r);
                      void refetchRuntime();
                    }}
                    ensureCached={ensureCached}
                    onCompleteSession={handleComplete}
                    completeSessionLoading={completeSessionMutation.isPending}
                    completeSessionDisabled={!isCompleteEnabled || completeSessionMutation.isPending}
                    completeSessionHint={
                      !hasMastered
                        ? (masteryResult
                          ? `Score ${Math.round(masteryResult.score_percentage)}% — need ${Math.round(masteryResult.threshold)}% to unlock`
                          : 'Complete the quiz to unlock')
                        : null
                    }
                  />
                </div>
              )}
            </div>
          )}

          {references.length > 0 && (
            <details className="group rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
              <summary className="flex cursor-pointer items-center gap-2 px-5 py-3 text-sm font-medium text-slate-600 select-none hover:bg-slate-50 transition-colors">
                <svg className="h-4 w-4 text-slate-400 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                References
                <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] tabular-nums text-slate-500">{references.length}</span>
              </summary>
              <ol className="border-t border-slate-100 px-5 pb-4 pt-3 space-y-2 text-xs text-slate-500 list-decimal list-inside">
                {references.map((ref) => (
                  <li key={ref.index} className="leading-relaxed">{ref.label}</li>
                ))}
              </ol>
            </details>
          )}

          {quizUnlocked && !feedbackSubmitted && (
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div className="space-y-1">
                  <h3 className="font-semibold text-slate-700 text-sm">Session complete</h3>
                  <p className="text-xs text-slate-500">
                    Feedback is optional. Share a quick rating to help improve future sessions.
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setIsFeedbackOpen((prev) => !prev)}
                >
                  {isFeedbackOpen ? 'Hide feedback' : 'Rate this session'}
                </Button>
              </div>

              {isFeedbackOpen && (
                <div className="space-y-4 pt-2">
                  {[
                    { label: 'Clarity', value: clarityRating, set: setClarityRating },
                    { label: 'Relevance', value: relevanceRating, set: setRelevanceRating },
                    { label: 'Depth', value: depthRating, set: setDepthRating },
                  ].map(({ label, value, set }) => (
                    <div key={label} className="flex items-center gap-3">
                      <span className="text-sm text-slate-600 w-20">{label}</span>
                      <div className="flex gap-1">
                        {[1, 2, 3, 4, 5].map((star) => (
                          <button
                            key={star}
                            type="button"
                            onClick={() => set(star)}
                            className={cn(
                              'text-xl',
                              star <= value ? 'text-amber-400' : 'text-slate-300 hover:text-amber-300',
                            )}
                          >
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
                  <Button
                    size="sm"
                    onClick={handleSubmitFeedback}
                    loading={submitFeedbackMutation.isPending}
                    disabled={
                      clarityRating === 0 ||
                      relevanceRating === 0 ||
                      depthRating === 0 ||
                      submitFeedbackMutation.isPending
                    }
                  >
                    Submit Feedback
                  </Button>
                </div>
              )}
            </div>
          )}
          {feedbackSubmitted && (
            <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-700">
              Thank you for your feedback!
            </div>
          )}

          {sessionCompleted ? (
            <div className="rounded-xl border border-green-300 bg-green-50 p-6 space-y-4">
              <div className="flex items-center gap-3">
                <svg className="w-8 h-8 text-green-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <p className="font-semibold text-green-800">Session completed!</p>
                  <p className="text-sm text-green-600">
                    {hasNextSession
                      ? 'Great job! Ready for the next session?'
                      : 'Congratulations! You have completed all sessions in this learning path.'}
                  </p>
                </div>
              </div>
              <div className="flex gap-3">
                {hasNextSession && (
                  <Button size="lg" onClick={handleNextSession}>
                    Next Session →
                  </Button>
                )}
                <Button size="lg" variant="secondary" onClick={() => navigate('/learning-path')}>
                  Back to Learning Path
                </Button>
              </div>
            </div>
          ) : null}
        </div>

        <aside className="w-full self-start sticky top-6 h-[calc(100vh-48px)] flex flex-col gap-4 min-h-0">
          <div className="rounded-2xl border border-slate-200 bg-white shadow-sm shrink-0 overflow-hidden">
            <div className="border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white px-4 py-3">
              <div className="flex items-center justify-between">
                <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Session overview</p>
                <span className="text-[11px] tabular-nums text-slate-400">
                  {Math.min(currentSectionIdx + 1, sections.length)}/{sections.length}
                </span>
              </div>
              {sections.length > 0 && (
                <div className="mt-2 h-1 w-full rounded-full bg-slate-100 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary-500 transition-all duration-500"
                    style={{ width: `${((currentSectionIdx + 1) / sections.length) * 100}%` }}
                  />
                </div>
              )}
            </div>
            <div className="max-h-64 overflow-y-auto p-2">
              {sections.map((s, i) => {
                const isActive = i === currentSectionIdx && !isOnQuiz;
                const isCompleted = i < currentSectionIdx;
                return (
                  <button
                    key={i}
                    type="button"
                    onClick={() => { setIsOnQuiz(false); setCurrentSectionIdx(i); }}
                    className={cn(
                      'w-full flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs transition-all duration-150',
                      isActive
                        ? 'bg-primary-50 text-primary-800 shadow-sm ring-1 ring-primary-200'
                        : 'hover:bg-slate-50 text-slate-600',
                    )}
                  >
                    <span
                      className={cn(
                        'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold transition-colors',
                        isActive && 'bg-primary-500 text-white shadow-sm',
                        isCompleted && 'bg-emerald-500 text-white',
                        !isActive && !isCompleted && 'bg-slate-100 text-slate-400',
                      )}
                    >
                      {isCompleted ? (
                        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                      ) : (
                        i + 1
                      )}
                    </span>
                    <span className={cn('truncate', isActive && 'font-medium')}>{s.title}</span>
                  </button>
                );
              })}
              {showQuiz && (
                <button
                  type="button"
                  onClick={() => { setIsOnQuiz(true); quizRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }}
                  className={cn(
                    'mt-0.5 w-full flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs transition-all duration-150',
                    isOnQuiz
                      ? 'bg-indigo-50 text-indigo-800 shadow-sm ring-1 ring-indigo-200'
                      : 'hover:bg-slate-50 text-slate-600',
                  )}
                >
                  <span className={cn(
                    'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold',
                    isOnQuiz ? 'bg-indigo-500 text-white shadow-sm' : quizUnlocked ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-100 text-slate-400',
                  )}>
                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4" /></svg>
                  </span>
                  <span className={cn('truncate', isOnQuiz && 'font-medium')}>Quiz</span>
                  {!quizUnlocked && (
                    <svg className="ml-auto h-3 w-3 text-slate-300 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg>
                  )}
                </button>
              )}
            </div>
          </div>

          {/* Ami AI: same 320px column as Session overview — aligned vertical axis */}
          <div className="hidden lg:flex mt-auto shrink-0 h-[420px] w-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl z-40">
        <div className="border-b border-slate-100 px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-800">Ami AI</p>
              <p className="mt-1 text-xs text-slate-500">Available for this lesson</p>
            </div>
            <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700">
              Ready
            </span>
          </div>
          <div className="mt-3 space-y-2">
            <ChatbotBiasAuditPanel audit={chatbotBiasAudit} />
          </div>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
          {chatMessages.length === 0 && (
            <div className="rounded-xl bg-slate-50 px-3 py-3 text-sm text-slate-500">
              Ask me about this lesson, vocabulary, pronunciation, or examples.
            </div>
          )}
          {chatMessages.map((msg, i) => (
            <div
              key={i}
              className={cn('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}
            >
              <div
                className={cn(
                  'max-w-[88%] rounded-2xl px-3 py-2.5 text-sm',
                  msg.role === 'user' ? 'bg-primary-600 text-white' : 'bg-slate-100 text-slate-800',
                )}
              >
                {msg.content}
              </div>
            </div>
          ))}
          {chatMutation.isPending && (
            <div className="flex justify-start">
              <div className="bg-slate-100 rounded-2xl px-3 py-2 text-sm text-slate-400">Thinking…</div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>
        <div className="border-t border-slate-100 p-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendChat();
                }
              }}
              placeholder="Ask Ami about this lesson…"
              className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-400"
            />
            <Button
              size="sm"
              onClick={handleSendChat}
              disabled={!chatInput.trim() || chatMutation.isPending}
            >
              Send
            </Button>
          </div>
        </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
