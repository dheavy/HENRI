import { NavLink, Outlet } from 'react-router-dom';
import { LayoutDashboard, Zap, Radio, Wifi, FileText, Upload } from 'lucide-react';
import clsx from 'clsx';
import { useDashboard } from '../hooks/useApi';

const NAV = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/surges', icon: Zap, label: 'Surges' },
  { to: '/delegations', icon: Radio, label: 'Delegations' },
  { to: '/connectivity', icon: Wifi, label: 'Connectivity' },
  { to: '/report', icon: FileText, label: 'Report' },
  { to: '/fixtures', icon: Upload, label: 'Fixtures' },
];

export default function Layout() {
  const { data: dashboard } = useDashboard();
  const pipelineOk = dashboard?.pipeline_status?.last_run != null;

  return (
    <div className="flex h-screen">
      <nav className="w-14 shrink-0 bg-bg-deepest border-r border-border flex flex-col items-center">
        <div className="py-4 border-b border-border w-full flex justify-center">
          <span className="text-accent font-bold text-lg tracking-tight">H</span>
        </div>
        <div className="flex-1 py-2 w-full">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              title={label}
              className={({ isActive }) =>
                clsx(
                  'flex items-center justify-center py-3 transition-colors',
                  isActive
                    ? 'text-text-primary bg-bg-highlight border-l-[3px] border-accent'
                    : 'text-text-muted hover:text-text-body hover:bg-bg-elevated border-l-[3px] border-transparent'
                )
              }
            >
              <Icon size={18} />
            </NavLink>
          ))}
        </div>
        <div className="py-4 border-t border-border w-full flex justify-center">
          <span
            className={clsx(
              'w-2.5 h-2.5 rounded-full',
              pipelineOk ? 'bg-green' : 'bg-error',
            )}
            title={pipelineOk ? 'Pipeline healthy' : 'Pipeline not run'}
          />
        </div>
      </nav>
      <main className="flex-1 overflow-y-auto p-4 bg-bg-base">
        <Outlet />
      </main>
    </div>
  );
}
