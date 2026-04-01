import { useState } from 'react';
import { useDelegations } from '../hooks/useApi';
import { Search, Radio } from 'lucide-react';
import clsx from 'clsx';
import type { Delegation } from '../api/client';

const REGIONS = ['All', 'AFRICA East', 'AFRICA West', 'AMERICAS', 'ASIA', 'EURASIA', 'NAME', 'HQ'];

function DelegationCard({ d }: { d: Delegation }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-surface rounded-lg border border-border p-4 hover:border-border/80 transition-colors cursor-pointer"
      onClick={() => setExpanded(!expanded)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-mono font-bold text-sm">{d.site_code}</span>
          <span className="text-xs text-text-secondary">{d.country}</span>
          <span className="text-xs bg-surface-hover px-2 py-0.5 rounded border border-border">{d.region || 'Unknown'}</span>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="font-mono">{d.incident_count_30d} <span className="text-text-secondary">incidents</span></span>
          {d.sitedown_count_30d > 0 && (
            <span className="font-mono text-red-400">{d.sitedown_count_30d} <span className="text-text-secondary">down</span></span>
          )}
        </div>
      </div>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border space-y-3">
          {d.dominant_alert !== 'N/A' && (
            <p className="text-xs text-text-secondary">Dominant alert: <span className="text-text-primary">{d.dominant_alert}</span></p>
          )}

          {d.sub_sites.length > 0 && (
            <div>
              <p className="text-xs text-text-secondary mb-1">Sub-sites:</p>
              <div className="flex gap-1 flex-wrap">
                {d.sub_sites.map((s) => (
                  <span key={s} className="font-mono text-xs bg-[#0a0a0a] px-1.5 py-0.5 rounded border border-border/50">{s}</span>
                ))}
              </div>
            </div>
          )}

          {d.circuits.length > 0 && (
            <div>
              <p className="text-xs text-text-secondary mb-1">Circuits:</p>
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-text-secondary">
                    <th className="text-left pb-1">CID</th>
                    <th className="text-left pb-1">Provider</th>
                    <th className="text-right pb-1">Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {d.circuits.map((c) => (
                    <tr key={c.cid} className="border-t border-border/30">
                      <td className="py-1 font-mono">{c.cid}</td>
                      <td className="py-1">{c.provider}</td>
                      <td className="py-1 text-right font-mono">{c.commit_rate_fmt || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Delegations() {
  const [search, setSearch] = useState('');
  const [region, setRegion] = useState('All');

  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (region !== 'All') params.set('region', region);

  const { data, isLoading } = useDelegations(params.toString());

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold flex items-center gap-2">
        <Radio size={24} className="text-accent" /> Delegation Inventory
      </h2>

      {/* Search + filter */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary" />
          <input
            type="text"
            placeholder="Search by site code, country..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-surface border border-border rounded-lg pl-9 pr-3 py-2 text-sm
              placeholder:text-text-secondary focus:outline-none focus:border-accent transition-colors"
          />
        </div>
        <div className="flex gap-1">
          {REGIONS.map((r) => (
            <button key={r} onClick={() => setRegion(r)}
              className={clsx('text-xs px-3 py-1.5 rounded transition-colors',
                region === r ? 'bg-accent text-white' : 'bg-surface text-text-secondary hover:text-text-primary border border-border'
              )}>
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* Count */}
      <p className="text-sm text-text-secondary">
        {data?.total ?? 0} delegations{search && ` matching "${search}"`}{region !== 'All' && ` in ${region}`}
      </p>

      {/* Grid */}
      {isLoading ? (
        <p className="text-text-secondary text-sm">Loading...</p>
      ) : (
        <div className="space-y-2">
          {data?.delegations.map((d) => <DelegationCard key={d.site_code} d={d} />)}
        </div>
      )}
    </div>
  );
}
