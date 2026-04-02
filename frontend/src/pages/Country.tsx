import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import AnimatedNumber from '../components/AnimatedNumber';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import clsx from 'clsx';
import { useCountryDetail } from '../hooks/useApi';

const TIER_BADGE: Record<string, string> = {
  high: 'bg-[#F0717844] text-red',
  medium: 'bg-[#F78C6C44] text-orange',
  low: 'bg-[#FFCB6B33] text-yellow',
  minimal: 'bg-[#C3E88D33] text-green',
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

  if (isLoading) return <div className="text-text-muted p-8">Loading country data...</div>;
  if (error || !data) return <div className="text-red p-8">Country not found</div>;

  const country = data.country as Record<string, unknown> | undefined;
  if (!country) return <div className="text-red p-8">No data available</div>;

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
      <Link to="/" className="inline-flex items-center gap-2 text-sm text-text-muted hover:text-text-primary transition-colors">
        <ArrowLeft size={16} /> Back to dashboard
      </Link>

      {/* Header */}
      <p className="text-sm text-text-muted">
        Country drill-down: ACLED (Armed Conflict Location &amp; Event Data) conflict timeline,
        IODA (Internet Outage Detection &amp; Analysis) signals, ServiceNow incidents
        by delegation, and historical surge events with precursor analysis.
      </p>

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">{name}</h2>
          <div className="flex items-center gap-3 mt-1">
            <span className={clsx('text-xs font-bold px-2 py-0.5 rounded', TIER_BADGE[t])}>
              {score.toFixed(1)} — {t}
            </span>
            <span className="text-sm text-text-muted flex items-center gap-1">
              {trend === 'increasing' && <><TrendingUp size={14} className="text-red" /> Increasing</>}
              {trend === 'decreasing' && <><TrendingDown size={14} className="text-green" /> Decreasing</>}
              {trend === 'stable' && <><Minus size={14} className="text-text-muted" /> Stable</>}
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          {delegations.map((d) => (
            <Link key={d} to={`/delegations`}
              className="font-mono text-xs bg-bg-surface border border-border px-2 py-1 rounded hover:border-accent transition-colors">
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
          <div key={label} className="bg-bg-surface rounded-lg border border-border p-4">
            <p className="text-label">{label}</p>
            <AnimatedNumber value={value ?? 0} className="text-data-display mt-1 block" />
          </div>
        ))}
      </div>

      {/* ACLED timeline chart */}
      {acledTimeline.length > 0 && (
        <div className="bg-bg-surface rounded-lg border border-border p-4">
          <h3 className="text-sm font-medium mb-4">ACLED Conflict Events — Daily (last 90 days)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={acledTimeline}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1F2233" />
              <XAxis dataKey="event_date" tick={{ fontSize: 10, fill: '#717CB4' }}
                tickFormatter={(d: string) => d.slice(5)} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10, fill: '#717CB4' }} />
              <Tooltip contentStyle={{ background: '#181A1F', border: '1px solid #1F2233', borderRadius: 8, color: '#EEFFFF' }}
                labelStyle={{ color: '#e5e5e5' }} />
              <Bar dataKey="events" fill="#C792EA" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ServiceNow incidents */}
      {snowIncidents.length > 0 && (
        <div className="bg-bg-surface rounded-lg border border-border p-4">
          <h3 className="text-sm font-medium mb-4">ServiceNow Incidents by Delegation</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-text-muted uppercase tracking-wider border-b border-border">
                <th className="pb-2">Delegation</th>
                <th className="pb-2">Total</th>
                <th className="pb-2">Site Down</th>
                <th className="pb-2 pl-4">Dominant Alert</th>
              </tr>
            </thead>
            <tbody>
              {snowIncidents.map((inc) => (
                <tr key={inc.delegation} className="border-b border-border/30">
                  <td className="py-2 font-mono">{inc.delegation}</td>
                  <td className="py-2 font-mono">{inc.total_incidents}</td>
                  <td className="py-2 font-mono">{inc.sitedown_count}</td>
                  <td className="py-2 pl-4 text-xs text-text-muted">{inc.dominant_alert}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Surge history */}
      {surges.length > 0 && (
        <div className="bg-bg-surface rounded-lg border border-border p-4">
          <h3 className="text-sm font-medium">Surge Events Affecting This Country</h3>
          <p className="text-xs text-text-muted mt-1 mb-4">
            Source badges (ACLED, IODA, CF) indicate which external signals were detected before the outage.
            The time label shows lead time — how far in advance the warning signal appeared. Surges without
            a time label had no detectable external precursor.
          </p>
          <div className="space-y-2">
            {surges.map((s) => (
              <div key={s.surge_id} className="flex items-center justify-between p-3 rounded-lg bg-bg-base border border-border/30">
                <div>
                  <span className="text-sm font-mono">{s.date}</span>
                  <span className="text-xs text-text-muted ml-3">{s.region}</span>
                </div>
                <div className="flex items-center gap-3">
                  {s.acled_detected && <span className="text-xs bg-[#F0717822] text-red px-2 py-0.5 rounded">ACLED</span>}
                  {s.ioda_detected && <span className="text-xs bg-[#82AAFF22] text-blue px-2 py-0.5 rounded">IODA</span>}
                  {s.cf_detected && <span className="text-xs bg-[#F78C6C22] text-orange px-2 py-0.5 rounded">CF</span>}
                  {s.lead_time_hours != null && (
                    <span className={clsx('text-xs font-mono px-2 py-0.5 rounded',
                      s.lead_time_hours > 48 ? 'bg-[#C3E88D22] text-green' :
                      s.lead_time_hours > 12 ? 'bg-[#FFCB6B22] text-yellow' :
                      'bg-[#F0717822] text-red'
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
