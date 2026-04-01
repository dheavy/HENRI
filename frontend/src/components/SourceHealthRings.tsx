interface SourceInfo {
  status: string;
  last_pull: string | null;
  metric?: string | null;
}

const SOURCE_META: Record<string, { label: string; color: string }> = {
  servicenow: { label: 'ServiceNow', color: '#A8C97A' },
  grafana: { label: 'Grafana', color: '#A8C97A' },
  netbox: { label: 'NetBox', color: '#A8C97A' },
  acled: { label: 'ACLED', color: '#C792EA' },
  ioda: { label: 'IODA', color: '#82AAFF' },
  cloudflare: { label: 'Cloudflare', color: '#89DDFF' },
};

function formatFreshness(lastPull: string | null): string {
  if (!lastPull) return '\u2014';
  const now = Date.now();
  const pulled = new Date(lastPull).getTime();
  const diffMs = now - pulled;
  if (diffMs < 0) return 'just now';
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function SourceHealthRings({
  sources,
  lastRun,
}: {
  sources: Record<string, SourceInfo>;
  lastRun?: string | null;
}) {
  const lastRunFmt = lastRun
    ? new Date(lastRun).toLocaleString('en-GB', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
      })
    : null;

  return (
    <div>
      <p className="text-label mb-3">
        Source health{lastRunFmt ? ` — last run ${lastRunFmt}` : ''}
      </p>
      <div className="space-y-0.5">
        {Object.entries(sources).map(([key, info]) => {
          const meta = SOURCE_META[key] ?? { label: key, color: '#5C5F66' };
          return (
            <div key={key} className="flex items-center justify-between py-1.5">
              <div className="flex items-center gap-2">
                <span
                  className="w-2 h-2 rounded-full inline-block shrink-0"
                  style={{ background: info.status === 'ok' ? meta.color : '#D83C3B' }}
                />
                <span className="text-sm text-text-body">{meta.label}</span>
              </div>
              <div className="flex items-center gap-3">
                {info.metric && <span className="text-data text-text-primary">{info.metric}</span>}
                <span className="text-small">{formatFreshness(info.last_pull)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
