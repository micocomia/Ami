import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface MasteryChartProps {
  data: Array<{ session_index: number; mastery_pct: number }>;
}

export function MasteryChart({ data }: MasteryChartProps) {
  const chartData = data.map((d) => ({
    session: `S${d.session_index + 1}`,
    mastery: Math.round(d.mastery_pct),
  }));

  return (
    <div style={{ height: 240 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 4, right: 8, left: -16, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="session" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} unit="%" domain={[0, 100]} />
          <Tooltip formatter={(v) => [`${v}%`, 'Mastery']} />
          <Line type="monotone" dataKey="mastery" stroke="#10b981" strokeWidth={2} dot={{ r: 3, fill: '#10b981' }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
