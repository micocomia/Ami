import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  ResponsiveContainer,
  Legend,
} from 'recharts';

interface SkillRadarChartProps {
  labels: string[];
  currentLevels: number[];
  requiredLevels: number[];
}

export function SkillRadarChart({ labels, currentLevels, requiredLevels }: SkillRadarChartProps) {
  const data = labels.map((label, i) => ({
    skill: label.length > 12 ? label.slice(0, 12) + '…' : label,
    current: currentLevels[i] ?? 0,
    required: requiredLevels[i] ?? 0,
  }));

  return (
    <div style={{ height: 300 }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data}>
          <PolarGrid />
          <PolarAngleAxis dataKey="skill" tick={{ fontSize: 11 }} />
          <Radar name="Required" dataKey="required" stroke="#6366f1" fill="#6366f1" fillOpacity={0.15} />
          <Radar name="Current" dataKey="current" stroke="#10b981" fill="#10b981" fillOpacity={0.25} />
          <Legend />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
