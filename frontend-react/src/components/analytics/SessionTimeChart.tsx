import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface SessionTimeChartProps {
  data: Array<{ session_index: number; duration_sec: number }>;
}

export function SessionTimeChart({ data }: SessionTimeChartProps) {
  const chartData = data.map((d) => ({
    session: `S${d.session_index + 1}`,
    minutes: Math.round(d.duration_sec / 60),
  }));

  return (
    <div style={{ height: 240 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 4, right: 8, left: -16, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="session" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} unit="m" />
          <Tooltip formatter={(v) => [`${v}m`, 'Duration']} />
          <Bar dataKey="minutes" fill="#6366f1" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
