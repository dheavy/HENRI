import { AlertTriangle, TrendingUp, TrendingDown } from 'lucide-react';
import clsx from 'clsx';
import type { Alert, DeltaAlert } from '../api/client';

export function PrecursorBanner({ alert }: { alert: Alert }) {
  return (
    <div className="bg-orange-950/50 border border-orange-800 rounded-lg p-4 mb-3">
      <div className="flex items-start gap-3">
        <AlertTriangle className="text-orange-400 shrink-0 mt-0.5\" size={18} />
        <div>
          <span className="text-orange-300 font-semibold text-sm">PRECURSOR DETECTED</span>
          <p className="text-sm text-text-primary mt-1">{alert.message}</p>
          <div className="flex gap-2 mt-2">
            {alert.delegations_at_risk.map((d) => (
              <span key={d} className="font-mono text-xs bg-orange-900/50 px-2 py-0.5 rounded">
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
    <div
      className={clsx(
        'border rounded-lg p-4 mb-3',
        isEscalation ? 'bg-red-950/50 border-red-800' : 'bg-green-950/50 border-green-800'
      )}
    >
      <div className="flex items-center gap-3">
        {isEscalation ? (
          <TrendingUp className="text-red-400 shrink-0" size={18} />
        ) : (
          <TrendingDown className="text-green-400 shrink-0" size={18} />
        )}
        <div>
          <span
            className={clsx(
              'font-semibold text-sm',
              isEscalation ? 'text-red-300' : 'text-green-300'
            )}
          >
            {isEscalation ? 'ESCALATION' : 'DE-ESCALATION'}
          </span>
          <span className="text-sm text-text-primary ml-2">
            {alert.country}: {alert.old_score.toFixed(1)} → {alert.new_score.toFixed(1)}
            <span className={clsx('ml-1 font-mono', isEscalation ? 'text-red-400' : 'text-green-400')}>
              ({alert.delta > 0 ? '+' : ''}{alert.delta.toFixed(1)})
            </span>
          </span>
          {alert.primary_driver && (
            <p className="text-xs text-text-secondary mt-1">Driven by: {alert.primary_driver}</p>
          )}
        </div>
      </div>
    </div>
  );
}
