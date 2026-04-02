import { AlertTriangle, TrendingUp, TrendingDown } from 'lucide-react';
import type { Alert, DeltaAlert } from '../api/client';

export function PrecursorBanner({ alert }: { alert: Alert }) {
  return (
    <div className="bg-[#D88A6C18] border-l-[3px] border-orange p-4 mb-3">
      <div className="flex items-start gap-3">
        <AlertTriangle className="text-orange shrink-0 mt-0.5" size={18} />
        <div>
          <span className="text-label !text-orange">Precursor Detected</span>
          <p className="text-sm text-text-primary mt-1">{alert.message}</p>
          <div className="flex gap-2 mt-2">
            {alert.delegations_at_risk.map((d) => (
              <span key={d} className="text-data bg-bg-highlight px-2 py-0.5 ">
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
      className={`${
        isEscalation ? 'bg-[#D83C3B18] border-red' : 'bg-[#A8C97A18] border-green'
      } border-l-[3px] p-4 mb-3`}
    >
      <div className="flex items-center gap-3">
        {isEscalation ? (
          <TrendingUp className="text-red shrink-0" size={18} />
        ) : (
          <TrendingDown className="text-green shrink-0" size={18} />
        )}
        <div>
          <span className={`text-label ${isEscalation ? '!text-red' : '!text-green'}`}>
            {isEscalation ? 'Escalation' : 'De-escalation'}
          </span>
          <span className="text-sm text-text-primary ml-2">
            {alert.country}: {alert.old_score.toFixed(1)} &rarr; {alert.new_score.toFixed(1)}
            <span className={`ml-1 text-data ${isEscalation ? '!text-red' : '!text-green'}`}>
              ({alert.delta > 0 ? '+' : ''}
              {alert.delta.toFixed(1)})
            </span>
          </span>
          {alert.primary_driver && (
            <p className="text-small mt-1">Driven by: {alert.primary_driver}</p>
          )}
        </div>
      </div>
    </div>
  );
}
