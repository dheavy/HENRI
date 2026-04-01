import { NavLink, Outlet } from 'react-router-dom';
import { LayoutDashboard, Zap, Radio, FileText } from 'lucide-react';
import clsx from 'clsx';

const NAV = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/surges', icon: Zap, label: 'Surges' },
  { to: '/delegations', icon: Radio, label: 'Delegations' },
  { to: '/report', icon: FileText, label: 'Report' },
];

export default function Layout() {
  return (
    <div className="flex h-screen">
      <nav className="w-56 shrink-0 bg-bg-deepest border-r border-border flex flex-col">
        <div className="p-4 border-b border-border">
          <h1 className="text-lg font-bold font-mono tracking-tight text-text-primary">
            <span className="text-accent">HENRI</span>
          </h1>
          <p className="text-xs text-text-muted mt-0.5">Network Intelligence</p>
        </div>
        <div className="flex-1 py-2">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-4 py-2.5 text-sm transition-colors',
                  isActive
                    ? 'text-text-primary bg-bg-highlight border-r-2 border-accent'
                    : 'text-text-muted hover:text-text-body hover:bg-bg-elevated'
                )
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </div>
        <div className="p-4 border-t border-border text-xs text-text-muted">
          ICRC Field IT
        </div>
      </nav>
      <main className="flex-1 overflow-y-auto p-6 bg-bg-base">
        <Outlet />
      </main>
    </div>
  );
}
