import { Outlet } from 'react-router-dom';
import { cn } from '@/lib/cn';
import { useSidebarCollapse } from '@/context/SidebarCollapseContext';
import { SideNav } from './SideNav';

export function AppShell() {
  const { collapsed } = useSidebarCollapse();
  return (
    <div className="flex min-h-screen bg-surface">
      <SideNav />

      <div
        className={cn(
          'flex flex-col flex-1 min-h-0 transition-[margin] duration-200',
          collapsed ? 'ml-16' : 'ml-sidebar',
        )}
      >
        <main className="flex-1 min-h-0 p-page overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
