import { useDashboard, useCountries, useDelegations, useSurges } from '../hooks/useApi';
import { useQuery } from '@tanstack/react-query';
import AlertSummary from '../components/AlertSummary';
import RiskTable from '../components/RiskTable';
import EmptyState from '../components/EmptyState';
import SurgePulse from '../components/SurgePulse';
import SourceHealth from '../components/SourceHealth';
import DotHistogram from '../components/DotHistogram';
import AnimatedNumber from '../components/AnimatedNumber';

function BandwidthScorecard() {
  const { data } = useQuery({
    queryKey: ['bandwidth'],
    queryFn: () => fetch('/api/v1/bandwidth').then(r => r.json()),
    staleTime: 60_000,
  });
  if (!data?.summary) return <p className="text-small text-text-muted italic">Loading...</p>;
  const { summary } = data;
  const hasUtil = summary.sites_with_utilisation > 0;

  return (
    <div className="space-y-3">
      {hasUtil && summary.over_utilised.length > 0 && (
        <div>
          <p className="text-data text-sm text-red mb-1">Over-utilised (&gt;80%)</p>
          {summary.over_utilised.slice(0, 5).map((s: { site: string; pct: number; provider: string }) => (
            <div key={s.site} className="flex justify-between text-data text-sm">
              <span className="text-text-primary">{s.site}</span>
              <span><span className="text-red">{s.pct}%</span> <span className="text-text-muted">{s.provider}</span></span>
            </div>
          ))}
        </div>
      )}
      {hasUtil && summary.under_utilised.length > 0 && (
        <div>
          <p className="text-data text-sm text-yellow mb-1">Under-utilised (&lt;10%)</p>
          {summary.under_utilised.slice(0, 5).map((s: { site: string; pct: number; provider: string }) => (
            <div key={s.site} className="flex justify-between text-data text-sm">
              <span className="text-text-primary">{s.site}</span>
              <span><span className="text-yellow">{s.pct}%</span> <span className="text-text-muted">{s.provider}</span></span>
            </div>
          ))}
        </div>
      )}
      {summary.zero_traffic.length > 0 && (
        <p className="text-data text-sm text-orange">{summary.zero_traffic.length} sites with near-zero traffic</p>
      )}
      <p className="text-small text-text-muted">
        Utilisation data for {summary.sites_with_utilisation} of {summary.sites_with_bandwidth} sites.
        {!hasUtil && ' Coverage improves as NetBox circuit records are completed.'}
      </p>
    </div>
  );
}

function CoherenceCard() {
  const { data } = useQuery({
    queryKey: ['coherence'],
    queryFn: () => fetch('/api/v1/coherence').then(r => r.json()),
    staleTime: 60_000,
  });
  if (!data) return <p className="text-small text-text-muted italic">Loading...</p>;

  const items = [
    { label: `${data.netbox_coverage.matched} / ${data.netbox_coverage.total_grafana} sites in NetBox`, pct: data.netbox_coverage.pct },
    { label: `${data.commit_rate_coverage.with_rate} / ${data.commit_rate_coverage.total_circuits} circuits with committed rate`, pct: data.commit_rate_coverage.pct },
  ];

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.label}>
          <div className="flex justify-between text-data text-sm mb-1">
            <span>{item.label}</span>
            <span className="text-text-muted">{item.pct}%</span>
          </div>
          <div className="h-1.5 bg-bg-highlight rounded-full overflow-hidden">
            <div className="h-full bg-accent rounded-full" style={{ width: `${item.pct}%` }} />
          </div>
        </div>
      ))}
      {data.grafana_not_in_netbox.length > 0 && (
        <p className="text-data text-sm">{data.grafana_not_in_netbox.length} Grafana sites not in NetBox</p>
      )}
      {data.netbox_not_in_grafana.length > 0 && (
        <p className="text-data text-sm">{data.netbox_not_in_grafana.length} NetBox circuits with no Grafana match</p>
      )}
      {data.zero_incident_sites.length > 0 && (
        <p className="text-data text-sm text-yellow">{data.zero_incident_sites.length} sites with zero incidents in 90 days</p>
      )}
      {data.snow_orphan_codes.length > 0 && (
        <p className="text-data text-sm">{data.snow_orphan_codes.length} ServiceNow codes not in Grafana</p>
      )}
    </div>
  );
}

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
        className="bg-bg-surface border border-border rounded-lg overflow-hidden"
      >
        <div className="px-5 pt-5 pb-3">
          <h3 className="text-label">
            Threat landscape — {countriesData?.countries.length ?? 0} countries
          </h3>
          <p className="text-small text-text-muted mt-1">Combined risk score from conflict data, outage monitoring, and internal network alerts</p>
        </div>
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
        style={{ gridColumn: 'span 1', alignSelf: 'start' }}
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

      {/* Column 2: Source health */}
      <div
        style={{ gridColumn: 'span 1', alignSelf: 'start' }}
        className="bg-bg-surface border border-border rounded-lg p-5"
      >
        <SourceHealth sources={pipeline_status.sources} lastRun={pipeline_status.last_run} />
      </div>

      {/* Column 3: Bandwidth scorecard + Data coherence stacked */}
      <div style={{ gridColumn: 'span 1', alignSelf: 'start' }} className="flex flex-col gap-3">

      {/* Bandwidth scorecard — UC-1 */}
      <div className="bg-bg-surface border border-border rounded-lg p-5">
        <h3 className="text-label">Bandwidth scorecard</h3>
        <p className="text-small text-text-muted mt-1 mb-3">Actual throughput vs contracted capacity — identifies over-paying and under-provisioned sites</p>
        <BandwidthScorecard />
      </div>

      {/* Data coherence — UC-3 */}
      <div className="bg-bg-surface border border-border rounded-lg p-5">
        <h3 className="text-label">Data coherence</h3>
        <p className="text-small text-text-muted mt-1 mb-3">Inventory completeness across data sources — gaps indicate missing configuration</p>
        <CoherenceCard />
      </div>

      </div>{/* end stacked column */}
    </div>
  );
}
