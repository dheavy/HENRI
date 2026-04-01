import { useDashboard, useCountries, useDelegations, useSurges } from '../hooks/useApi';
import AlertSummary from '../components/AlertSummary';
import RiskTable from '../components/RiskTable';
import EmptyState from '../components/EmptyState';
import SurgePulse from '../components/SurgePulse';
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
  const { data: delegationsData } = useDelegations();
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

  const hasAlerts = alerts.length > 0 || delta_alerts.length > 0;

  // Filter out HQ delegations
  const topDelegations = (delegationsData?.delegations ?? [])
    .filter((d) => d.region && d.region !== 'HQ')
    .slice(0, 10);

  return (
    <div
      className="max-w-[1440px] mx-auto"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '12px',
        padding: '16px',
      }}
    >
      {/* 1. Title — always first */}
      <div style={{ gridColumn: 'span 3' }}>
        <h1 style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
          <span className="text-heading">HENRI</span>
          <span style={{ fontSize: '20px', color: 'var(--color-text-muted)' }}>— Network intelligence</span>
        </h1>
        <p className="text-data" style={{ color: 'var(--color-text-muted)', marginTop: '4px' }}>
          Last update: {dashboard.generated_at ? new Date(dashboard.generated_at).toLocaleString('en-GB', {
            day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short'
          }) : '—'}
        </p>
      </div>

      {/* 2. Alert explainer + alert card */}
      {hasAlerts && (
        <>
          <div style={{ gridColumn: 'span 3' }}>
            <p style={{ fontSize: '14px', color: 'var(--color-text-muted)' }}>
              Conflict activity above normal levels — network disruption possible within 24-72h
            </p>
          </div>
          <div style={{ gridColumn: 'span 3' }}>
            <AlertSummary alerts={alerts} deltaAlerts={delta_alerts} />
          </div>
        </>
      )}

      {/* 3. LLM report placeholder (was map): span 1 */}
      <div
        style={{ gridColumn: 'span 1', minHeight: '200px' }}
        className="bg-bg-surface border border-border rounded-lg p-5 flex flex-col"
      >
        <p className="text-label">Intelligence summary</p>
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm italic text-text-muted text-center">
            LLM-generated briefing coming soon
          </p>
        </div>
      </div>

      {/* Risk table: span 2 */}
      <div
        style={{ gridColumn: 'span 2', maxHeight: '500px', overflowY: 'auto' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <h3 className="text-label mb-3">
          Threat landscape — {countriesData?.countries.length ?? 0} countries
        </h3>
        {countriesData?.countries && <RiskTable countries={countriesData.countries} />}
      </div>

      {/* 4. Stat cards: each span 1 */}
      <div style={{ gridColumn: 'span 1' }}>
        <StatCard
          label="Surges with precursors"
          value={`${surgesWithPrecursors} / ${totalSurges}`}
          description={`Of ${totalSurges} outage clusters, ${surgesWithPrecursors} had warning signals visible before the outage.`}
          accent
        />
      </div>
      <div style={{ gridColumn: 'span 1' }}>
        <StatCard
          label="Detection rate"
          value={detectionRate}
          description={detectionPct != null
            ? 'More than half of all network outages could have been anticipated.'
            : undefined}
        />
      </div>
      <div style={{ gridColumn: 'span 1' }}>
        <StatCard
          label="Avg lead time"
          value={avgLeadTime}
          description={avgLeadHours != null
            ? `Average warning time before connectivity loss: ~${(avgLeadHours / 24).toFixed(1)} days of advance notice.`
            : undefined}
        />
      </div>

      {/* 5. Surge activity: span 2 */}
      <div
        style={{ gridColumn: 'span 2' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <SurgePulse surges={surgesData?.surges ?? []} />
      </div>

      {/* Incident volume: span 1 */}
      <div
        style={{ gridColumn: 'span 1' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <DotHistogram />
      </div>

      {/* 6. Bottom row: two-way split */}
      <div
        style={{ gridColumn: 'span 1' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <h3 className="text-label mb-3">Most alerting delegations</h3>
        {topDelegations.length === 0 ? (
          <p className="text-small">No delegation data available</p>
        ) : (
          <ol className="space-y-1.5">
            {topDelegations.map((d, i) => (
              <li key={d.site_code} className="flex items-center gap-3">
                <span className="text-data text-text-muted w-5 text-right shrink-0">{i + 1}.</span>
                <span className="text-data text-text-primary w-12 shrink-0">{d.site_code}</span>
                <span className="text-data text-text-primary w-10 shrink-0">{d.incident_count_30d}</span>
                <span className="text-small text-text-muted truncate">{d.dominant_alert}</span>
              </li>
            ))}
          </ol>
        )}
      </div>

      <div
        style={{ gridColumn: 'span 1' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <SourceHealthRings sources={pipeline_status.sources} lastRun={pipeline_status.last_run} />
      </div>
    </div>
  );
}
