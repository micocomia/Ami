import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom';
import { AppShell, AuthLayout, LearningSessionLayout, OnboardingLayout } from '@/components/shell';
import { HomePage } from '@/pages/HomePage';
import { LoginPage } from '@/pages/LoginPage';
import { RegisterPage } from '@/pages/RegisterPage';
import { OnboardingPage } from '@/pages/OnboardingPage';
import { GoalsPage } from '@/pages/GoalsPage';
import { ProfilePage } from '@/pages/ProfilePage';
import { LearningPathPage } from '@/pages/LearningPathPage';
import { LearningSessionPage } from '@/pages/LearningSessionPage';
import { SkillGapPage } from '@/pages/SkillGapPage';
import { RefineGoalExamplePage } from '@/pages/RefineGoalExamplePage';
import { AnalyticsPage } from '@/pages/AnalyticsPage';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';
import { SidebarCollapseProvider } from '@/context/SidebarCollapseContext';

// Vite 的 base（如 /Ami-React/）去掉末尾斜杠作为 React Router basename，适配 GitHub Pages
const basename = import.meta.env.BASE_URL.replace(/\/$/, '') || '/';

/** Redirects unauthenticated users to /login */
function AuthGuard() {
  const { isAuthenticated } = useAuthContext();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return (
    <SidebarCollapseProvider>
      <Outlet />
    </SidebarCollapseProvider>
  );
}

/**
 * Root redirect: after login, same rule as postAuthRedirect —
 * goals exist → /goals (goal management), empty → /onboarding.
 */
function RootRedirect() {
  const { isAuthenticated } = useAuthContext();
  const { goals, isLoading } = useGoalsContext();

  if (!isAuthenticated) return <Navigate to="/login" replace />;

  // GoalsProvider fetches GET /v1/goals/{user_id} on auth; wait to avoid flashing onboarding
  if (isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-sm font-medium text-slate-600">
        Loading your workspace…
      </div>
    );
  }

  // Route by goal existence only:
  // - has goal -> dashboard
  // - no goal -> onboarding
  if (goals.length > 0) return <Navigate to="/dashboard" replace />;
  return <Navigate to="/onboarding" replace />;
}

export const router = createBrowserRouter(
  [
    /* Root redirect */
    { path: '/', element: <RootRedirect /> },

    /* Auth — centered card layout */
    {
      element: <AuthLayout />,
      children: [
        { path: '/login', element: <LoginPage /> },
        { path: '/register', element: <RegisterPage /> },
      ],
    },

    /* Protected routes */
    {
      element: <AuthGuard />,
      children: [
        /* Landing / Onboarding — full-page, no sidebar */
        {
          element: <OnboardingLayout />,
          children: [
            { path: '/onboarding', element: <OnboardingPage /> },
          ],
        },
        /* Learning Session — sidebar only, no TopBar, center + right panel */
        {
          element: <LearningSessionLayout />,
          children: [
            { path: '/learning-session', element: <LearningSessionPage /> },
          ],
        },
        /* Main app — sidebar + top bar */
        {
          element: <AppShell />,
          children: [
            { path: '/dashboard', element: <HomePage /> },
            { path: '/goals', element: <GoalsPage /> },
            { path: '/profile', element: <ProfilePage /> },
            { path: '/learning-path', element: <LearningPathPage /> },
            { path: '/skill-gap', element: <SkillGapPage /> },
            { path: '/analytics', element: <AnalyticsPage /> },
            { path: '/example/refine-goal', element: <RefineGoalExamplePage /> },
          ],
        },
      ],
    },

    { path: '*', element: <Navigate to="/" replace /> },
  ],
  { basename }
);
