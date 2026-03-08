import { useLocation, Link } from 'react-router-dom';
import { useAuthContext } from '@/context/AuthContext';
import { useNavigate } from 'react-router-dom';

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
  const { userId, logout } = useAuthContext();
  const navigate = useNavigate();
  const title = pageTitles[pathname] ?? 'Page';
  const initials = userId ? userId.slice(0, 2).toUpperCase() : 'U';

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="h-topbar bg-white border-b border-slate-200 flex items-center justify-between px-6 shrink-0">
      <h1 className="text-lg font-semibold text-slate-800">{title}</h1>

      <div className="flex items-center gap-4">
        <Link
          to="/profile"
          className="flex items-center gap-2 text-sm text-slate-600 hover:text-slate-900 transition-colors"
        >
          <div className="w-8 h-8 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center font-semibold text-xs">
            {initials}
          </div>
          <span className="hidden sm:inline">{userId ?? 'User'}</span>
        </Link>
        <button
          onClick={handleLogout}
          className="text-sm text-slate-500 hover:text-slate-800 transition-colors"
          title="Sign out"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
          </svg>
        </button>
      </div>
    </header>
  );
}
