interface SourceInfo {
  status: string;
  last_pull: string | null;
}

const SOURCE_META: Record<string, { label: string; color: string; metric?: string }> = {
  servicenow: { label: 'ServiceNow', color: '#A8C97A', metric: '50,000 incidents' },
  grafana: { label: 'Grafana', color: '#A8C97A', metric: '316 sites' },
  netbox: { label: 'NetBox', color: '#A8C97A', metric: '46 sites' },
  acled: { label: 'ACLED', color: '#C792EA', metric: '24,891 events' },
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
}: {
  sources: Record<string, SourceInfo>;
}) {
  return (
    <div>
      <p className="text-label mb-3">Source health</p>
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
                {meta.metric && <span className="text-data text-text-primary">{meta.metric}</span>}
                <span className="text-small">{formatFreshness(info.last_pull)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
