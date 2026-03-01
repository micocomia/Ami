import { createBrowserRouter, Navigate } from 'react-router-dom';
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

// Vite 的 base（如 /Ami-React/）去掉末尾斜杠作为 React Router basename，适配 GitHub Pages
const basename = import.meta.env.BASE_URL.replace(/\/$/, '') || '/';

export const router = createBrowserRouter(
  [
  /* Landing / Onboarding — full-page, no sidebar */
  {
    element: <OnboardingLayout />,
    children: [
      { path: '/', element: <OnboardingPage /> },
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
      { path: '/analytics/active-goal', element: <AnalyticsPage /> },
      { path: '/example/refine-goal', element: <RefineGoalExamplePage /> },
    ],
  },
  /* Auth — centered card layout */
  {
    element: <AuthLayout />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/register', element: <RegisterPage /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
  ],
  { basename }
);
