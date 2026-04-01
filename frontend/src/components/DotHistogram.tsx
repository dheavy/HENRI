import { useState, useCallback } from 'react';

const REGION_DATA = [
  { region: 'AFRICA East', months: [420, 380, 350, 400, 390], color: '#D83C3B' },
  { region: 'AFRICA West', months: [280, 300, 270, 290, 310], color: '#82AAFF' },
  { region: 'AMERICAS', months: [80, 90, 85, 75, 95], color: '#A8C97A' },
  { region: 'ASIA', months: [200, 210, 190, 220, 215], color: '#D88A6C' },
  { region: 'EURASIA', months: [70, 65, 80, 75, 60], color: '#C792EA' },
  { region: 'NAME', months: [150, 170, 160, 180, 165], color: '#89DDFF' },
];

const MONTH_LABELS = ['Nov', 'Dec', 'Jan', 'Feb', 'Mar'];
const DOTS_PER_INCIDENT = 50;
const DOT_R = 4;
const DOT_GAP = 2;
const DOT_STEP = DOT_R * 2 + DOT_GAP; // 10px per dot vertically
const COL_WIDTH = 80;
const SVG_W = COL_WIDTH * 5;
const LABEL_Y = 198;

export default function DotHistogram() {
  const [hovered, setHovered] = useState<string | null>(null);

  const handleEnter = useCallback((region: string) => setHovered(region), []);
  const handleLeave = useCallback(() => setHovered(null), []);

  // Pre-compute max height to size viewBox
  let maxDots = 0;
  for (let m = 0; m < 5; m++) {
    let total = 0;
    for (const r of REGION_DATA) {
      total += Math.round(r.months[m] / DOTS_PER_INCIDENT);
    }
    maxDots = Math.max(maxDots, total);
  }
  const chartH = maxDots * DOT_STEP + 20;
  const svgH = chartH + 20; // room for labels

  return (
    <svg viewBox={`0 0 ${SVG_W} ${svgH}`} width="100%" height="100%">
      {Array.from({ length: 5 }, (_, monthIdx) => {
        const cx = monthIdx * COL_WIDTH + COL_WIDTH / 2;
        let dotIdx = 0;

        return (
          <g key={monthIdx}>
            {REGION_DATA.map((r) => {
              const dotCount = Math.round(r.months[monthIdx] / DOTS_PER_INCIDENT);
              const dots = Array.from({ length: dotCount }, (_, d) => {
                const currentDot = dotIdx;
                dotIdx++;
                const cy = chartH - (currentDot * DOT_STEP + DOT_R);
                return (
                  <circle
                    key={`${r.region}-${d}`}
                    cx={cx}
                    cy={cy}
                    r={DOT_R}
                    fill={r.color}
                    opacity={hovered === null || hovered === r.region ? 1 : 0.3}
                    className="transition-opacity duration-150"
                    onMouseEnter={() => handleEnter(r.region)}
                    onMouseLeave={handleLeave}
                  />
                );
              });
              return dots;
            })}
            <text
              x={cx}
              y={LABEL_Y}
              textAnchor="middle"
              fill="#9A9DA6"
              fontSize="10"
              fontFamily="Noto Sans, sans-serif"
            >
              {MONTH_LABELS[monthIdx]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
