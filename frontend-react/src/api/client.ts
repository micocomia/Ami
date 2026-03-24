import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';
import { setupResponseErrorHandling } from './errors';
import { pushApiLog } from '@/components/DebugPanel';

const rawBase =
  typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL != null
    ? (import.meta.env.VITE_API_BASE_URL as string)
    : 'http://localhost:8001/';

const normalized = rawBase.replace(/\s+/g, '').replace(/\/+$/, '');

// VITE_API_BASE_URL = 后端 origin，勿带 /v1；axios baseURL = origin + '/v1/'
// 未设置时 fallback localhost:8001 — 线上构建务必注入，否则 Pages 会请求用户本机
export const apiOrigin = normalized.replace(/\/v1$/, '');
export const baseURL = (normalized.endsWith('/v1') ? normalized : `${normalized}/v1`) + '/';

export const apiClient: AxiosInstance = axios.create({
  baseURL,
  timeout: 60_000,
  headers: { 'Content-Type': 'application/json' },
});

/** Request interceptor: attach JWT */
apiClient.interceptors.request.use((config) => {
  try {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  } catch {
    // ignore
  }
  return config;
});

setupResponseErrorHandling(apiClient);

/* ── Debug interceptor: log every request/response for the debug panel ── */
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  (config as any).__debugStartMs = Date.now();
  return config;
});

apiClient.interceptors.response.use(
  (response) => {
    const start = (response.config as any).__debugStartMs as number | undefined;
    pushApiLog({
      ts: Date.now(),
      method: (response.config.method ?? 'GET').toUpperCase(),
      url: response.config.url ?? '',
      status: response.status,
      requestBody: response.config.data ? safeJsonParse(response.config.data) : undefined,
      responseBody: response.data,
      durationMs: start ? Date.now() - start : undefined,
    });
    return response;
  },
  (error) => {
    const config = error?.config;
    const start = config?.__debugStartMs as number | undefined;
    pushApiLog({
      ts: Date.now(),
      method: (config?.method ?? 'GET').toUpperCase(),
      url: config?.url ?? '',
      status: error?.response?.status,
      requestBody: config?.data ? safeJsonParse(config.data) : undefined,
      responseBody: error?.response?.data,
      error: error?.message,
      durationMs: start ? Date.now() - start : undefined,
    });
    return Promise.reject(error);
  },
);

function safeJsonParse(data: unknown): unknown {
  if (typeof data === 'string') {
    try { return JSON.parse(data); } catch { return data; }
  }
  return data;
}
