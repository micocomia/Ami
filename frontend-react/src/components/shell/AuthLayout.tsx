import { Outlet } from 'react-router-dom';
import Logo from '@/assets/Logo_black.png';

export function AuthLayout() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-alt">
      <div className="w-full max-w-md mx-4">
        <div className="flex flex-col items-center mb-8">
          <img src={Logo} alt="Ami" className="h-12 w-auto mb-3" />
          <p className="text-sm text-slate-500 mt-1">Adaptive Mentoring Intelligence</p>
        </div>
        <div className="bg-white rounded-xl shadow-md p-8">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
