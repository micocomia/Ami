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

// Vite 的 base（如 /Ami-React/）去掉末尾斜杠作为 React Router basename，适配 GitHub Pages
const basename = import.meta.env.BASE_URL.replace(/\/$/, '') || '/';

/** Redirects unauthenticated users to /login */
function AuthGuard() {
  const { isAuthenticated } = useAuthContext();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Outlet />;
}

/** Root redirect: routes users to onboarding (goals routing comes later) */
function RootRedirect() {
  const { isAuthenticated } = useAuthContext();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
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
