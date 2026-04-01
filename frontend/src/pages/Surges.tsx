import { useSurges } from '../hooks/useApi';

export default function Surges() {
  const { data, isLoading } = useSurges('has_precursor=true&limit=30');

  if (isLoading) return <div className="text-text-secondary">Loading surges...</div>;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold">Surge Events & Precursor Analysis</h2>
      <p className="text-text-secondary text-sm">Full interactive view in Phase 3d.</p>
      {data?.stats && (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-surface rounded-lg border border-border p-4">
            <p className="text-xs text-text-secondary uppercase">Total Surges</p>
            <p className="text-2xl font-bold font-mono">{data.stats.total_surges}</p>
          </div>
          <div className="bg-surface rounded-lg border border-border p-4">
            <p className="text-xs text-text-secondary uppercase">With Precursors</p>
            <p className="text-2xl font-bold font-mono">{data.stats.pct_with_precursor}%</p>
          </div>
          <div className="bg-surface rounded-lg border border-border p-4">
            <p className="text-xs text-text-secondary uppercase">Avg Lead Time</p>
            <p className="text-2xl font-bold font-mono">{data.stats.avg_lead_time_hours}h</p>
          </div>
        </div>
      )}
      <div className="bg-surface rounded-lg border border-border p-4 text-sm text-text-secondary">
        {data?.surges.length ?? 0} surges loaded. Interactive table coming in Phase 3d.
      </div>
    </div>
  );
}
