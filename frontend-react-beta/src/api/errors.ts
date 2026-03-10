import type { AxiosInstance, AxiosError } from 'axios';
import { showError } from './toast';

const AUTH_TOKEN_KEY = 'auth_token';
const LOGIN_PATH = '/login';

function clearTokenAndRedirectToLogin(): void {
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  } catch {
    // ignore
  }
  const base = typeof window !== 'undefined' ? window.location.origin : '';
  const path = base + LOGIN_PATH;
  if (typeof window !== 'undefined' && window.location.pathname !== LOGIN_PATH) {
    window.location.href = path;
  }
}

function getDetailFromError(
  err: AxiosError<{ detail?: string | Array<{ msg?: string }> }>
): string {
  const d = err.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg ?? '').join('; ');
  return err.message || 'Request failed';
}

export function setupResponseErrorHandling(client: AxiosInstance): void {
  client.interceptors.response.use(
    (res) => res,
    (err: AxiosError<{ detail?: string | Array<{ msg?: string }> }>) => {
      const status = err.response?.status;
      const detail = getDetailFromError(err);

      if (status === 401) {
        clearTokenAndRedirectToLogin();
        showError('Session expired. Please log in again.');
        return Promise.reject(err);
      }

      showError(detail || 'Network error. Please try again later.');
      return Promise.reject(err);
    }
  );
}
