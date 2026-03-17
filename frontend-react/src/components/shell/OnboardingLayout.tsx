import { Outlet, Link } from 'react-router-dom';
import { Button } from '@/components/ui';
import { useAuthContext } from '@/context/AuthContext';
import Logo from '@/assets/Logo_black.png';

export function OnboardingLayout() {
  const { isAuthenticated } = useAuthContext();

  return (
    <div className="min-h-screen flex flex-col bg-white">
      {/* Minimal top bar — matches Figma: LOGO left, Sign in / Register right */}
      <header className="flex items-center justify-between px-8 py-4 shrink-0">
        <Link to="/" className="flex items-center gap-2">
          <img src={Logo} alt="Ami logo" className="h-9 w-auto" />
        </Link>

        <div className="flex items-center gap-2">
          {isAuthenticated ? (
            <Link to="/dashboard">
              <Button variant="secondary" size="sm">
                My Learning
              </Button>
            </Link>
          ) : (
            <>
              <Link to="/login">
                <Button variant="secondary" size="sm">Sign in</Button>
              </Link>
              <Link to="/register">
                <Button variant="primary" size="sm">Register</Button>
              </Link>
            </>
          )}
        </div>
      </header>

      {/* Page content — full width, no sidebar offset */}
      <main className="flex-1 min-h-0 flex flex-col">
        <Outlet />
      </main>
    </div>
  );
}
