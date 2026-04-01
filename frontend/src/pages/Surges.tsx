import { useState } from 'react';
import { useSurges } from '../hooks/useApi';
import EmptyState from '../components/EmptyState';
import clsx from 'clsx';
import { Zap, Filter } from 'lucide-react';
import type { Surge } from '../api/client';

const REGIONS = ['All', 'AFRICA East', 'AFRICA West', 'AMERICAS', 'ASIA', 'EURASIA', 'NAME'];

function PrecursorDot({ detected, label }: { detected: boolean; label: string }) {
  return (
    <span title={label} className={clsx(
      'inline-block w-2.5 h-2.5 rounded-full',
      detected ? 'bg-green-500' : 'bg-neutral-700'
    )} />
  );
}

function LeadTimeBadge({ hours }: { hours: number | null }) {
  if (hours == null) return <span className="text-text-muted">—</span>;
  const rounded = Math.round(hours);
  return (
    <span className={clsx('font-mono text-xs px-2 py-0.5 rounded',
      hours > 48 ? 'bg-[#C3E88D22] text-green' :
      hours > 12 ? 'bg-[#FFCB6B22] text-yellow' :
      'bg-[#F0717822] text-red'
    )}>
      {rounded}h
    </span>
  );
}

function SurgeRow({ surge }: { surge: Surge }) {
  const [expanded, setExpanded] = useState(false);
  const p = surge.precursors;

  return (
    <>
      <tr onClick={() => setExpanded(!expanded)}
        className={clsx(
          'border-b border-border/30 cursor-pointer transition-colors',
          surge.any_precursor ? 'hover:bg-bg-elevated' : 'hover:bg-bg-elevated opacity-60'
        )}>
        <td className="py-2.5 font-mono text-xs">{surge.date}</td>
        <td className="py-2.5 text-xs">{surge.region}</td>
        <td className="py-2.5">
          <div className="flex gap-1 flex-wrap">
            {surge.delegations.slice(0, 4).map((d) => (
              <span key={d} className="font-mono text-xs bg-bg-surface px-1 py-0.5 rounded border border-border">{d}</span>
            ))}
            {surge.delegations.length > 4 && <span className="text-xs text-text-muted">+{surge.delegations.length - 4}</span>}
          </div>
        </td>
        <td className="py-2.5 text-right font-mono text-xs">{surge.score.toFixed(1)}</td>
        <td className="py-2.5">
          <div className="flex gap-1.5 items-center">
            <PrecursorDot detected={p.acled.detected} label="ACLED" />
            <PrecursorDot detected={p.ioda.detected} label="IODA" />
            <PrecursorDot detected={p.cloudflare.detected} label="Cloudflare" />
            <PrecursorDot detected={p.internal.detected} label="Internal" />
          </div>
        </td>
        <td className="py-2.5 text-right"><LeadTimeBadge hours={surge.lead_time_h} /></td>
      </tr>
      {expanded && (
        <tr className="border-b border-border/30 bg-bg-base">
          <td colSpan={6} className="p-4">
            <div className="grid grid-cols-4 gap-4 text-xs">
              <div>
                <span className="text-text-muted uppercase">ACLED</span>
                {p.acled.detected
                  ? <p className="mt-1">{p.acled.events} events ({p.acled.ratio}x baseline)</p>
                  : <p className="mt-1 text-text-muted">No precursor</p>}
              </div>
              <div>
                <span className="text-text-muted uppercase">IODA</span>
                {p.ioda.detected
                  ? <p className="mt-1">{p.ioda.alerts} alerts</p>
                  : <p className="mt-1 text-text-muted">No precursor</p>}
              </div>
              <div>
                <span className="text-text-muted uppercase">Cloudflare</span>
                {p.cloudflare.detected
                  ? <p className="mt-1">{p.cloudflare.events} outages</p>
                  : <p className="mt-1 text-text-muted">No precursor</p>}
              </div>
              <div>
                <span className="text-text-muted uppercase">Internal (WAN)</span>
                {p.internal.detected
                  ? <p className="mt-1">{p.internal.latency_alerts} latency alerts</p>
                  : <p className="mt-1 text-text-muted">No precursor</p>}
              </div>
            </div>
            <div className="mt-3 text-xs text-text-muted">
              Countries: {surge.countries.join(', ')}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function Surges() {
  const [region, setRegion] = useState('All');
  const [precursorOnly, setPrecursorOnly] = useState(false);

  const params = new URLSearchParams();
  if (region !== 'All') params.set('region', region);
  if (precursorOnly) params.set('has_precursor', 'true');
  params.set('limit', '50');

  const { data, isLoading } = useSurges(params.toString());

  if (!isLoading && (!data?.stats?.total_surges)) {
    return <EmptyState
      title="No surge data"
      message="Precursor analysis requires a pipeline run. Generate reports to analyse surge events and detect external warning signals."
    />;
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold flex items-center gap-2">
        <Zap size={24} className="text-accent" /> Surge Events & Precursor Analysis
      </h2>

      {/* Stats */}
      {data?.stats && (
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-bg-surface rounded-lg border border-border p-4">
            <p className="text-xs text-text-muted uppercase">Total Surges</p>
            <p className="text-2xl font-bold font-mono">{data.stats.total_surges}</p>
          </div>
          <div className="bg-bg-surface rounded-lg border border-border p-4">
            <p className="text-xs text-text-muted uppercase">With Precursors</p>
            <p className="text-2xl font-bold font-mono text-accent">{data.stats.with_external_precursor}</p>
            <p className="text-xs text-text-muted">{data.stats.pct_with_precursor}%</p>
          </div>
          <div className="bg-bg-surface rounded-lg border border-border p-4">
            <p className="text-xs text-text-muted uppercase">Avg Lead Time</p>
            <p className="text-2xl font-bold font-mono">{data.stats.avg_lead_time_hours}h</p>
          </div>
          <div className="bg-bg-surface rounded-lg border border-border p-4">
            <p className="text-xs text-text-muted uppercase">Precursor Legend</p>
            <div className="flex gap-3 mt-2 text-xs">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500" /> Detected</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-neutral-700" /> None</span>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-4">
        <Filter size={16} className="text-text-muted" />
        <div className="flex gap-1">
          {REGIONS.map((r) => (
            <button key={r} onClick={() => setRegion(r)}
              className={clsx('text-xs px-3 py-1.5 rounded transition-colors',
                region === r ? 'bg-accent text-white' : 'bg-bg-surface text-text-muted hover:text-text-primary border border-border'
              )}>
              {r}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs text-text-muted ml-auto cursor-pointer">
          <input type="checkbox" checked={precursorOnly} onChange={(e) => setPrecursorOnly(e.target.checked)}
            className="rounded" />
          Precursor-only
        </label>
      </div>

      {/* Table */}
      <div className="bg-bg-surface rounded-lg border border-border p-4">
        {isLoading ? (
          <p className="text-text-muted text-sm">Loading surges...</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-text-muted uppercase tracking-wider border-b border-border">
                <th className="pb-2">Date</th>
                <th className="pb-2">Region</th>
                <th className="pb-2">Delegations</th>
                <th className="pb-2 text-right">Score</th>
                <th className="pb-2">Precursors</th>
                <th className="pb-2 text-right">Lead Time</th>
              </tr>
            </thead>
            <tbody>
              {data?.surges.map((s) => <SurgeRow key={s.id} surge={s} />)}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
