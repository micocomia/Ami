import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, InputField } from '@/components/ui';
import { useLogin } from '@/api/endpoints/auth';
import { useAuthContext } from '@/context/AuthContext';

export function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const { login } = useAuthContext();
  const navigate = useNavigate();
  const loginMutation = useLogin();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!username.trim() || !password) return;
    try {
      const data = await loginMutation.mutateAsync({ username: username.trim(), password });
      login(data);
      navigate('/', { replace: true }); // RootRedirect at '/' routes to onboarding or learning-path
    } catch {
      setError('Invalid username or password. Please try again.');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Sign in</h2>
        <p className="mt-1 text-sm text-slate-500">
          Welcome back — enter your credentials to continue.
        </p>
      </div>

      <form className="space-y-4" onSubmit={handleSubmit}>
        <InputField
          label="Username"
          type="text"
          placeholder="your_username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
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
        {error && <p className="text-sm text-red-600">{error}</p>}
        <Button type="submit" className="w-full" disabled={loginMutation.isPending}>
          {loginMutation.isPending ? 'Signing in…' : 'Sign in'}
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
