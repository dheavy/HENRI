import { useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import type { Country } from '../api/client';

const TIER_ROW_BG: Record<string, string> = {
  high: 'bg-risk-high',
  medium: 'bg-risk-medium',
  low: 'bg-risk-low',
  minimal: 'bg-risk-minimal',
};

const TIER_BADGE: Record<string, string> = {
  high: 'bg-[#F0717844] text-red',
  medium: 'bg-[#F78C6C44] text-orange',
  low: 'bg-[#FFCB6B33] text-yellow',
  minimal: 'bg-[#C3E88D33] text-green',
};

export default function RiskTable({ countries }: { countries: Country[] }) {
  const navigate = useNavigate();

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-text-comment uppercase tracking-wider border-b border-border">
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
                'border-b border-border/30 cursor-pointer transition-colors hover:bg-bg-elevated',
                TIER_ROW_BG[c.risk_tier]
              )}
            >
              <td className="py-2.5 pr-4 text-text-muted font-mono text-xs">{i + 1}</td>
              <td className="py-2.5 pr-4 text-link font-medium">{c.name}</td>
              <td className="py-2.5 pr-4 text-right">
                <span className={clsx('text-xs font-bold font-mono px-2 py-0.5 rounded', TIER_BADGE[c.risk_tier])}>
                  {c.risk_score.toFixed(1)}
                </span>
              </td>
              <td className="py-2.5 pr-4 text-right font-mono text-text-primary">{c.acled_events.toLocaleString()}</td>
              <td className="py-2.5 pr-4 text-right font-mono text-text-primary">{c.acled_fatalities.toLocaleString()}</td>
              <td className="py-2.5 pr-4 text-right font-mono text-text-primary">{c.ioda_score ? c.ioda_score.toLocaleString() : '—'}</td>
              <td className="py-2.5 pr-4 text-right font-mono text-text-primary">{c.cf_outages || '—'}</td>
              <td className="py-2.5 pr-4 text-right font-mono text-text-primary">{c.snow_sitedown || '—'}</td>
              <td className="py-2.5">
                <div className="flex gap-1 flex-wrap">
                  {c.delegations.slice(0, 4).map((d) => (
                    <span key={d} className="font-mono text-xs bg-bg-highlight text-text-body px-1.5 py-0.5 rounded">
                      {d}
                    </span>
                  ))}
                  {c.delegations.length > 4 && (
                    <span className="text-xs text-text-muted">+{c.delegations.length - 4}</span>
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
