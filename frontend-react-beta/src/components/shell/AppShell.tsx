import { Outlet } from 'react-router-dom';
import { SideNav } from './SideNav';

export function AppShell() {
  return (
    <div className="flex min-h-screen bg-surface">
      <SideNav />

      <div className="flex flex-col flex-1 min-h-0 ml-sidebar">
        <main className="flex-1 min-h-0 p-page overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
