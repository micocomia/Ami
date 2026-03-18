import { Outlet } from 'react-router-dom';
import { cn } from '@/lib/cn';
import { useSidebarCollapse } from '@/context/SidebarCollapseContext';
import { SideNav } from './SideNav';

/**
 * Layout for the Learning Session page: SideNav only, no TopBar.
 * Content area is full-height; the page owns center + right panel layout.
 */
export function LearningSessionLayout() {
  const { collapsed } = useSidebarCollapse();
  return (
    <div className="flex h-screen overflow-hidden bg-slate-100">
      <SideNav />
      <div
        className={cn(
          'flex flex-1 overflow-y-auto min-h-0 transition-[margin] duration-200',
          collapsed ? 'ml-16' : 'ml-sidebar',
        )}
      >
        <Outlet />
      </div>
    </div>
  );
}
