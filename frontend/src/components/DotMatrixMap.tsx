import { useMemo } from 'react';
import DottedMap from 'dotted-map';
import type { Country } from '../api/client';

// Approximate centroids for ICRC delegation countries (lat, lon)
const CENTROIDS: Record<string, [number, number]> = {
  AF: [33, 65], AZ: [40, 50], BD: [24, 90], BF: [12, -2], BI: [-3, 30],
  BR: [-10, -55], CF: [7, 21], CM: [6, 12], CO: [4, -72], CD: [0, 25],
  CI: [8, -5], DJ: [12, 43], ER: [15, 39], ET: [9, 38], FJ: [-18, 178],
  FR: [46, 2], GE: [42, 44], GH: [8, -2], GN: [11, -10], GT: [16, -90],
  HN: [15, -87], IL: [31, 35], IN: [21, 79], IQ: [33, 44], IR: [32, 53],
  JO: [31, 36], KE: [0, 38], KG: [41, 75], KW: [29, 48], LB: [34, 36],
  LK: [7, 81], LR: [6, -10], ML: [17, -4], MM: [22, 96], MX: [23, -102],
  MZ: [-19, 35], NE: [18, 8], NG: [10, 8], PK: [30, 70], PE: [-10, -76],
  PH: [12, 122], PS: [32, 35], RU: [60, 100], RW: [-2, 30], SD: [15, 30],
  SL: [9, -12], SN: [14, -14], SO: [6, 46], SS: [7, 30], SY: [35, 38],
  TD: [15, 19], TH: [15, 101], TJ: [39, 71], TZ: [-6, 35], UA: [49, 32],
  UG: [1, 32], US: [38, -97], UZ: [41, 65], VE: [8, -66], YE: [15, 48],
  ZM: [-15, 28], ZW: [-20, 30], GB: [54, -2], MY: [4, 102],
};

const TIER_COLORS: Record<string, string> = {
  high: '#D83C3B',
  medium: '#D88A6C',
  low: '#E5C46B',
  minimal: '#A8C97A',
};

function tierFromScore(score: number): string {
  if (score >= 70) return 'high';
  if (score >= 50) return 'medium';
  if (score >= 25) return 'low';
  return 'minimal';
}

interface Props {
  countries: Country[];
}

export default function DotMatrixMap({ countries }: Props) {
  const svgString = useMemo(() => {
    const map = new DottedMap({ height: 60, grid: 'diagonal' });

    for (const c of countries) {
      const coords = CENTROIDS[c.iso2.toUpperCase()];
      if (!coords) continue;
      const tier = tierFromScore(c.risk_score);
      const color = TIER_COLORS[tier] ?? '#5C5F66';
      map.addPin({
        lat: coords[0],
        lng: coords[1],
        svgOptions: { color, radius: 0.5 },
      });
    }

    return map.getSVG({
      radius: 0.22,
      color: '#3A3D44',
      shape: 'circle',
      backgroundColor: 'transparent',
    });
  }, [countries]);

  return (
    <div
      className="w-full h-full flex items-center justify-center"
      dangerouslySetInnerHTML={{ __html: svgString }}
    />
  );
}
