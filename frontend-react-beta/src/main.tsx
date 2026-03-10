import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { router } from './router';
import { ToastProvider } from '@/components/ui/Toast';
import { ApiToastBridge } from '@/components/ApiToastBridge';
import { AuthProvider } from '@/context/AuthContext';
import { HasEnteredGoalProvider } from '@/context/HasEnteredGoalContext';
import { GoalsProvider } from '@/context/GoalsContext';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000,
      retry: 1,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <GoalsProvider>
          <HasEnteredGoalProvider>
            <ToastProvider>
              <ApiToastBridge />
              <RouterProvider router={router} />
            </ToastProvider>
          </HasEnteredGoalProvider>
        </GoalsProvider>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
