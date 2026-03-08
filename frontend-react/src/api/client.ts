import axios, { type AxiosInstance } from 'axios';
import { setupResponseErrorHandling } from './errors';

const baseURL =
  typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL != null
    ? (import.meta.env.VITE_API_BASE_URL as string).replace(/\/?$/, '') + '/'
    : 'http://localhost:8000/';

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

export { baseURL };
