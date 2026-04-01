import { AlertTriangle, TrendingUp, TrendingDown } from 'lucide-react';
import type { Alert, DeltaAlert } from '../api/client';

export function PrecursorBanner({ alert }: { alert: Alert }) {
  return (
    <div className="bg-[#F78C6C20] border-l-4 border-orange rounded-r-lg p-4 mb-3">
      <div className="flex items-start gap-3">
        <AlertTriangle className="text-orange shrink-0 mt-0.5" size={18} />
        <div>
          <span className="text-orange font-semibold text-sm font-mono">PRECURSOR DETECTED</span>
          <p className="text-sm text-text-primary mt-1">{alert.message}</p>
          <div className="flex gap-2 mt-2">
            {alert.delegations_at_risk.map((d) => (
              <span key={d} className="font-mono text-xs bg-bg-highlight text-text-body px-2 py-0.5 rounded">
                {d}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function DeltaBanner({ alert }: { alert: DeltaAlert }) {
  const isEscalation = alert.direction === 'escalation';
  return (
    <div className={`${isEscalation ? 'bg-[#FF537020] border-error' : 'bg-[#C3E88D20] border-green'} border-l-4 rounded-r-lg p-4 mb-3`}>
      <div className="flex items-center gap-3">
        {isEscalation
          ? <TrendingUp className="text-error shrink-0" size={18} />
          : <TrendingDown className="text-green shrink-0" size={18} />}
        <div>
          <span className={`font-semibold text-sm font-mono ${isEscalation ? 'text-error' : 'text-green'}`}>
            {isEscalation ? 'ESCALATION' : 'DE-ESCALATION'}
          </span>
          <span className="text-sm text-text-primary ml-2">
            {alert.country}: {alert.old_score.toFixed(1)} → {alert.new_score.toFixed(1)}
            <span className={`ml-1 font-mono ${isEscalation ? 'text-error' : 'text-green'}`}>
              ({alert.delta > 0 ? '+' : ''}{alert.delta.toFixed(1)})
            </span>
          </span>
          {alert.primary_driver && (
            <p className="text-xs text-text-muted mt-1">Driven by: {alert.primary_driver}</p>
          )}
        </div>
      </div>
    </div>
  );
}
