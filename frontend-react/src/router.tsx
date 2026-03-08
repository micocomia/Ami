import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom';
import { AppShell, AuthLayout, LearningSessionLayout, OnboardingLayout } from '@/components/shell';
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
import { HomePage } from '@/pages/HomePage';
import { useAuthContext } from '@/context/AuthContext';
import { useGoalsContext } from '@/context/GoalsContext';

// Vite base path (handles GitHub Pages deployment)
const basename = import.meta.env.BASE_URL.replace(/\/$/, '') || '/';

/** Redirects unauthenticated users to /login */
function AuthGuard() {
  const { isAuthenticated } = useAuthContext();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Outlet />;
}

/** Root redirect: routes users to the right starting page */
function RootRedirect() {
  const { isAuthenticated } = useAuthContext();
  const { goals, isLoading } = useGoalsContext();

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (isLoading) return null; // brief wait while goals load
  if (goals.length > 0) return <Navigate to="/learning-path" replace />;
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

    /* Onboarding — full-page, no sidebar (auth-gated) */
    {
      element: <AuthGuard />,
      children: [
        {
          element: <OnboardingLayout />,
          children: [
            { path: '/onboarding', element: <OnboardingPage /> },
            { path: '/skill-gap', element: <SkillGapPage /> },
          ],
        },
      ],
    },

    /* Learning Session — sidebar only, no TopBar (auth-gated) */
    {
      element: <AuthGuard />,
      children: [
        {
          element: <LearningSessionLayout />,
          children: [
            { path: '/learning-session', element: <LearningSessionPage /> },
          ],
        },
      ],
    },

    /* Main app — sidebar + top bar (auth-gated) */
    {
      element: <AuthGuard />,
      children: [
        {
          element: <AppShell />,
          children: [
            { path: '/dashboard', element: <HomePage /> },
            { path: '/goals', element: <GoalsPage /> },
            { path: '/profile', element: <ProfilePage /> },
            { path: '/learning-path', element: <LearningPathPage /> },
            { path: '/analytics', element: <AnalyticsPage /> },
            { path: '/analytics/active-goal', element: <AnalyticsPage /> },
            { path: '/example/refine-goal', element: <RefineGoalExamplePage /> },
          ],
        },
      ],
    },

    /* Catch-all */
    { path: '*', element: <Navigate to="/" replace /> },
  ],
  { basename }
);
