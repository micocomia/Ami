import { Outlet } from 'react-router-dom';

export function AuthLayout() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-alt">
      <div className="w-full max-w-md mx-4">
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-primary-600 text-white flex items-center justify-center font-bold text-xl mb-3">
            A
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Ami</h1>
          <p className="text-sm text-slate-500 mt-1">Adaptive Mentoring Intelligence</p>
        </div>
        <div className="bg-white rounded-xl shadow-md p-8">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
