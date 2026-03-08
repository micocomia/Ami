import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        primary: {
          50:  '#f2fafb',
          100: '#e5f5f7',
          200: '#C8E6ED',
          300: '#b0dce4',
          400: '#A6CFD5',
          500: '#8fc4cc',
          600: '#7ab5be',
          700: '#5fa3ad',
          800: '#4a8f98',
          900: '#3d7a82',
        },
        sidebar: {
          DEFAULT: '#ffffff',
          hover:   '#f1f5f9',
          active:  '#C8E6ED',
        },
        surface: {
          DEFAULT: '#f0f9fb',
          alt:     '#e5f5f7',
        },
        success: {
          50:  '#f0fdf4',
          500: '#22c55e',
          700: '#15803d',
        },
        danger: {
          50:  '#fef2f2',
          500: '#ef4444',
          700: '#b91c1c',
        },
        warning: {
          50:  '#fffbeb',
          500: '#f59e0b',
        },
      },
      spacing: {
        page: '1.5rem',
        sidebar: '15rem',
        topbar: '3.5rem',
      },
      width: {
        sidebar: '15rem',
      },
      height: {
        topbar: '3.5rem',
      },
      margin: {
        sidebar: '15rem',
      },
      padding: {
        page: '1.5rem',
      },
      borderRadius: {
        sm: '0.375rem',
        md: '0.5rem',
        lg: '0.75rem',
      },
    },
  },
  plugins: [],
} satisfies Config;
