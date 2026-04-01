import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';

interface SurgePoint {
  date: string;
  score: number;
  any_precursor: boolean;
}

interface WeekBucket {
  weekLabel: string;
  withPrecursor: number;
  withoutPrecursor: number;
}

function getISOWeekStart(dateStr: string): string {
  const d = new Date(dateStr);
  const day = d.getUTCDay();
  const diff = d.getUTCDate() - day + (day === 0 ? -6 : 1); // Monday
  const monday = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), diff));
  return monday.toISOString().slice(0, 10);
}

function formatWeekLabel(isoDate: string): string {
  const d = new Date(isoDate);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${months[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

export default function SurgePulse({ surges }: { surges: SurgePoint[] }) {
  const weeklyData = useMemo<WeekBucket[]>(() => {
    const now = Date.now();
    const ninetyDaysAgo = now - 90 * 24 * 3600_000;

    const filtered = surges.filter(
      (s) => new Date(s.date).getTime() >= ninetyDaysAgo,
    );

    const buckets = new Map<string, { withPrecursor: number; withoutPrecursor: number }>();

    for (const s of filtered) {
      const weekStart = getISOWeekStart(s.date);
      const bucket = buckets.get(weekStart) ?? { withPrecursor: 0, withoutPrecursor: 0 };
      if (s.any_precursor) {
        bucket.withPrecursor += 1;
      } else {
        bucket.withoutPrecursor += 1;
      }
      buckets.set(weekStart, bucket);
    }

    return Array.from(buckets.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([weekStart, counts]) => ({
        weekLabel: formatWeekLabel(weekStart),
        withPrecursor: counts.withPrecursor,
        withoutPrecursor: counts.withoutPrecursor,
      }));
  }, [surges]);

  return (
    <div className="w-full">
      <p className="text-label mb-2">Surge activity — last 90 days</p>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={weeklyData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#3A3D44" />
          <XAxis
            dataKey="weekLabel"
            tick={{ fontSize: 10, fontFamily: 'DM Mono, monospace', fill: '#9A9DA6' }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tick={{ fontSize: 10, fontFamily: 'DM Mono, monospace', fill: '#9A9DA6' }}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={{
              background: '#2A2C32',
              border: '1px solid #3A3D44',
              borderRadius: 8,
              color: '#EEFFFF',
            }}
          />
          <Bar
            dataKey="withPrecursor"
            stackId="a"
            fill="#89DDFF"
            name="Had precursors"
            radius={[0, 0, 0, 0]}
          />
          <Bar
            dataKey="withoutPrecursor"
            stackId="a"
            fill="#5C5F66"
            name="No precursors"
            radius={[2, 2, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-2">
        <span className="text-small flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-sm" style={{ background: '#89DDFF' }} />
          Had precursors
        </span>
        <span className="text-small flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-sm" style={{ background: '#5C5F66' }} />
          No precursors
        </span>
      </div>
    </div>
  );
}
