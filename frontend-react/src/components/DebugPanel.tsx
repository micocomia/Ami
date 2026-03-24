import { useState, useEffect, useCallback, useRef } from 'react';
import { cn } from '@/lib/cn';

/* ------------------------------------------------------------------ */
/*  API Log store — filled by axios interceptor, read by panel        */
/* ------------------------------------------------------------------ */

export interface ApiLogEntry {
  id: number;
  ts: number;
  method: string;
  url: string;
  status?: number;
  requestBody?: unknown;
  responseBody?: unknown;
  error?: string;
  durationMs?: number;
}

let _nextId = 1;
let _logs: ApiLogEntry[] = [];
let _listeners: Array<() => void> = [];

function notify() {
  _listeners.forEach((fn) => fn());
}

export function pushApiLog(entry: Omit<ApiLogEntry, 'id'>) {
  _logs = [{ ...entry, id: _nextId++ }, ..._logs].slice(0, 200);
  notify();
}

export function clearApiLogs() {
  _logs = [];
  _nextId = 1;
  notify();
}

function useApiLogs() {
  const [, setTick] = useState(0);
  useEffect(() => {
    const cb = () => setTick((t) => t + 1);
    _listeners.push(cb);
    return () => {
      _listeners = _listeners.filter((fn) => fn !== cb);
    };
  }, []);
  return _logs;
}

/* ------------------------------------------------------------------ */
/*  App State event store — push from anywhere, inspect in panel      */
/* ------------------------------------------------------------------ */

export interface AppStateEntry {
  id: number;
  ts: number;
  label: string;
  data: Record<string, unknown>;
}

let _stateNextId = 1;
let _stateEvents: AppStateEntry[] = [];
let _stateListeners: Array<() => void> = [];

function notifyState() {
  _stateListeners.forEach((fn) => fn());
}

export function pushAppState(label: string, data: Record<string, unknown>) {
  _stateEvents = [{ id: _stateNextId++, ts: Date.now(), label, data }, ..._stateEvents].slice(0, 100);
  notifyState();
}

export function clearAppState() {
  _stateEvents = [];
  _stateNextId = 1;
  notifyState();
}

function useAppStateEvents() {
  const [, setTick] = useState(0);
  useEffect(() => {
    const cb = () => setTick((t) => t + 1);
    _stateListeners.push(cb);
    return () => {
      _stateListeners = _stateListeners.filter((fn) => fn !== cb);
    };
  }, []);
  return _stateEvents;
}

/* ------------------------------------------------------------------ */
/*  JSON viewer (collapsible)                                         */
/* ------------------------------------------------------------------ */

