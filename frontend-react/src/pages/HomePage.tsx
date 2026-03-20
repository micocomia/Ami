import { Link } from 'react-router-dom';
import { Button } from '@/components/ui';
import { useAuthContext } from '@/context/AuthContext';
import { useBiasAuditHistory } from '@/api/endpoints/skillGap';
import { HighRiskBanner } from '@/components/analytics';

const quickLinks = [
  { to: '/goals', label: 'Set Learning Goals', description: 'Define and refine what you want to learn.' },
  { to: '/learning-path', label: 'Learning Path', description: 'View your personalized study schedule.' },
];

export function HomePage() {
  const { userId } = useAuthContext();
  const { data: biasHistory } = useBiasAuditHistory(userId ?? undefined);

  return (
    <div className="space-y-8">
      {/* High-risk bias warning */}
      <HighRiskBanner entries={biasHistory?.entries ?? []} />

      {/* Welcome banner */}
      <div className="bg-gradient-to-br from-primary-400 to-primary-600 rounded-xl p-8 text-white">
        <h2 className="text-2xl font-bold">Welcome back!</h2>
        <p className="mt-2 text-primary-100 max-w-lg">
          Pick up where you left off, or start something new. Ami adapts your learning path based on your progress.
        </p>
        <Link to="/goals">
          <Button variant="secondary" className="mt-5 !text-primary-800 !bg-white/90 hover:!bg-white">
            Continue Learning
          </Button>
        </Link>
      </div>

      {/* Quick-access cards */}
      <div>
        <h3 className="text-lg font-semibold text-slate-800 mb-4">Quick Access</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {quickLinks.map(({ to, label, description }) => (
            <Link
              key={to}
              to={to}
              className="group block bg-white rounded-lg border border-slate-200 p-5 hover:border-primary-300 hover:shadow-md transition-all"
            >
              <h4 className="font-medium text-slate-800 group-hover:text-primary-600 transition-colors">
                {label}
              </h4>
              <p className="mt-1 text-sm text-slate-500 leading-relaxed">{description}</p>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
