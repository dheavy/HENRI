import { useState } from 'react';
import { useConnectivity } from '../hooks/useApi';
import type { ConnectivitySite, ConnectivityLink } from '../api/client';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';

const GRADE_COLORS: Record<string, string> = {
  Excellent: 'var(--color-green)',
  Good: 'var(--color-green)',
  Adequate: 'var(--color-yellow)',
  Degraded: 'var(--color-orange)',
  Critical: 'var(--color-red)',
  'No data': 'var(--color-text-muted)',
};

function gradeColor(grade: string): string {
  return GRADE_COLORS[grade] ?? 'var(--color-text-muted)';
}

function scoreColor(score: number): string {
  if (score >= 90) return 'var(--color-green)';
  if (score >= 70) return 'var(--color-green)';
  if (score >= 50) return 'var(--color-yellow)';
  if (score >= 25) return 'var(--color-orange)';
  return 'var(--color-red)';
}

function CompletenessBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-bg-highlight overflow-hidden">
        <div
          className="h-full bg-green"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-data text-xs text-text-muted">{pct}%</span>
    </div>
  );
}

function LinkRow({ link }: { link: ConnectivityLink }) {
  return (
    <tr className="border-t border-border/50">
      <td className="py-1.5 px-3 text-data text-sm">{link.cid}</td>
      <td className="py-1.5 px-3 text-data text-sm text-text-muted">
        {link.link_type ?? '\u2014'}
      </td>
      <td className="py-1.5 px-3 text-data text-sm text-text-muted">
        {link.provider ?? '\u2014'}
      </td>
      <td className="py-1.5 px-3 text-data text-sm">
        <span className={link.rtt_source === 'estimated' ? 'italic text-text-muted' : ''}>
          {link.rtt_ms.toFixed(0)} ms
        </span>
        {link.rtt_source === 'estimated' && (
          <span className="text-xs text-text-muted ml-1">est.</span>
        )}
      </td>
      <td className="py-1.5 px-3 text-data text-sm">
        <span className={link.loss_source === 'default' ? 'italic text-text-muted' : ''}>
          {(link.loss * 100).toFixed(2)}%
        </span>
        {link.loss_source === 'default' && (
          <span className="text-xs text-text-muted ml-1">est.</span>
        )}
      </td>
      <td className="py-1.5 px-3 text-data text-sm">
        {link.mathis_mbps.toFixed(1)} Mbps
      </td>
      <td className="py-1.5 px-3 text-data text-sm">
        {link.capacity_mbps != null ? `${link.capacity_mbps.toFixed(1)} Mbps` : '\u2014'}
      </td>
      <td className="py-1.5 px-3 text-data text-sm font-semibold">
        {link.effective_mbps.toFixed(2)} Mbps
      </td>
      <td className="py-1.5 px-3 text-data text-sm text-text-muted">
        {link.is_primary ? 'Primary' : 'Backup'}
      </td>
    </tr>
  );
}

function ExpandedRow({ site }: { site: ConnectivitySite }) {
  return (
    <tr>
      <td colSpan={9} className="bg-bg-elevated px-5 py-3">
        <div className="mb-2">
          <span className="text-label text-xs">
            Link breakdown — {site.site_code}
          </span>
          <span className="text-text-muted text-xs ml-2">
            {site.num_users} users ({site.num_users_source}) · Diversity bonus: {site.diversity_bonus.toFixed(2)}x
            {site.availability_penalty < 1 && ` · Availability penalty: ${site.availability_penalty.toFixed(3)}`}
          </span>
        </div>
        <table className="w-full text-left">
          <thead>
            <tr className="text-label text-xs">
              <th className="py-1 px-3">CID</th>
              <th className="py-1 px-3">Type</th>
              <th className="py-1 px-3">Provider</th>
              <th className="py-1 px-3">RTT</th>
              <th className="py-1 px-3">Loss</th>
              <th className="py-1 px-3">Mathis</th>
              <th className="py-1 px-3">Capacity</th>
              <th className="py-1 px-3">Effective</th>
              <th className="py-1 px-3">Role</th>
            </tr>
          </thead>
          <tbody>
            {site.links.map(link => (
              <LinkRow key={link.cid} link={link} />
            ))}
          </tbody>
        </table>
      </td>
    </tr>
  );
}

