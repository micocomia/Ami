import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/cn';
import LogoBlack from '@/assets/Logo_black.png';
import AvatarImg from '@/assets/avatar.png';
import { useHasEnteredGoal } from '@/context/HasEnteredGoalContext';
import { useAuthContext } from '@/context/AuthContext';
import { useSidebarCollapse } from '@/context/SidebarCollapseContext';

interface NavSubItem {
  to: string;
  label: string;
}

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
  /** Only show when user has entered a goal */
  showWhenHasGoal?: boolean;
  /** Sub-navigation (e.g. Analytics → Overview, Active Goal) */
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
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 6.75V15m6-6v8.25m.503 3.498l4.875-2.437c.381-.19.622-.58.622-1.006V4.82c0-.836-.88-1.38-1.628-1.006l-3.869 1.934c-.317.159-.69.159-1.006 0L9.503 3.252a1.125 1.125 0 00-1.006 0L3.622 5.689C3.24 5.88 3 6.27 3 6.695V19.18c0 .836.88 1.38 1.628 1.006l3.869-1.934c.317-.159.69-.159 1.006 0l4.994 2.497c.317.158.69.158 1.006 0z" />
      </svg>
    ),
  },
  {
    to: '/learning-session',
    label: 'Sessions',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 010 1.972l-11.54 6.347a1.125 1.125 0 01-1.667-.986V5.653z" />
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
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
      </svg>
    ),
  },
];

interface SideNavProps {
  /** @deprecated Use SidebarCollapseContext instead */
  collapsed?: boolean;
}

export function SideNav({ collapsed: collapsedProp }: SideNavProps) {
  const { collapsed: collapsedCtx, toggleCollapsed, setCollapsed } = useSidebarCollapse();
  const collapsed = collapsedProp ?? collapsedCtx;
  const { hasEnteredGoal } = useHasEnteredGoal();
  const { userId } = useAuthContext();
  const navItems = NAV_ITEMS.filter((item) => !item.showWhenHasGoal || hasEnteredGoal);

  return (
    <aside
      className={cn(
        'fixed top-0 left-0 h-screen bg-sidebar flex flex-col z-30 transition-all duration-200 text-slate-800',
        collapsed ? 'w-16' : 'w-sidebar',
      )}
    >
      {/* Brand: expanded = logo link + collapse; collapsed = avatar only, click to expand */}
      <div
        className={cn(
          'flex items-center h-topbar shrink-0 border-b border-slate-200',
          collapsed ? 'justify-center px-2' : 'gap-2 px-3',
        )}
      >
        {collapsed ? (
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            className="flex items-center justify-center rounded-lg p-0.5 outline-none focus-visible:ring-2 focus-visible:ring-primary-400 focus-visible:ring-offset-2 hover:bg-sidebar-hover transition-colors"
            title="Expand sidebar"
            aria-label="Expand sidebar"
          >
            <img
              src={AvatarImg}
              alt=""
              className="h-8 w-8 rounded-full object-cover ring-2 ring-slate-100"
            />
          </button>
        ) : (
          <>
            <NavLink
              to="/dashboard"
              className="flex items-center min-w-0 rounded-lg py-1 flex-1 outline-none focus-visible:ring-2 focus-visible:ring-primary-400 focus-visible:ring-offset-2"
              title="Ami"
            >
              <img
                src={LogoBlack}
                alt="Ami"
                className="h-8 w-auto max-h-8 max-w-[120px] object-contain object-left"
              />
            </NavLink>
            <button
              type="button"
              onClick={toggleCollapsed}
              className="rounded-lg p-2 shrink-0 text-slate-500 hover:bg-sidebar-hover hover:text-slate-800 transition-colors"
              title="Collapse sidebar"
              aria-expanded
              aria-label="Collapse sidebar"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
              </svg>
            </button>
          </>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 overflow-y-auto">
        <ul className="flex flex-col gap-0.5 px-2">
          {navItems.map(({ to, label, icon, badge }) => {
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
                  {!collapsed && badge != null && (
                    <span className="ml-auto bg-slate-200 text-slate-700 text-xs font-semibold px-2 py-0.5 rounded-full">
                      {badge}
                    </span>
                  )}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Bottom: User avatar + profile */}
      <div className="px-2 pb-3 mt-auto border-t border-slate-200 pt-3">
        <NavLink
          to="/profile"
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
              isActive
                ? 'bg-sidebar-active text-slate-900'
                : 'text-slate-600 hover:bg-sidebar-hover hover:text-slate-800',
              collapsed && 'justify-center px-0',
            )
          }
          title={collapsed ? (userId ?? 'User') : undefined}
        >
          <div className="w-8 h-8 rounded-full bg-primary-200 text-primary-800 flex items-center justify-center font-semibold text-xs shrink-0">
            {userId ? userId.charAt(0).toUpperCase() : 'U'}
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-800 truncate">{userId ?? 'User'}</p>
              <p className="text-[11px] text-slate-400 truncate">View profile</p>
            </div>
          )}
        </NavLink>
      </div>
    </aside>
  );
}
