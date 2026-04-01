import { useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import type { Country } from '../api/client';

const TIER_BG: Record<string, string> = {
  high: 'bg-red-950/40',
  medium: 'bg-orange-950/30',
  low: 'bg-yellow-950/20',
  minimal: 'bg-green-950/20',
};

const TIER_BADGE: Record<string, string> = {
  high: 'bg-risk-high text-red-900',
  medium: 'bg-risk-medium text-orange-900',
  low: 'bg-risk-low text-yellow-900',
  minimal: 'bg-risk-minimal text-green-900',
};

export default function RiskTable({ countries }: { countries: Country[] }) {
  const navigate = useNavigate();

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-text-secondary uppercase tracking-wider border-b border-border">
            <th className="pb-3 pr-4">#</th>
            <th className="pb-3 pr-4">Country</th>
            <th className="pb-3 pr-4 text-right">Risk</th>
            <th className="pb-3 pr-4 text-right">ACLED</th>
            <th className="pb-3 pr-4 text-right">Fatalities</th>
            <th className="pb-3 pr-4 text-right">IODA</th>
            <th className="pb-3 pr-4 text-right">CF</th>
            <th className="pb-3 pr-4 text-right">SiteDown</th>
            <th className="pb-3">Delegations</th>
          </tr>
        </thead>
        <tbody>
          {countries.map((c, i) => (
            <tr
              key={c.iso2}
              onClick={() => navigate(`/country/${c.iso2}`)}
              className={clsx(
                'border-b border-border/50 cursor-pointer transition-colors hover:bg-surface-hover',
                TIER_BG[c.risk_tier]
              )}
            >
              <td className="py-2.5 pr-4 text-text-secondary font-mono text-xs">{i + 1}</td>
              <td className="py-2.5 pr-4 font-medium">{c.name}</td>
              <td className="py-2.5 pr-4 text-right">
                <span className={clsx('text-xs font-bold px-2 py-0.5 rounded', TIER_BADGE[c.risk_tier])}>
                  {c.risk_score.toFixed(1)}
                </span>
              </td>
              <td className="py-2.5 pr-4 text-right font-mono">{c.acled_events.toLocaleString()}</td>
              <td className="py-2.5 pr-4 text-right font-mono">{c.acled_fatalities.toLocaleString()}</td>
              <td className="py-2.5 pr-4 text-right font-mono">{c.ioda_score ? c.ioda_score.toLocaleString() : '—'}</td>
              <td className="py-2.5 pr-4 text-right font-mono">{c.cf_outages || '—'}</td>
              <td className="py-2.5 pr-4 text-right font-mono">{c.snow_sitedown || '—'}</td>
              <td className="py-2.5">
                <div className="flex gap-1 flex-wrap">
                  {c.delegations.slice(0, 4).map((d) => (
                    <span key={d} className="font-mono text-xs bg-surface px-1.5 py-0.5 rounded border border-border">
                      {d}
                    </span>
                  ))}
                  {c.delegations.length > 4 && (
                    <span className="text-xs text-text-secondary">+{c.delegations.length - 4}</span>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
