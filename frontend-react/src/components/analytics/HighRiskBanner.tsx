import { useState } from 'react';
import { Link } from 'react-router-dom';

interface AuditEntry {
  overall_risk: 'low' | 'medium' | 'high';
  timestamp: string;
}

interface HighRiskBannerProps {
  entries: AuditEntry[];
}

const RECENT_WINDOW = 5;
const HIGH_RISK_THRESHOLD = 3;

function hasRepeatedHighRisk(entries: AuditEntry[]): boolean {
  const recent = [...entries]
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    .slice(0, RECENT_WINDOW);
  return recent.filter((e) => e.overall_risk === 'high').length >= HIGH_RISK_THRESHOLD;
}

export function HighRiskBanner({ entries }: HighRiskBannerProps) {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed || entries.length === 0 || !hasRepeatedHighRisk(entries)) return null;

  return (
    <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4 flex items-start gap-3">
      {/* Warning icon */}
      <svg
        className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500"
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z"
          clipRule="evenodd"
        />
      </svg>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-red-800">Repeated High-Risk Bias Audits</p>
        <p className="mt-1 text-sm text-red-700">
          Multiple recent bias audits flagged high risk. Review your Bias &amp; Ethics analytics for details.
        </p>
        <Link
          to="/analytics"
          className="mt-2 inline-block text-sm font-medium text-red-700 underline hover:text-red-900"
        >
          View Details
        </Link>
      </div>

      <button
        type="button"
        onClick={() => setDismissed(true)}
        className="flex-shrink-0 rounded p-1 text-red-400 hover:text-red-600 hover:bg-red-100 transition-colors"
        aria-label="Dismiss warning"
      >
        <svg className="h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
          <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
        </svg>
      </button>
    </div>
  );
}
