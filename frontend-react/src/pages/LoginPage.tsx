import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, InputField } from '@/components/ui';

const DEMO_EMAIL = 'demo@genmentor.ai';
const DEMO_PASSWORD = 'demo';

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const loginWithDemo = () => {
    setEmail(DEMO_EMAIL);
    setPassword(DEMO_PASSWORD);
    navigate('/dashboard');
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Sign in</h2>
        <p className="mt-1 text-sm text-slate-500">
          Welcome back — enter your credentials to continue.
        </p>
      </div>

      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          // TODO: wire up useLogin
        }}
      >
        <InputField
          label="Email"
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <InputField
          label="Password"
          type="password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Button type="submit" className="w-full">
          Sign in
        </Button>
        <Button
          type="button"
          variant="secondary"
          className="w-full"
          onClick={loginWithDemo}
        >
          Use demo account
        </Button>
      </form>

      <p className="text-center text-sm text-slate-500">
        Don&apos;t have an account?{' '}
        <Link to="/register" className="font-medium text-primary-600 hover:text-primary-700">
          Register
        </Link>
      </p>
    </div>
  );
}