function CoverageChart({
  coverage,
}: {
  coverage: {
    has_bandwidth: number;
    has_circuits: number;
    has_rtt: number;
    has_loss: number;
    has_jitter: number;
    has_dhcp: number;
    has_availability: number;
    full_data: number;
    total_sites: number;
  };
}) {
  const total = coverage.total_sites;
  const items = [
    { label: 'Bandwidth (Grafana)', value: coverage.has_bandwidth },
    { label: 'Link availability', value: coverage.has_availability },
    { label: 'Circuits (NetBox)', value: coverage.has_circuits },
    { label: 'RTT / latency', value: coverage.has_rtt },
    { label: 'Packet loss', value: coverage.has_loss },
    { label: 'DHCP user count', value: coverage.has_dhcp },
    { label: 'Jitter', value: coverage.has_jitter },
    { label: 'Full ETU (all metrics)', value: coverage.full_data },
  ];

  const data = items.map(i => ({
    name: i.label,
    value: i.value,
    remaining: total - i.value,
  }));

  return (
    <div>
      <ResponsiveContainer width="100%" height={items.length * 36 + 20}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 0, right: 60, bottom: 0, left: 150 }}
          barSize={14}
        >
          <XAxis type="number" domain={[0, total]} hide />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fill: 'var(--color-text-body)', fontSize: 12, fontFamily: 'DM Sans' }}
            width={140}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--color-bg-surface)',
              border: '1px solid var(--color-border)',
              fontSize: 12,
            }}
            formatter={(value: number, name: string) => [
              `${value} / ${total}`,
              name === 'value' ? 'Available' : 'Missing',
            ]}
          />
          <Bar dataKey="value" stackId="a" fill="var(--color-green)" radius={0}>
            {data.map((entry, i) => (
              <Cell key={i} fill="var(--color-green)" />
            ))}
          </Bar>
          <Bar dataKey="remaining" stackId="a" fill="var(--color-bg-highlight)" radius={0}>
            {data.map((entry, i) => (
              <Cell key={i} fill="var(--color-bg-highlight)" />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {/* Count labels overlaid on right side */}
      <div className="space-y-0">
        {items.map((item, i) => (
          <div
            key={item.label}
            className="flex justify-end text-data text-xs text-text-muted"
            style={{
              height: '36px',
              alignItems: 'center',
              marginTop: i === 0 ? `-${items.length * 36 + 20}px` : '0',
              paddingRight: '4px',
            }}
          >
            {item.value} / {total}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Connectivity() {
  const { data, isLoading } = useConnectivity();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [activeGrades, setActiveGrades] = useState<Set<string> | null>(null);

  const toggle = (code: string) =>
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });

  if (isLoading) {
    return <div className="text-text-muted p-4">Loading connectivity data...</div>;
  }

  if (!data || data.sites.length === 0) {
    return (
      <div className="max-w-4xl mx-auto p-4">
        <h1 className="text-heading mb-2">Connectivity quality</h1>
        <p className="text-text-muted">
          No connectivity data available. Run the pipeline with Grafana and NetBox
          sources to generate ETU scores.
        </p>
      </div>
    );
  }

  const { sites, summary, coverage } = data;

  const toggleGrade = (grade: string) =>
    setActiveGrades(prev => {
      if (prev === null) {
        // First click: show only this grade
        return new Set([grade]);
      }
      const next = new Set(prev);
      if (next.has(grade)) {
        next.delete(grade);
        // If all deselected, reset to show all
        return next.size === 0 ? null : next;
      }
      next.add(grade);
      // If all grades selected, reset to null (show all)
      const allGrades = Object.keys(summary.by_grade);
      return next.size === allGrades.length ? null : next;
    });

  const filteredSites = activeGrades
    ? sites.filter(s => activeGrades.has(s.grade))
    : sites;

  return (
    <div className="max-w-[1440px] mx-auto p-4 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-heading">
          Connectivity quality — Effective Throughput per User
        </h1>
        <p className="text-small text-text-muted mt-1">
          Sites ranked by user experience score — lower scores need attention first.{' '}
          {summary.scored_sites} of {summary.total_sites} field sites scored
          ({Math.round(summary.avg_completeness * 100)}% avg data completeness).
        </p>
      </div>

      {/* ETU explainer */}
      <div className="bg-bg-surface border border-border p-4 space-y-2">
        <p className="text-label">What is ETU?</p>
        <p className="text-small text-text-body">
          <strong>Effective Throughput per User</strong> estimates real per-user
          bandwidth using the{' '}
          <span className="text-text-primary font-semibold">Mathis TCP throughput model</span>:
        </p>
        <p className="text-data text-sm text-text-primary text-center py-1">
          Throughput = (MSS / RTT) &times; (C / &radic;loss) &times; 8
        </p>
        <p className="text-small text-text-muted">
          Each link's theoretical maximum is capped at its contracted capacity,
          then divided across active users. Penalties for jitter, availability,
          and a bonus for provider diversity produce the final 0–100 score on a
          log scale (0.05 Mbps = 0, 5 Mbps = 100). Where measurements are
          missing, conservative estimates are used and flagged.
        </p>
      </div>

      {/* Grade summary pills — click to filter */}
      <div className="flex gap-3 flex-wrap">
        {Object.entries(summary.by_grade).map(([grade, count]) => {
          const isActive = activeGrades === null || activeGrades.has(grade);
          return (
            <button
              key={grade}
              type="button"
              onClick={() => toggleGrade(grade)}
              className="flex items-center gap-2 border px-3 py-1.5 cursor-pointer transition-opacity"
              style={{
                backgroundColor: isActive ? 'var(--color-bg-surface)' : 'var(--color-bg-base)',
                borderColor: isActive ? gradeColor(grade) : 'var(--color-border)',
                opacity: isActive ? 1 : 0.4,
              }}
            >
              <span
                className="w-2 h-2"
                style={{ backgroundColor: gradeColor(grade) }}
              />
              <span className="text-data text-sm">{grade}</span>
              <span className="text-data text-sm text-text-muted">{count}</span>
            </button>
          );
        })}
      </div>

      {/* Sites table */}
      <div className="bg-bg-surface border border-border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-bg-elevated">
                <th className="text-label py-2.5 px-3 w-10">#</th>
                <th className="text-label py-2.5 px-3">Site</th>
                <th className="text-label py-2.5 px-3">Score</th>
                <th className="text-label py-2.5 px-3">Grade</th>
                <th className="text-label py-2.5 px-3">ETU/user</th>
                <th className="text-label py-2.5 px-3">Users</th>
                <th className="text-label py-2.5 px-3">Links</th>
                <th className="text-label py-2.5 px-3">Limiting factor</th>
                <th className="text-label py-2.5 px-3">Completeness</th>
              </tr>
            </thead>
            <tbody>
              {filteredSites.map((site, i) => (
                <>
                  <tr
                    key={site.site_code}
                    className="border-t border-border hover:bg-bg-elevated cursor-pointer transition-colors"
                    onClick={() => toggle(site.site_code)}
                  >
                    <td className="py-2 px-3 text-data text-sm text-text-muted">
                      {i + 1}
                    </td>
                    <td className="py-2 px-3">
                      <span className="text-data text-sm text-text-primary">
                        {site.site_code}
                      </span>
                      <span className="text-data text-xs text-text-muted ml-2">
                        {site.country}
                      </span>
                    </td>
                    <td className="py-2 px-3">
                      <span
                        className="text-data text-sm font-semibold"
                        style={{ color: scoreColor(site.score) }}
                      >
                        {site.score}
                      </span>
                    </td>
                    <td className="py-2 px-3">
                      <span
                        className="text-data text-xs px-1.5 py-0.5 border"
                        style={{
                          color: gradeColor(site.grade),
                          borderColor: gradeColor(site.grade),
                        }}
                      >
                        {site.grade}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-data text-sm">
                      {site.etu_mbps < 0.01
                        ? `${(site.etu_mbps * 1000).toFixed(0)} kbps`
                        : `${site.etu_mbps.toFixed(2)} Mbps`}
                    </td>
                    <td className="py-2 px-3 text-data text-sm">
                      {site.num_users}
                      {site.num_users_source === 'default' && (
                        <span className="text-xs text-text-muted ml-1 italic">
                          est.
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-data text-sm">
                      {site.num_links}
                    </td>
                    <td className="py-2 px-3 text-data text-sm text-text-muted">
                      {site.limiting_factor}
                    </td>
                    <td className="py-2 px-3">
                      <CompletenessBar value={site.data_completeness} />
                    </td>
                  </tr>
                  {expanded.has(site.site_code) && (
                    <ExpandedRow
                      key={`${site.site_code}-expanded`}
                      site={site}
                    />
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Data coverage */}
      <div className="bg-bg-surface border border-border p-5">
        <h2 className="text-label mb-1">
          Data coverage — what's needed for full ETU scoring
        </h2>
        <p className="text-small text-text-muted mb-4">
          Metrics available across {coverage.total_sites} field sites
        </p>
        <CoverageChart coverage={coverage} />

        <div className="mt-5 pt-4 border-t border-border">
          <p className="text-label text-xs mb-2">To improve coverage:</p>
          <ul className="text-small text-text-muted space-y-1 list-disc list-inside">
            <li>
              RTT + loss: requires blackbox exporter or SNMP latency metrics in
              Prometheus for each site
            </li>
            <li>
              DHCP: requires DhcpHighDHCPAddressUsageByScope alert or a DHCP
              scope size metric in Prometheus
            </li>
            <li>
              Jitter: requires probe_duration_seconds stddev calculation —
              available once blackbox exporter access is confirmed
            </li>
            <li>
              Circuits: {coverage.total_sites - coverage.has_circuits} sites
              missing from NetBox — populate via /api/dcim/sites/ and
              /api/circuits/circuits/
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
