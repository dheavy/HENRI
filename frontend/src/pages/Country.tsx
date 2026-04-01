import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import clsx from 'clsx';
import { useCountryDetail } from '../hooks/useApi';

const TIER_BADGE: Record<string, string> = {
  high: 'bg-risk-high text-red-900',
  medium: 'bg-risk-medium text-orange-900',
  low: 'bg-risk-low text-yellow-900',
  minimal: 'bg-risk-minimal text-green-900',
};

function tier(score: number): string {
  if (score >= 70) return 'high';
  if (score >= 50) return 'medium';
  if (score >= 25) return 'low';
  return 'minimal';
}

interface AcledDay {
  event_date: string;
  events: number;
  fatalities: number;
}

interface SnowIncident {
  delegation: string;
  total_incidents: number;
  sitedown_count: number;
  dominant_alert: string;
}

interface SurgeRow {
  surge_id: number;
  date: string;
  region: string;
  score: number;
  acled_detected: boolean;
  cf_detected: boolean;
  ioda_detected: boolean;
  lead_time_hours: number | null;
}

export default function Country() {
  const { iso2 } = useParams<{ iso2: string }>();
  const { data, isLoading, error } = useCountryDetail(iso2 ?? '');

  if (isLoading) return <div className="text-text-secondary p-8">Loading country data...</div>;
  if (error || !data) return <div className="text-red-400 p-8">Country not found</div>;

  const country = data.country as Record<string, unknown> | undefined;
  if (!country) return <div className="text-red-400 p-8">No data available</div>;

  const name = country.name as string;
  const score = (country.risk_score as number) ?? 0;
  const t = tier(score);
  const trend = country.acled_trend as string;
  const delegations = (country.delegations as string[]) ?? [];
  const acledTimeline = (data.acled_timeline as AcledDay[]) ?? [];
  const snowIncidents = (data.servicenow_incidents as SnowIncident[]) ?? [];
  const surges = (data.surges as SurgeRow[]) ?? [];

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Back link */}
      <Link to="/" className="inline-flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary transition-colors">
        <ArrowLeft size={16} /> Back to dashboard
      </Link>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">{name}</h2>
          <div className="flex items-center gap-3 mt-1">
            <span className={clsx('text-xs font-bold px-2 py-0.5 rounded', TIER_BADGE[t])}>
              {score.toFixed(1)} — {t}
            </span>
            <span className="text-sm text-text-secondary flex items-center gap-1">
              {trend === 'increasing' && <><TrendingUp size={14} className="text-red-400" /> Increasing</>}
              {trend === 'decreasing' && <><TrendingDown size={14} className="text-green-400" /> Decreasing</>}
              {trend === 'stable' && <><Minus size={14} className="text-text-secondary" /> Stable</>}
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          {delegations.map((d) => (
            <Link key={d} to={`/delegations`}
              className="font-mono text-xs bg-surface border border-border px-2 py-1 rounded hover:border-accent transition-colors">
              {d}
            </Link>
          ))}
        </div>
      </div>

      {/* Signal cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'ACLED Events (30d)', value: country.acled_events as number },
          { label: 'ACLED Fatalities', value: country.acled_fatalities as number },
          { label: 'IODA Score', value: country.ioda_score as number },
          { label: 'SiteDown Events', value: country.snow_sitedown as number },
        ].map(({ label, value }) => (
          <div key={label} className="bg-surface rounded-lg border border-border p-4">
            <p className="text-xs text-text-secondary uppercase tracking-wider">{label}</p>
            <p className="text-2xl font-bold font-mono">{(value ?? 0).toLocaleString()}</p>
          </div>
        ))}
      </div>

      {/* ACLED timeline chart */}
      {acledTimeline.length > 0 && (
        <div className="bg-surface rounded-lg border border-border p-4">
          <h3 className="text-sm font-medium mb-4">ACLED Conflict Events — Daily (last 90 days)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={acledTimeline}>
              <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
              <XAxis dataKey="event_date" tick={{ fontSize: 10, fill: '#737373' }}
                tickFormatter={(d: string) => d.slice(5)} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10, fill: '#737373' }} />
              <Tooltip contentStyle={{ background: '#141414', border: '1px solid #262626', borderRadius: 8 }}
                labelStyle={{ color: '#e5e5e5' }} />
              <Bar dataKey="events" fill="#D52B1E" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ServiceNow incidents */}
      {snowIncidents.length > 0 && (
        <div className="bg-surface rounded-lg border border-border p-4">
          <h3 className="text-sm font-medium mb-4">ServiceNow Incidents by Delegation</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-text-secondary uppercase tracking-wider border-b border-border">
                <th className="pb-2">Delegation</th>
                <th className="pb-2 text-right">Total</th>
                <th className="pb-2 text-right">SiteDown</th>
                <th className="pb-2">Dominant Alert</th>
              </tr>
            </thead>
            <tbody>
              {snowIncidents.map((inc) => (
                <tr key={inc.delegation} className="border-b border-border/50">
                  <td className="py-2 font-mono">{inc.delegation}</td>
                  <td className="py-2 text-right font-mono">{inc.total_incidents}</td>
                  <td className="py-2 text-right font-mono">{inc.sitedown_count}</td>
                  <td className="py-2 text-xs text-text-secondary">{inc.dominant_alert}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Surge history */}
      {surges.length > 0 && (
        <div className="bg-surface rounded-lg border border-border p-4">
          <h3 className="text-sm font-medium mb-4">Surge Events Affecting This Country</h3>
          <div className="space-y-2">
            {surges.map((s) => (
              <div key={s.surge_id} className="flex items-center justify-between p-3 rounded-lg bg-[#0a0a0a] border border-border/50">
                <div>
                  <span className="text-sm font-mono">{s.date}</span>
                  <span className="text-xs text-text-secondary ml-3">{s.region}</span>
                </div>
                <div className="flex items-center gap-3">
                  {s.acled_detected && <span className="text-xs bg-red-950 text-red-300 px-2 py-0.5 rounded">ACLED</span>}
                  {s.ioda_detected && <span className="text-xs bg-blue-950 text-blue-300 px-2 py-0.5 rounded">IODA</span>}
                  {s.cf_detected && <span className="text-xs bg-orange-950 text-orange-300 px-2 py-0.5 rounded">CF</span>}
                  {s.lead_time_hours != null && (
                    <span className={clsx('text-xs font-mono px-2 py-0.5 rounded',
                      s.lead_time_hours > 48 ? 'bg-green-950 text-green-300' :
                      s.lead_time_hours > 12 ? 'bg-yellow-950 text-yellow-300' :
                      'bg-red-950 text-red-300'
                    )}>
                      {Math.round(s.lead_time_hours)}h
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
