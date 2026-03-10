import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, InputField } from '@/components/ui';
import { useRegister } from '@/api/endpoints/auth';
import { useAuthContext } from '@/context/AuthContext';

export function RegisterPage() {
  const navigate = useNavigate();
  const { login } = useAuthContext();
  const registerMutation = useRegister();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!username.trim() || !password) return;
    if (confirm !== password) return;
    try {
      const data = await registerMutation.mutateAsync({ username: username.trim(), password });
      login(data);
      navigate('/', { replace: true });
    } catch {
      setError('Failed to create account. Please try again.');
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Create an account</h2>
        <p className="mt-1 text-sm text-slate-500">
          Start your adaptive learning journey with Ami.
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
          placeholder="At least 8 characters"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <InputField
          label="Confirm password"
          type="password"
          placeholder="Repeat your password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={confirm && confirm !== password ? 'Passwords do not match' : undefined}
          required
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <Button type="submit" className="w-full" disabled={registerMutation.isPending || confirm !== password}>
          {registerMutation.isPending ? 'Creating account…' : 'Create account'}
        </Button>
      </form>

      <p className="text-center text-sm text-slate-500">
        Already have an account?{' '}
        <Link to="/login" className="font-medium text-primary-600 hover:text-primary-700">
          Sign in
        </Link>
      </p>
    </div>
  );
}