function JsonBlock({ label, data }: { label: string; data: unknown }) {
  const [open, setOpen] = useState(false);
  if (data === undefined || data === null) return null;
  const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
  const preview = text.length > 120 ? text.slice(0, 120) + '…' : text;

  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-[10px] font-semibold text-slate-500 hover:text-slate-800"
      >
        <span className={cn('transition-transform', open && 'rotate-90')}>▸</span>
        {label}
      </button>
      {open ? (
        <pre className="mt-0.5 max-h-[300px] overflow-auto rounded bg-slate-800 p-2 text-[10px] leading-relaxed text-green-300 select-text">
          {text}
        </pre>
      ) : (
        <pre className="mt-0.5 truncate text-[10px] text-slate-400 select-text">{preview}</pre>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Floating debug panel                                              */
/* ------------------------------------------------------------------ */

const STATUS_COLOR: Record<string, string> = {
  '2': 'text-green-600',
  '4': 'text-amber-600',
  '5': 'text-red-600',
};

function statusColor(status?: number) {
  if (!status) return 'text-slate-400';
  return STATUS_COLOR[String(status)[0]] ?? 'text-slate-600';
}

type DebugTab = 'api' | 'state';

function LocalStorageSnapshot() {
  const [snapshot, setSnapshot] = useState<Record<string, string>>({});
  useEffect(() => {
    const keys = ['ami_learning_style_preference', 'auth_token', 'ami_member_since'];
    const snap: Record<string, string> = {};
    for (const k of keys) {
      try {
        const v = localStorage.getItem(k);
        if (v != null) snap[k] = v;
      } catch { /* ignore */ }
    }
    setSnapshot(snap);
  }, []);

  if (Object.keys(snapshot).length === 0) return null;
  return (
    <div className="border-b border-slate-100 px-4 py-2">
      <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide mb-1">localStorage</p>
      {Object.entries(snapshot).map(([k, v]) => (
        <div key={k} className="flex gap-2 text-[10px] leading-relaxed">
          <span className="shrink-0 font-mono text-slate-500">{k}:</span>
          <span className="text-slate-800 break-all">{v.length > 80 ? v.slice(0, 80) + '…' : v}</span>
        </div>
      ))}
    </div>
  );
}

export function DebugPanel() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<DebugTab>('api');
  const [filter, setFilter] = useState('');
  const logs = useApiLogs();
  const stateEvents = useAppStateEvents();
  const panelRef = useRef<HTMLDivElement>(null);

  const toggle = useCallback(() => setOpen((o) => !o), []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'D') {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [toggle]);

  const filtered = filter
    ? logs.filter(
        (l) =>
          l.url.toLowerCase().includes(filter.toLowerCase()) ||
          l.method.toLowerCase().includes(filter.toLowerCase()),
      )
    : logs;

  const filteredState = filter
    ? stateEvents.filter((e) => e.label.toLowerCase().includes(filter.toLowerCase()))
    : stateEvents;

  return (
    <>
      {/* Floating toggle button — bottom-left so it doesn't overlap main content */}
      <button
        type="button"
        onClick={toggle}
        className={cn(
          'fixed bottom-4 left-4 z-[9999] mb-[55px] flex h-10 w-10 items-center justify-center rounded-full shadow-lg transition-colors',
          'bg-slate-800 text-white hover:bg-slate-700 active:bg-slate-900',
          'ring-2 ring-white/20',
        )}
        title="Toggle debug panel (Ctrl+Shift+D)"
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
        </svg>
      </button>

      {/* Panel */}
      {open && (
        <div
          ref={panelRef}
          className="fixed bottom-16 left-4 z-[9999] flex max-h-[70vh] w-[480px] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2">
            <span className="text-xs font-bold text-slate-700">Debug Panel</span>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-slate-400">
                {tab === 'api' ? `${logs.length} calls` : `${stateEvents.length} events`}
              </span>
              <button
                type="button"
                onClick={tab === 'api' ? clearApiLogs : clearAppState}
                className="rounded px-1.5 py-0.5 text-[10px] font-medium text-red-600 hover:bg-red-50"
              >
                Clear
              </button>
              <button
                type="button"
                onClick={toggle}
                className="rounded px-1.5 py-0.5 text-[10px] font-medium text-slate-500 hover:bg-slate-100"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-slate-200 bg-slate-50/60">
            {(['api', 'state'] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={cn(
                  'flex-1 py-1.5 text-[10px] font-semibold uppercase tracking-wider transition-colors',
                  tab === t
                    ? 'text-slate-800 border-b-2 border-slate-700'
                    : 'text-slate-400 hover:text-slate-600',
                )}
              >
                {t === 'api' ? 'API Logs' : 'App State'}
              </button>
            ))}
          </div>

          {/* Filter */}
          <div className="border-b border-slate-100 px-4 py-1.5">
            <input
              type="text"
              placeholder={tab === 'api' ? 'Filter by URL or method…' : 'Filter by event label…'}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-full rounded bg-slate-50 px-2 py-1 text-xs text-slate-700 placeholder:text-slate-400 outline-none ring-1 ring-slate-200 focus:ring-slate-400"
            />
          </div>

          {/* API Logs tab */}
          {tab === 'api' && (
            <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
              {filtered.length === 0 && (
                <p className="px-4 py-8 text-center text-xs text-slate-400">
                  No API calls yet. Interact with the app to see requests here.
                </p>
              )}
              {filtered.map((log) => (
                <div key={log.id} className="px-4 py-2.5 hover:bg-slate-50/80">
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 font-mono font-bold text-slate-600">
                      {log.method}
                    </span>
                    <span className="min-w-0 flex-1 truncate font-mono text-slate-700" title={log.url}>
                      {log.url}
                    </span>
                    <span className={cn('shrink-0 font-bold tabular-nums', statusColor(log.status))}>
                      {log.status ?? '…'}
                    </span>
                    {log.durationMs != null && (
                      <span className="shrink-0 text-[10px] tabular-nums text-slate-400">
                        {log.durationMs}ms
                      </span>
                    )}
                  </div>
                  {log.error && (
                    <p className="mt-1 text-[10px] text-red-600">{log.error}</p>
                  )}
                  <JsonBlock label="Request body" data={log.requestBody} />
                  <JsonBlock label="Response body" data={log.responseBody} />
                </div>
              ))}
            </div>
          )}

          {/* App State tab */}
          {tab === 'state' && (
            <div className="flex-1 overflow-y-auto">
              <LocalStorageSnapshot />
              <div className="divide-y divide-slate-100">
                {filteredState.length === 0 && (
                  <p className="px-4 py-8 text-center text-xs text-slate-400">
                    No state events yet. Navigate through the app to see data snapshots.
                  </p>
                )}
                {filteredState.map((evt) => (
                  <div key={evt.id} className="px-4 py-2.5 hover:bg-slate-50/80">
                    <div className="flex items-center gap-2 text-[11px]">
                      <span className="shrink-0 rounded bg-indigo-100 px-1.5 py-0.5 font-semibold text-indigo-700">
                        {evt.label}
                      </span>
                      <span className="shrink-0 text-[10px] tabular-nums text-slate-400">
                        {new Date(evt.ts).toLocaleTimeString()}
                      </span>
                    </div>
                    {Object.entries(evt.data).map(([key, value]) => (
                      <JsonBlock key={key} label={key} data={value} />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
