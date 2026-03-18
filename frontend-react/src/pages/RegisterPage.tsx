import { useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, InputField } from '@/components/ui';
import { useRegister } from '@/api/endpoints/auth';
import { useAuthContext } from '@/context/AuthContext';
import { navigateAfterAuth } from '@/lib/postAuthRedirect';

const USERNAME_MIN = 3;
const USERNAME_MAX = 32;
const PASSWORD_MIN = 8;
const PASSWORD_MAX = 128;
/** Letters, digits, underscore only — conventional username */
const USERNAME_PATTERN = /^[a-zA-Z0-9_]+$/;

function EyeIcon({ open }: { open: boolean }) {
  if (open) {
    return (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden>
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    );
  }
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
    </svg>
  );
}

function PasswordToggle({ visible, onToggle, id }: { visible: boolean; onToggle: () => void; id: string }) {
  return (
    <button
      type="button"
      id={id}
      onClick={onToggle}
      className="rounded p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400"
      aria-label={visible ? 'Hide password' : 'Show password'}
      tabIndex={0}
    >
      <EyeIcon open={visible} />
    </button>
  );
}

export function RegisterPage() {
  const navigate = useNavigate();
  const { login } = useAuthContext();
  const registerMutation = useRegister();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [error, setError] = useState('');

  const usernameError = useMemo(() => {
    const u = username.trim();
    if (!u) return undefined;
    if (u.length < USERNAME_MIN) return `At least ${USERNAME_MIN} characters`;
    if (u.length > USERNAME_MAX) return `At most ${USERNAME_MAX} characters`;
    if (!USERNAME_PATTERN.test(u)) return 'Only letters, numbers, and underscores';
    return undefined;
  }, [username]);

  const passwordError = useMemo(() => {
    if (!password) return undefined;
    if (password.length < PASSWORD_MIN) return `At least ${PASSWORD_MIN} characters`;
    if (password.length > PASSWORD_MAX) return `At most ${PASSWORD_MAX} characters`;
    return undefined;
  }, [password]);

  const confirmError =
    confirm && confirm !== password ? 'Passwords do not match' : undefined;

  const canSubmit =
    username.trim().length >= USERNAME_MIN &&
    username.trim().length <= USERNAME_MAX &&
    USERNAME_PATTERN.test(username.trim()) &&
    password.length >= PASSWORD_MIN &&
    password.length <= PASSWORD_MAX &&
    password === confirm &&
    !registerMutation.isPending;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!canSubmit) return;
    try {
      const data = await registerMutation.mutateAsync({
        username: username.trim(),
        password,
      });
      login(data);
      await navigateAfterAuth(navigate, data.username);
    } catch {
      setError('Failed to create account. Please try again.');
    }
  };

  return (
    <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-md space-y-6">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Create an account</h2>
          <p className="mt-1 text-sm text-slate-500">
            Start your adaptive learning journey with Ami.
          </p>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit} noValidate>
          <InputField
            label="Username"
            type="text"
            placeholder="your_username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            error={usernameError}
            hint={
              !usernameError
                ? `${USERNAME_MIN}–${USERNAME_MAX} chars, letters, numbers, underscores only`
                : undefined
            }
            autoComplete="username"
            required
            minLength={USERNAME_MIN}
            maxLength={USERNAME_MAX}
            pattern="[a-zA-Z0-9_]+"
            title="Letters, numbers, and underscores only"
          />
          <InputField
            label="Password"
            type={showPassword ? 'text' : 'password'}
            placeholder={`At least ${PASSWORD_MIN} characters`}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={passwordError}
            hint={!passwordError ? `${PASSWORD_MIN}–${PASSWORD_MAX} characters` : undefined}
            autoComplete="new-password"
            required
            minLength={PASSWORD_MIN}
            maxLength={PASSWORD_MAX}
            rightAdornment={
              <PasswordToggle
                visible={showPassword}
                onToggle={() => setShowPassword((v) => !v)}
                id="toggle-password"
              />
            }
          />
          <InputField
            label="Confirm password"
            type={showConfirm ? 'text' : 'password'}
            placeholder="Repeat your password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            error={confirmError}
            autoComplete="new-password"
            required
            rightAdornment={
              <PasswordToggle
                visible={showConfirm}
                onToggle={() => setShowConfirm((v) => !v)}
                id="toggle-confirm"
              />
            }
          />
          {error && (
            <p className="text-sm text-red-600" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" className="w-full" disabled={!canSubmit}>
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
    </div>
  );
}
