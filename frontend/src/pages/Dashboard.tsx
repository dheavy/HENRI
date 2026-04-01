import { useDashboard, useCountries, useDelegations, useSurges } from '../hooks/useApi';
import AlertSummary from '../components/AlertSummary';
import RiskTable from '../components/RiskTable';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import SurgePulse from '../components/SurgePulse';
import DotMatrixMap from '../components/DotMatrixMap';
import SourceHealthRings from '../components/SourceHealthRings';
import DotHistogram from '../components/DotHistogram';

function StatCard({
  label,
  value,
  description,
  accent,
}: {
  label: string;
  value: string | number;
  description?: string;
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
      {description && <p className="text-sm text-text-muted mt-2">{description}</p>}
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
  const totalSurges = stats?.total_surges ?? 0;
  const surgesWithPrecursors = stats?.with_external_precursor ?? 0;
  const detectionPct = stats?.pct_with_precursor != null ? Math.round(stats.pct_with_precursor) : null;
  const detectionRate = detectionPct != null ? `${detectionPct}%` : '--';
  const avgLeadHours = stats?.avg_lead_time_hours ?? null;
  const avgLeadTime = avgLeadHours != null ? `${avgLeadHours.toFixed(1)}h` : '--';

  // Filter out HQ delegations (Fix 9)
  const topDelegations = (delegationsData?.delegations ?? [])
    .filter((d) => d.region !== 'HQ' && d.region !== '')
    .slice(0, 10);

  return (
    <div
      className="max-w-[1440px] mx-auto"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(12, 1fr)',
        gridAutoRows: 'minmax(80px, auto)',
        gap: '12px',
        padding: '16px',
        minHeight: 'calc(100vh - 32px)',
      }}
    >
      {/* Alert summary — full width */}
      {(alerts.length > 0 || delta_alerts.length > 0) && (
        <div style={{ gridColumn: 'span 12' }}>
          <AlertSummary alerts={alerts} deltaAlerts={delta_alerts} />
        </div>
      )}

      {/* Dot-matrix map: span 5, row-span 3 */}
      <div
        style={{ gridColumn: 'span 5', gridRow: 'span 3' }}
        className="bg-bg-surface border border-border rounded-lg overflow-hidden"
      >
        {countriesData?.countries ? (
          <DotMatrixMap countries={countriesData.countries} />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <p className="text-small">Loading map...</p>
          </div>
        )}
      </div>

      {/* Risk table: span 7, row-span 3 */}
      <div
        style={{ gridColumn: 'span 7', gridRow: 'span 3' }}
        className="bg-bg-surface border border-border rounded-lg p-5 overflow-y-auto"
      >
        <h3 className="text-label mb-3">
          Threat Landscape — {countriesData?.countries.length ?? 0} Countries
        </h3>
        {countriesData?.countries && <RiskTable countries={countriesData.countries} />}
      </div>

      {/* 3 stat cards: span 4 each = 12 cols */}
      <div style={{ gridColumn: 'span 4' }}>
        <StatCard
          label="Surges with precursors"
          value={`${surgesWithPrecursors} / ${totalSurges}`}
          description={`Of ${totalSurges} outage clusters, ${surgesWithPrecursors} had warning signals visible before the outage.`}
          accent
        />
      </div>
      <div style={{ gridColumn: 'span 4' }}>
        <StatCard
          label="Detection rate"
          value={detectionRate}
          description={detectionPct != null
            ? `More than half of all network outages could have been anticipated.`
            : undefined}
        />
      </div>
      <div style={{ gridColumn: 'span 4' }}>
        <StatCard
          label="Avg lead time"
          value={avgLeadTime}
          description={avgLeadHours != null
            ? `Average warning time before connectivity loss: ~${(avgLeadHours / 24).toFixed(1)} days of advance notice.`
            : undefined}
        />
      </div>

      {/* Surge pulse: span 5 */}
      <div
        style={{ gridColumn: 'span 5' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <SurgePulse surges={surgesData?.surges ?? []} />
      </div>

      {/* Source health: span 2 */}
      <div
        style={{ gridColumn: 'span 2' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <SourceHealthRings sources={pipeline_status.sources} />
      </div>

      {/* Region volume: span 5 */}
      <div
        style={{ gridColumn: 'span 5' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <DotHistogram />
      </div>

      {/* Top delegations: span 5 */}
      <div
        style={{ gridColumn: 'span 5' }}
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

      {/* Pipeline status: span 2 */}
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
