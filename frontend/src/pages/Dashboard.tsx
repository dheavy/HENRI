import { useDashboard, useCountries } from '../hooks/useApi';
import { PrecursorBanner, DeltaBanner } from '../components/AlertBanner';
import RiskTable from '../components/RiskTable';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import { Shield, AlertTriangle, Zap, Globe } from 'lucide-react';

function StatCard({
  label,
  value,
  icon: Icon,
  colorClass,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  colorClass: string;
}) {
  return (
    <div className="bg-bg-surface rounded-lg border border-border p-4">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${colorClass}`}>
          <Icon size={18} />
        </div>
        <div>
          <p className="text-xs text-text-muted uppercase tracking-wider">{label}</p>
          <p className="text-2xl font-bold font-mono text-text-primary">{value}</p>
        </div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { data: dashboard, isLoading: dashLoading } = useDashboard();
  const { data: countriesData } = useCountries('sort=risk_score&order=desc');

  if (dashLoading) {
    return <div className="text-text-muted">Loading dashboard...</div>;
  }

  if (!dashboard || (!dashboard.risk_cards?.length && !dashLoading)) {
    return <EmptyState
      title="No dashboard data"
      message="The pipeline has not been run yet. Generate reports to see the threat landscape, alerts, and delegation status."
    />;
  }

  const { alerts, delta_alerts, risk_summary, pipeline_status } = dashboard;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold text-text-primary">Dashboard</h2>
        <p className="text-sm text-text-muted mt-1">
          Real-time overview of network risk across ICRC field delegations. Active precursor warnings,
          risk score changes, and the full country threat landscape at a glance.
        </p>
      </div>

      {/* Alert banners */}
      {alerts.length > 0 && (
        <div>
          {alerts.map((a, i) => (
            <PrecursorBanner key={i} alert={a} />
          ))}
        </div>
      )}
      {delta_alerts.length > 0 && (
        <div>
          {delta_alerts.map((d, i) => (
            <DeltaBanner key={i} alert={d} />
          ))}
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard label="High Risk" value={risk_summary.high} icon={AlertTriangle} colorClass="bg-[#F0717833] text-red" />
        <StatCard label="Medium Risk" value={risk_summary.medium} icon={Shield} colorClass="bg-[#F78C6C33] text-orange" />
        <StatCard label="Low Risk" value={risk_summary.low} icon={Globe} colorClass="bg-[#FFCB6B22] text-yellow" />
        <StatCard label="Minimal" value={risk_summary.minimal} icon={Zap} colorClass="bg-[#C3E88D15] text-green" />
      </div>

      {/* Pipeline status */}
      <div className="bg-bg-surface rounded-lg border border-border p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-text-primary">Pipeline Status</h3>
          <span className="text-xs text-text-muted font-mono">
            Last run: {pipeline_status.last_run ? new Date(pipeline_status.last_run).toLocaleString() : 'Never'}
          </span>
        </div>
        <div className="flex gap-6 mt-3">
          {Object.entries(pipeline_status.sources).map(([name, info]) => (
            <div key={name} className="flex items-center gap-2">
              <StatusBadge status={info.status} />
              <span className="text-xs text-text-muted capitalize">{name}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Risk table */}
      <div className="bg-bg-surface rounded-lg border border-border p-4">
        <h3 className="text-sm font-medium text-text-primary mb-4">
          Threat Landscape — {countriesData?.countries.length ?? 0} Countries
        </h3>
        {countriesData?.countries && <RiskTable countries={countriesData.countries} />}
      </div>
    </div>
  );
}
