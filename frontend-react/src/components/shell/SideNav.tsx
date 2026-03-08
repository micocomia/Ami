import { NavLink, useLocation } from 'react-router-dom';
import { cn } from '@/lib/cn';
import { useGoalsContext } from '@/context/GoalsContext';

interface NavSubItem {
  to: string;
  label: string;
}

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
  showWhenHasGoal?: boolean;
  children?: NavSubItem[];
}

const NAV_ITEMS: NavItem[] = [
  {
    to: '/dashboard',
    label: 'Dashboard',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
      </svg>
    ),
  },
  {
    to: '/goals',
    label: 'Goals',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v1.5M3 21v-6m0 0l2.77-.693a9 9 0 016.208.682l.108.054a9 9 0 006.086.71l3.114-.732a48.524 48.524 0 01-.005-10.499l-3.11.732a9 9 0 01-6.085-.711l-.108-.054a9 9 0 00-6.208-.682L3 4.5M3 15V4.5" />
      </svg>
    ),
  },
  {
    to: '/learning-path',
    label: 'Learning Path',
    showWhenHasGoal: true,
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 6.75V15m6-6v8.25m.503 3.498l4.875-2.437c.381-.19.622-.58.622-1.006V4.82c0-.836-.88-1.38-1.628-1.006l-3.869 1.934c-.317.159-.69.159-1.006 0L9.503 3.252a1.125 1.125 0 00-1.006 0L3.622 5.689C3.24 5.88 3 6.27 3 6.695V19.18c0 .836.88 1.38 1.628 1.006l3.869-1.934c.317-.159.69-.159 1.006 0l4.994 2.497c.317.158.69.158 1.006 0z" />
      </svg>
    ),
  },
  {
    to: '/profile',
    label: 'Profile',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
      </svg>
    ),
  },
  {
    to: '/analytics',
    label: 'Analytics',
    showWhenHasGoal: true,
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
      </svg>
    ),
    children: [
      { to: '/analytics', label: 'Overview' },
      { to: '/analytics/active-goal', label: 'Active Goal' },
    ],
  },
];

interface SideNavProps {
  collapsed?: boolean;
}

export function SideNav({ collapsed = false }: SideNavProps) {
  const { goals } = useGoalsContext();
  const hasGoal = goals.length > 0;
  const location = useLocation();
  const pathname = location.pathname;
  const navItems = NAV_ITEMS.filter((item) => !item.showWhenHasGoal || hasGoal);

  return (
    <aside
      className={cn(
        'fixed top-0 left-0 h-screen bg-sidebar flex flex-col z-30 transition-all duration-200 text-slate-800',
        collapsed ? 'w-16' : 'w-sidebar',
      )}
    >
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-4 h-topbar shrink-0 border-b border-slate-200">
        <div className="w-8 h-8 rounded-lg bg-primary-500 text-white flex items-center justify-center font-bold text-sm">
          A
        </div>
        {!collapsed && <span className="text-lg font-semibold tracking-tight text-slate-900">Ami</span>}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 overflow-y-auto">
        <ul className="flex flex-col gap-0.5 px-2">
          {navItems.map(({ to, label, icon, children }) => {
            const isAnalyticsGroup = label === 'Analytics' && children?.length;
            const isAnalyticsActive = pathname === '/analytics' || pathname === '/analytics/active-goal';

            if (isAnalyticsGroup && children) {
              return (
                <li key={to}>
                  <div
                    className={cn(
                      'flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-t-md',
                      isAnalyticsActive ? 'bg-sidebar-active text-slate-900' : 'text-slate-600',
                      collapsed && 'justify-center px-0',
                    )}
                  >
                    {icon}
                    {!collapsed && (
                      <>
                        <span className="flex-1">{label}</span>
                        <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5" />
                        </svg>
                      </>
                    )}
                  </div>
                  {!collapsed && (
                    <ul className="rounded-b-md overflow-hidden">
                      {children.map((sub) => (
                        <li key={sub.to}>
                          <NavLink
                            to={sub.to}
                            end={sub.to === '/analytics'}
                            className={({ isActive }) =>
                              cn(
                                'flex items-center gap-2 pl-11 pr-3 py-2 text-sm transition-colors block',
                                isActive
                                  ? 'bg-sidebar-active text-slate-900'
                                  : 'text-slate-600 hover:bg-sidebar-hover hover:text-slate-800',
                              )
                            }
                          >
                            {sub.label}
                          </NavLink>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            }

            return (
              <li key={to}>
                <NavLink
                  to={to}
                  end={to === '/dashboard'}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-sidebar-active text-slate-900'
                        : 'text-slate-600 hover:bg-sidebar-hover hover:text-slate-800',
                      collapsed && 'justify-center px-0',
                    )
                  }
                  title={collapsed ? label : undefined}
                >
                  {icon}
                  {!collapsed && label}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
