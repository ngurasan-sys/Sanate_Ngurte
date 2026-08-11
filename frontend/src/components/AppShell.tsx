import React from 'react';
import { useUiStore } from '../stores/uiStore';
import Sidebar from './Sidebar';
import HeaderBar from './HeaderBar';

interface AppShellProps {
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const sidebarExpanded = useUiStore((state) => state.sidebarExpanded);

  return (
    <div className="flex min-h-screen w-full bg-zinc-950 text-zinc-100 overflow-x-hidden">
      {/* Sidebar - fixed left */}
      <div
        className={`shrink-0 border-r border-zinc-800 bg-zinc-900 transition-all duration-300 ${
          sidebarExpanded ? 'w-64' : 'w-16'
        }`}
      >
        <Sidebar />
      </div>

      {/* Main content wrapper */}
      <div className="flex flex-col flex-1 min-w-0">
        <HeaderBar />
        <main className="flex-1 p-6 lg:p-8 overflow-y-auto max-w-[1600px] w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
};

export default AppShell;
