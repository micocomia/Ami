import { useLocation, Link } from 'react-router-dom';

const pageTitles: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/goals': 'Goals',
  '/learning-path': 'Learning Path',
  '/skill-gap': 'Skill Gap',
  '/profile': 'Profile',
  '/analytics': 'Analytics',
  '/analytics/active-goal': 'Analytics',
  '/example/refine-goal': 'API Example',
};

export function TopBar() {
  const { pathname } = useLocation();
  const title = pageTitles[pathname] ?? 'Page';

  return (
    <header className="h-topbar bg-white border-b border-slate-200 flex items-center justify-between px-6 shrink-0">
      <h1 className="text-lg font-semibold text-slate-800">{title}</h1>

      <div className="flex items-center gap-4">
        {/* Placeholder user menu */}
        <Link
          to="/profile"
          className="flex items-center gap-2 text-sm text-slate-600 hover:text-slate-900 transition-colors"
        >
          <div className="w-8 h-8 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center font-semibold text-xs">
            U
          </div>
          <span className="hidden sm:inline">User</span>
        </Link>
      </div>
    </header>
  );
}
