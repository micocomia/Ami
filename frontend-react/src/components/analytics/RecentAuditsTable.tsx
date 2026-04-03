interface AuditEntry {
  timestamp: string;
  audit_type: string;
  overall_risk: 'low' | 'medium' | 'high';
  flagged_count: number;
  audited_count: number;
}

interface RecentAuditsTableProps {
  entries: AuditEntry[];
}

const RISK_STYLES: Record<string, string> = {
  low: 'bg-green-100 text-green-700',
  medium: 'bg-amber-100 text-amber-700',
  high: 'bg-red-100 text-red-700',
};

const AUDIT_LABELS: Record<string, string> = {
  skill_gap_bias: 'Skill Gap Bias',
  profile_fairness: 'Profile Fairness',
  content_bias: 'Content Bias',
  chatbot_bias: 'Chatbot Bias',
};

export function RecentAuditsTable({ entries }: RecentAuditsTableProps) {
  const sorted = [...entries]
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    .slice(0, 10);

  if (sorted.length === 0) return null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-500">
            <th className="pb-2 pr-4 font-medium">Date</th>
            <th className="pb-2 pr-4 font-medium">Audit Type</th>
            <th className="pb-2 pr-4 font-medium">Risk Level</th>
            <th className="pb-2 font-medium">Flags</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((entry, i) => (
            <tr key={i} className="border-b border-slate-100 last:border-0">
              <td className="py-2 pr-4 text-slate-600">
                {new Date(entry.timestamp).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </td>
              <td className="py-2 pr-4 text-slate-700">
                {AUDIT_LABELS[entry.audit_type] ?? entry.audit_type}
              </td>
              <td className="py-2 pr-4">
                <span
                  className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${RISK_STYLES[entry.overall_risk] ?? ''}`}
                >
                  {entry.overall_risk}
                </span>
              </td>
              <td className="py-2 text-slate-600">
                {entry.flagged_count} / {entry.audited_count}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
