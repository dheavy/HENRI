import { useState, useCallback } from 'react';

interface SourceInfo {
  status: string;
  last_pull: string | null;
}

interface TooltipState {
  x: number;
  y: number;
  name: string;
  status: string;
  lastPull: string | null;
}

const RINGS: { key: string; label: string; r: number; color: string }[] = [
  { key: 'acled', label: 'ACLED', r: 55, color: '#C792EA' },
  { key: 'ioda', label: 'IODA', r: 47, color: '#82AAFF' },
  { key: 'cloudflare', label: 'Cloudflare', r: 39, color: '#89DDFF' },
  { key: 'servicenow', label: 'ServiceNow', r: 31, color: '#8A8D94' },
  { key: 'grafana', label: 'Grafana', r: 23, color: '#8A8D94' },
  { key: 'netbox', label: 'NetBox', r: 15, color: '#8A8D94' },
];

const CX = 60;
const CY = 60;
const STROKE_W = 3;

export default function SourceHealthRings({
  sources,
}: {
  sources: Record<string, SourceInfo>;
}) {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const handleEnter = useCallback(
    (ring: (typeof RINGS)[0], event: React.MouseEvent<SVGCircleElement>) => {
      const svg = event.currentTarget.closest('svg') as SVGSVGElement;
      const rect = svg.getBoundingClientRect();
      const info = sources[ring.key];
      setTooltip({
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
        name: ring.label,
        status: info?.status ?? 'unknown',
        lastPull: info?.last_pull ?? null,
      });
    },
    [sources],
  );

  const handleLeave = useCallback(() => setTooltip(null), []);

  return (
    <div className="relative w-full h-full flex items-center justify-center">
      <svg viewBox="0 0 120 120" width="100%" height="100%">
        {RINGS.map((ring) => {
          const info = sources[ring.key];
          const isOk = info?.status === 'ok';
          const circumference = 2 * Math.PI * ring.r;

          return (
            <circle
              key={ring.key}
              cx={CX}
              cy={CY}
              r={ring.r}
              fill="none"
              stroke={ring.color}
              strokeWidth={STROKE_W}
              strokeLinecap="round"
              strokeDasharray={isOk ? `${circumference}` : '4 4'}
              strokeDashoffset={0}
              opacity={isOk ? 0.9 : 0.35}
              transform={`rotate(-90 ${CX} ${CY})`}
              className="cursor-pointer"
              onMouseEnter={(e) => handleEnter(ring, e)}
              onMouseLeave={handleLeave}
            />
          );
        })}

        {/* Center accent dot */}
        <circle cx={CX} cy={CY} r={3} fill="#D83C3B" />
      </svg>

      {tooltip && (
        <div
          className="absolute pointer-events-none bg-bg-elevated border border-border rounded px-2 py-1 text-xs z-10"
          style={{
            left: tooltip.x + 12,
            top: tooltip.y - 8,
            whiteSpace: 'nowrap',
          }}
        >
          <p className="text-text-body font-medium">{tooltip.name}</p>
          <p className="text-text-muted">
            Status: <span className="text-text-primary">{tooltip.status}</span>
          </p>
          {tooltip.lastPull && (
            <p className="text-text-muted">
              Last pull: {new Date(tooltip.lastPull).toLocaleString()}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
