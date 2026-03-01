import { Outlet, Link } from 'react-router-dom';
import { Button } from '@/components/ui';

export function OnboardingLayout() {
  return (
    <div className="min-h-screen flex flex-col bg-white">
      {/* Minimal top bar — matches Figma: LOGO left, Sign in / Register right */}
      <header className="flex items-center justify-between px-8 py-4 shrink-0">
        <Link to="/" className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-primary-600 text-white flex items-center justify-center font-bold text-sm">
            A
          </div>
          <span className="text-xl font-bold text-slate-900 tracking-tight">Ami</span>
        </Link>

        <div className="flex items-center gap-2">
          <Link to="/login">
            <Button variant="secondary" size="sm">Sign in</Button>
          </Link>
          <Link to="/register">
            <Button variant="primary" size="sm">Register</Button>
          </Link>
        </div>
      </header>

      {/* Page content — full width, no sidebar offset */}
      <main className="flex-1 min-h-0 flex flex-col">
        <Outlet />
      </main>
    </div>
  );
}
