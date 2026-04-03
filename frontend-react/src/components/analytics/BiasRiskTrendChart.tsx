import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface AuditEntry {
  timestamp: string;
  overall_risk: 'low' | 'medium' | 'high';
}

interface BiasRiskTrendChartProps {
  entries: AuditEntry[];
}

const RISK_VALUE: Record<string, number> = { low: 1, medium: 2, high: 3 };
const RISK_COLOR: Record<number, string> = { 1: '#10b981', 2: '#f59e0b', 3: '#ef4444' };

function riskLabel(value: number) {
  if (value === 1) return 'Low';
  if (value === 2) return 'Medium';
  if (value === 3) return 'High';
  return '';
}

export function BiasRiskTrendChart({ entries }: BiasRiskTrendChartProps) {
  const sorted = [...entries].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );

  const chartData = sorted.map((e) => ({
    date: new Date(e.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    risk: RISK_VALUE[e.overall_risk] ?? 1,
  }));

  return (
    <div style={{ height: 240 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 4, right: 8, left: -16, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis
            tick={{ fontSize: 11 }}
            domain={[0.5, 3.5]}
            ticks={[1, 2, 3]}
            tickFormatter={riskLabel}
          />
          <Tooltip
            formatter={(v) => [riskLabel(Number(v)), 'Risk Level']}
            labelFormatter={(label) => `Date: ${label}`}
          />
          <Line
            type="monotone"
            dataKey="risk"
            stroke="#6366f1"
            strokeWidth={2}
            dot={({ cx, cy, payload }) => (
              <circle
                key={`${cx}-${cy}`}
                cx={cx}
                cy={cy}
                r={4}
                fill={RISK_COLOR[payload.risk] ?? '#6366f1'}
                stroke="white"
                strokeWidth={1.5}
              />
            )}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
