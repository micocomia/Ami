import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { router } from './router';
import { ToastProvider } from '@/components/ui/Toast';
import { ApiToastBridge } from '@/components/ApiToastBridge';
import { HasEnteredGoalProvider } from '@/context/HasEnteredGoalContext';
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
      <HasEnteredGoalProvider>
        <ToastProvider>
          <ApiToastBridge />
          <RouterProvider router={router} />
        </ToastProvider>
      </HasEnteredGoalProvider>
    </QueryClientProvider>
  </StrictMode>,
);
