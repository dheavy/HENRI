import { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronUp, TrendingUp, TrendingDown } from 'lucide-react';
import type { Alert, DeltaAlert } from '../api/client';

interface Props {
  alerts: Alert[];
  deltaAlerts: DeltaAlert[];
}

export default function AlertSummary({ alerts, deltaAlerts }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (alerts.length === 0 && deltaAlerts.length === 0) return null;

  const totalCount = alerts.length + deltaAlerts.length;

  // Collect unique countries with alert counts
  const countryCounts = new Map<string, number>();
  for (const a of alerts) {
    countryCounts.set(a.country, (countryCounts.get(a.country) ?? 0) + 1);
  }
  for (const d of deltaAlerts) {
    countryCounts.set(d.country, (countryCounts.get(d.country) ?? 0) + 1);
  }

  // Collect all delegation pills
  const allDelegations = new Set<string>();
  for (const a of alerts) {
    for (const d of a.delegations_at_risk) allDelegations.add(d);
  }

  return (
    <div className="bg-bg-surface border-l-[3px] border-orange p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <AlertTriangle className="text-orange shrink-0" size={18} />
          <div>
            <span className="text-text-primary text-sm font-medium">
              {totalCount} active alert{totalCount !== 1 ? 's' : ''}
            </span>
          </div>
          <span className="text-text-muted text-sm">
            {Array.from(countryCounts.entries()).map(([country, count], i) => (
              <span key={country}>
                {i > 0 && ', '}
                <span className="text-text-primary">{country}</span>
                {count > 1 && <span className="text-text-muted">{'\u00D7'}{count}</span>}
              </span>
            ))}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {allDelegations.size > 0 && (
            <div className="flex gap-1 flex-wrap">
              {Array.from(allDelegations).slice(0, 6).map((d) => (
                <span
                  key={d}
                  className="bg-bg-elevated text-text-primary font-mono text-xs px-2 py-0.5 "
                >
                  {d}
                </span>
              ))}
              {allDelegations.size > 6 && (
                <span className="text-xs text-text-muted">+{allDelegations.size - 6}</span>
              )}
            </div>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-text-muted hover:text-text-primary transition-colors p-1"
            aria-label={expanded ? 'Collapse alerts' : 'Expand alerts'}
          >
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 space-y-2 border-t border-border pt-3">
          {alerts.map((a, i) => (
            <div key={`alert-${i}`} className="flex items-start gap-3">
              <AlertTriangle className="text-orange shrink-0 mt-0.5" size={14} />
              <div>
                <span className="text-label !text-orange">Precursor Detected</span>
                <p className="text-sm text-text-primary mt-0.5">{a.message}</p>
                <div className="flex gap-1 mt-1">
                  {a.delegations_at_risk.map((d) => (
                    <span
                      key={d}
                      className="bg-bg-elevated text-text-primary font-mono text-xs px-2 py-0.5 "
                    >
                      {d}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
          {deltaAlerts.map((d, i) => {
            const isEscalation = d.direction === 'escalation';
            return (
              <div key={`delta-${i}`} className="flex items-center gap-3">
                {isEscalation ? (
                  <TrendingUp className="text-red shrink-0" size={14} />
                ) : (
                  <TrendingDown className="text-green shrink-0" size={14} />
                )}
                <div>
                  <span className={`text-label ${isEscalation ? '!text-red' : '!text-green'}`}>
                    {isEscalation ? 'Escalation' : 'De-escalation'}
                  </span>
                  <span className="text-sm text-text-primary ml-2">
                    {d.country}: {d.old_score.toFixed(1)} &rarr; {d.new_score.toFixed(1)}
                    <span className={`ml-1 text-data ${isEscalation ? '!text-red' : '!text-green'}`}>
                      ({d.delta > 0 ? '+' : ''}{d.delta.toFixed(1)})
                    </span>
                  </span>
                  {d.primary_driver && (
                    <p className="text-small mt-0.5">Driven by: {d.primary_driver}</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
