import { Outlet } from 'react-router-dom';
import { SideNav } from './SideNav';

/**
 * Layout for the Learning Session page: SideNav only, no TopBar.
 * Content area is full-height; the page owns center + right panel layout.
 */
export function LearningSessionLayout() {
  return (
    <div className="flex h-screen overflow-hidden bg-slate-100">
      <SideNav />
      <div className="flex flex-1 ml-sidebar overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
