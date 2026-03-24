import type { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { showError } from './toast';

const AUTH_TOKEN_KEY = 'auth_token';

/** Login URL including Vite base (e.g. /Ami-React/login) so GitHub Pages full reload lands in SPA */
function getLoginHref(): string {
  if (typeof window === 'undefined') return '/login';
  const base = import.meta.env.BASE_URL || '/';
  const path = base.endsWith('/') ? `${base}login` : `${base}/login`;
  return `${window.location.origin}${path}`;
}

function isAuthLoginOrRegisterRequest(config?: InternalAxiosRequestConfig): boolean {
  const url = config?.url ?? '';
  // baseURL already has /v1/; url is relative e.g. auth/login
  return /auth\/(login|register)\/?$/i.test(url) || url.includes('auth/login') || url.includes('auth/register');
}

function clearTokenAndRedirectToLogin(): void {
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  } catch {
    // ignore
  }
  if (typeof window === 'undefined') return;
  const loginHref = getLoginHref();
  // Avoid reload loop when already on login page (pathname may include basename, e.g. /Ami-React/login)
  if (window.location.pathname.endsWith('/login')) return;
  window.location.href = loginHref;
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
        // Wrong password on login/register returns 401 too — do not redirect (would hit GitHub 404 without basename)
        if (isAuthLoginOrRegisterRequest(err.config)) {
          return Promise.reject(err);
        }
        clearTokenAndRedirectToLogin();
        showError('Session expired. Please log in again.');
        return Promise.reject(err);
      }

      showError(detail || 'Network error. Please try again later.');
      return Promise.reject(err);
    }
  );
}
