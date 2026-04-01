import { useDashboard, useCountries, useDelegations, useSurges } from '../hooks/useApi';
import { PrecursorBanner, DeltaBanner } from '../components/AlertBanner';
import RiskTable from '../components/RiskTable';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import SurgePulse from '../components/SurgePulse';
import MiniGlobe from '../components/MiniGlobe';
import SourceHealthRings from '../components/SourceHealthRings';
import DotHistogram from '../components/DotHistogram';

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent?: boolean;
}) {
  return (
    <div
      className={`bg-bg-surface border border-border rounded-lg p-5 ${
        accent ? 'border-l-2 border-l-accent' : ''
      }`}
    >
      <p className="text-label">{label}</p>
      <p className="text-data-display mt-2">{value}</p>
    </div>
  );
}


export default function Dashboard() {
  const { data: dashboard, isLoading: dashLoading } = useDashboard();
  const { data: countriesData } = useCountries('sort=risk_score&order=desc');
  const { data: delegationsData } = useDelegations('sort=incident_count_30d&order=desc&limit=10');
  const { data: surgesData } = useSurges();

  if (dashLoading) {
    return <div className="text-text-muted">Loading dashboard...</div>;
  }

  if (!dashboard || (!dashboard.risk_cards?.length && !dashLoading)) {
    return (
      <EmptyState
        title="No dashboard data"
        message="The pipeline has not been run yet. Generate reports to see the threat landscape, alerts, and delegation status."
      />
    );
  }

  const { alerts, delta_alerts, pipeline_status } = dashboard;

  const stats = surgesData?.stats;
  const surgesWithPrecursors = stats?.with_external_precursor ?? 0;
  const detectionRate = stats?.pct_with_precursor != null ? `${Math.round(stats.pct_with_precursor)}%` : '--';
  const avgLeadTime = stats?.avg_lead_time_hours != null ? `${stats.avg_lead_time_hours.toFixed(1)}h` : '--';

  const topDelegations = delegationsData?.delegations.slice(0, 10) ?? [];

  return (
    <div
      className="max-w-[1440px] mx-auto"
      style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '12px' }}
    >
      {/* Row 1: Alert banners — full width */}
      {(alerts.length > 0 || delta_alerts.length > 0) && (
        <div style={{ gridColumn: 'span 12' }}>
          {alerts.map((a, i) => (
            <PrecursorBanner key={i} alert={a} />
          ))}
          {delta_alerts.map((d, i) => (
            <DeltaBanner key={i} alert={d} />
          ))}
        </div>
      )}

      {/* Row 2: Globe placeholder + Risk table */}
      <div
        style={{ gridColumn: 'span 5' }}
        className="bg-bg-surface border border-border rounded-lg h-[400px] overflow-hidden"
      >
        {countriesData?.countries ? (
          <MiniGlobe countries={countriesData.countries} />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <p className="text-small">Loading globe...</p>
          </div>
        )}
      </div>

      <div
        style={{ gridColumn: 'span 7' }}
        className="bg-bg-surface border border-border rounded-lg p-5 h-[400px] overflow-y-auto"
      >
        <h3 className="text-label mb-3">
          Threat Landscape — {countriesData?.countries.length ?? 0} Countries
        </h3>
        {countriesData?.countries && <RiskTable countries={countriesData.countries} />}
      </div>

      {/* Row 3: 3 stat cards + Surge pulse + Source health */}
      <div style={{ gridColumn: 'span 2' }}>
        <StatCard label="Surges with precursors" value={surgesWithPrecursors} accent />
      </div>
      <div style={{ gridColumn: 'span 2' }}>
        <StatCard label="Detection rate" value={detectionRate} />
      </div>
      <div style={{ gridColumn: 'span 2' }}>
        <StatCard label="Avg lead time" value={avgLeadTime} />
      </div>
      <div
        style={{ gridColumn: 'span 4' }}
        className="bg-bg-surface border border-border rounded-lg p-5 h-[120px]"
      >
        <SurgePulse surges={surgesData?.surges ?? []} />
      </div>
      <div
        style={{ gridColumn: 'span 2' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <SourceHealthRings sources={pipeline_status.sources} />
      </div>

      {/* Row 4: Region volume + Top delegations + Pipeline status */}
      <div
        style={{ gridColumn: 'span 6' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <h3 className="text-label mb-2">Region Volume</h3>
        <DotHistogram />
      </div>

      <div
        style={{ gridColumn: 'span 4' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <h3 className="text-label mb-3">Top Delegations</h3>
        {topDelegations.length === 0 ? (
          <p className="text-small">No delegation data available</p>
        ) : (
          <ol className="space-y-1.5">
            {topDelegations.map((d, i) => (
              <li key={d.site_code} className="flex items-center justify-between">
                <span className="text-data">
                  <span className="text-text-muted mr-2">{i + 1}.</span>
                  {d.site_code}
                </span>
                <span className="flex items-center gap-3">
                  <span className="text-data">{d.incident_count_30d}</span>
                  {d.dominant_alert && (
                    <span className="text-small truncate max-w-[120px]">{d.dominant_alert}</span>
                  )}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>

      <div
        style={{ gridColumn: 'span 2' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <h3 className="text-label mb-3">Pipeline Status</h3>
        <p className="text-small mb-3">
          {pipeline_status.last_run
            ? new Date(pipeline_status.last_run).toLocaleString()
            : 'Never run'}
        </p>
        <div className="space-y-2">
          {Object.entries(pipeline_status.sources).map(([name, info]) => (
            <div key={name} className="flex items-center gap-2">
              <StatusBadge status={info.status} />
              <span className="text-small capitalize">{name}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
