import { useState, useCallback } from 'react';

interface SurgePoint {
  date: string;
  score: number;
  any_precursor: boolean;
}

interface TooltipState {
  x: number;
  y: number;
  surge: SurgePoint;
}

const SVG_W = 600;
const SVG_H = 120;
const BASELINE_Y = 110;
const TOP_MARGIN = 10;

export default function SurgePulse({ surges }: { surges: SurgePoint[] }) {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const now = Date.now();
  const ninetyDaysAgo = now - 90 * 24 * 3600_000;

  // Filter to last 90 days and sort by date
  const filtered = surges
    .filter((s) => new Date(s.date).getTime() >= ninetyDaysAgo)
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

  const maxScore = Math.max(1, ...filtered.map((s) => s.score));

  function toX(dateStr: string): number {
    const t = new Date(dateStr).getTime();
    return ((t - ninetyDaysAgo) / (now - ninetyDaysAgo)) * SVG_W;
  }

  function toY(score: number): number {
    const normalized = score / maxScore;
    return BASELINE_Y - normalized * (BASELINE_Y - TOP_MARGIN);
  }

  function buildPolyline(points: SurgePoint[]): string {
    if (points.length === 0) return '';
    const segments: string[] = [];
    for (const p of points) {
      const x = toX(p.date);
      const y = toY(p.score);
      segments.push(`${x},${BASELINE_Y}`, `${x},${y}`, `${x},${BASELINE_Y}`);
    }
    return segments.join(' ');
  }

  const precursorSurges = filtered.filter((s) => s.any_precursor);
  const nonPrecursorSurges = filtered.filter((s) => !s.any_precursor);

  const precursorLine = buildPolyline(precursorSurges);
  const nonPrecursorLine = buildPolyline(nonPrecursorSurges);

  const handleMouseEnter = useCallback(
    (surge: SurgePoint, event: React.MouseEvent<SVGCircleElement>) => {
      const rect = (event.currentTarget.closest('svg') as SVGSVGElement).getBoundingClientRect();
      const svgX = event.clientX - rect.left;
      const svgY = event.clientY - rect.top;
      setTooltip({ x: svgX, y: svgY, surge });
    },
    [],
  );

  const handleMouseLeave = useCallback(() => {
    setTooltip(null);
  }, []);

  return (
    <div className="relative w-full h-full">
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        preserveAspectRatio="none"
      >
        {/* Non-precursor spikes (gray) */}
        {nonPrecursorLine && (
          <polyline
            points={nonPrecursorLine}
            fill="none"
            stroke="#5C5F66"
            strokeWidth="1.5"
          />
        )}

        {/* Precursor spikes (cyan) */}
        {precursorLine && (
          <polyline
            points={precursorLine}
            fill="none"
            stroke="#89DDFF"
            strokeWidth="1.5"
          />
        )}

        {/* Interactive hit targets */}
        {filtered.map((s, i) => (
          <circle
            key={i}
            cx={toX(s.date)}
            cy={toY(s.score)}
            r={6}
            fill="transparent"
            className="cursor-pointer"
            onMouseEnter={(e) => handleMouseEnter(s, e)}
            onMouseLeave={handleMouseLeave}
          />
        ))}

        {/* "Now" marker */}
        <line
          x1={SVG_W}
          y1={0}
          x2={SVG_W}
          y2={SVG_H}
          stroke="#5C5F66"
          strokeWidth="0.5"
          strokeDasharray="3 2"
        />
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
          <p className="text-text-body">{tooltip.surge.date}</p>
          <p className="text-text-muted">
            Score: <span className="text-text-primary font-mono">{tooltip.surge.score}</span>
          </p>
          <p className={tooltip.surge.any_precursor ? 'text-[#89DDFF]' : 'text-text-muted'}>
            {tooltip.surge.any_precursor ? 'Precursor detected' : 'No precursor'}
          </p>
        </div>
      )}
    </div>
  );
}
