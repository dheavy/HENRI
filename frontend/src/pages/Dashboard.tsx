import { useDashboard, useCountries, useDelegations, useSurges } from '../hooks/useApi';
import AlertSummary from '../components/AlertSummary';
import RiskTable from '../components/RiskTable';
import EmptyState from '../components/EmptyState';
import SurgePulse from '../components/SurgePulse';
import SourceHealthRings from '../components/SourceHealthRings';
import DotHistogram from '../components/DotHistogram';
import AnimatedNumber from '../components/AnimatedNumber';

function StatCard({
  label,
  children,
  description,
  accent,
}: {
  label: string;
  children: React.ReactNode;
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
      <div className="text-data-display mt-2">{children}</div>
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
  const avgLeadHours = stats?.avg_lead_time_hours ?? null;

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
          <span style={{ fontSize: '20px', color: 'var(--color-text-muted)' }}>— Humanitarian Early-warning Network Intelligence</span>
        </h1>
        <p className="text-data" style={{ color: 'var(--color-text-muted)', marginTop: '4px' }}>
          Last update: {dashboard.generated_at ? (() => {
            const d = new Date(dashboard.generated_at);
            const utc = d.toLocaleString('en-GB', { day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short' });
            const local = d.toLocaleString('en-GB', { hour: '2-digit', minute: '2-digit', timeZoneName: 'short' });
            return `${utc} (${local})`;
          })() : '—'}
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
        <p className="text-small text-text-muted mt-1">AI-generated briefing based on the latest data — coming soon</p>
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm italic text-text-muted text-center">
            Coming soon
          </p>
        </div>
      </div>

      {/* Risk table: span 2 */}
      <div
        style={{ gridColumn: 'span 2', maxHeight: '500px', overflowY: 'auto' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <h3 className="text-label">
          Threat landscape — {countriesData?.countries.length ?? 0} countries
        </h3>
        <p className="text-small text-text-muted mt-1 mb-3">Combined risk score from conflict data, outage monitoring, and internal network alerts</p>
        {countriesData?.countries && <RiskTable countries={countriesData.countries} />}
      </div>

      {/* 4. Stat cards: each span 1 */}
      <div style={{ gridColumn: 'span 1' }}>
        <StatCard
          label="Surges with precursors"
          description={`Of ${totalSurges} outage clusters, ${surgesWithPrecursors} had warning signals visible before the outage.`}
          accent
        >
          <AnimatedNumber value={surgesWithPrecursors} className="text-data-display" />
          <span className="text-text-muted text-data-display"> / </span>
          <AnimatedNumber value={totalSurges} className="text-data-display" />
        </StatCard>
      </div>
      <div style={{ gridColumn: 'span 1' }}>
        <StatCard
          label="Detection rate"
          description={detectionPct != null
            ? 'More than half of all network outages could have been anticipated.'
            : undefined}
        >
          {detectionPct != null
            ? <AnimatedNumber value={detectionPct} suffix="%" className="text-data-display" />
            : <span className="text-data-display">--</span>}
        </StatCard>
      </div>
      <div style={{ gridColumn: 'span 1' }}>
        <StatCard
          label="Avg lead time"
          description={avgLeadHours != null
            ? `Average warning time before connectivity loss: ~${(avgLeadHours / 24).toFixed(1)} days of advance notice.`
            : undefined}
        >
          {avgLeadHours != null
            ? <AnimatedNumber value={avgLeadHours} decimals={1} suffix="h" className="text-data-display" />
            : <span className="text-data-display">--</span>}
        </StatCard>
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
        <p className="text-label">Incident volume by region</p>
        <p className="text-small text-text-muted mt-1 mb-3">Monthly incident distribution across ICT regions — each dot represents ~50 incidents</p>
        <DotHistogram />
      </div>

      {/* Bottom: delegations | bandwidth | source health + data coherence */}
      <div
        style={{ gridColumn: 'span 1' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <h3 className="text-label">Most alerting delegations</h3>
        <p className="text-small text-text-muted mt-1 mb-3">Field sites ranked by total alert volume in the current dataset</p>
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

      {/* Column 2: Source health + Data coherence stacked */}
      <div style={{ gridColumn: 'span 1', alignSelf: 'start' }} className="flex flex-col gap-3">

      {/* Source health */}
      <div className="bg-bg-surface border border-border rounded-lg p-5">
        <SourceHealthRings sources={pipeline_status.sources} lastRun={pipeline_status.last_run} />
      </div>

      {/* Data coherence — UC-3 */}
      <div className="bg-bg-surface border border-border rounded-lg p-5">
        <h3 className="text-label">Data coherence</h3>
        <p className="text-small text-text-muted mt-1 mb-3">Inventory completeness across data sources — gaps indicate missing configuration</p>
        {dashboard.data_coherence ? (() => {
          const dc = dashboard.data_coherence as { netbox_sites: number; grafana_sites: number; circuits_total: number; circuits_with_rate: number; silent_sites: number };
          const nbPct = dc.grafana_sites > 0 ? Math.round(dc.netbox_sites / dc.grafana_sites * 100) : 0;
          const ratePct = dc.circuits_total > 0 ? Math.round(dc.circuits_with_rate / dc.circuits_total * 100) : 0;
          return (
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-data text-sm mb-1">
                  <span>{dc.netbox_sites} / {dc.grafana_sites} sites in NetBox</span>
                  <span className="text-text-muted">{nbPct}%</span>
                </div>
                <div className="h-1.5 bg-bg-highlight rounded-full overflow-hidden">
                  <div className="h-full bg-accent rounded-full" style={{ width: `${nbPct}%` }} />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-data text-sm mb-1">
                  <span>{dc.circuits_with_rate} / {dc.circuits_total} circuits with committed rate</span>
                  <span className="text-text-muted">{ratePct}%</span>
                </div>
                <div className="h-1.5 bg-bg-highlight rounded-full overflow-hidden">
                  <div className="h-full bg-accent rounded-full" style={{ width: `${ratePct}%` }} />
                </div>
              </div>
              {dc.silent_sites > 0 && (
                <p className="text-data text-sm text-yellow">{dc.silent_sites} sites with zero incidents in 90 days</p>
              )}
            </div>
          );
        })() : (
          <p className="text-small text-text-muted italic">No coherence data available</p>
        )}
      </div>

      </div>{/* end stacked column */}

      {/* Bandwidth — UC-1 */}
      <div
        style={{ gridColumn: 'span 1', alignSelf: 'start' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <h3 className="text-label">Bandwidth — top consumers</h3>
        <p className="text-small text-text-muted mt-1 mb-3">Highest peak throughput across field sites in the last 7 days</p>
        {dashboard.bandwidth_top && dashboard.bandwidth_top.length > 0 ? (
          <div className="space-y-1.5">
            {dashboard.bandwidth_top.map((b) => (
              <div key={b.site} className="flex items-center justify-between">
                <span className="text-data text-text-primary">{b.site}</span>
                <span className="text-data text-text-muted">
                  {b.utilisation_pct != null
                    ? <><span className="text-text-primary">{b.utilisation_pct}%</span> util</>
                    : <><span className="text-text-primary">{b.peak_mbps}</span> Mbps peak</>}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-small text-text-muted italic">No bandwidth data available — Grafana pull pending</p>
        )}
      </div>
    </div>
  );
}
