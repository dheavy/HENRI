import { useState, useEffect } from 'react';
import { FileText, Download } from 'lucide-react';
import clsx from 'clsx';

interface ReportEntry {
  filename: string;
  label: string;
  description: string;
}

function parseReports(files: string[]): ReportEntry[] {
  return files.map((f) => {
    const dateMatch = f.match(/(\d{4}-\d{2}-\d{2})/);
    const date = dateMatch ? dateMatch[1] : '';

    if (f.startsWith('henri_field_'))
      return { filename: f, label: `Field report (${date})`, description: 'field' };
    if (f.startsWith('henri_full_'))
      return { filename: f, label: `Full report (${date})`, description: 'full' };
    if (f.includes('field'))
      return { filename: f, label: 'Field report (latest)', description: 'field' };
    return { filename: f, label: 'Full report (latest)', description: 'full' };
  });
}

const DESCRIPTIONS: Record<string, string> = {
  full: 'The full report includes all 50,000 incidents across all regions — HQ, field delegations, and unassigned tickets. Use this for a complete operational picture.',
  field: 'The field report filters to the six field ICT regions only (AFRICA East/West, AMERICAS, ASIA, EURASIA, NAME), excluding HQ and unassigned tickets.',
};

export default function Report() {
  const [entries, setEntries] = useState<ReportEntry[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);

  useEffect(() => {
    fetch('/api/v1/reports')
      .then((r) => r.json())
      .then((data) => {
        const parsed = parseReports(data.reports ?? []);
        setEntries(parsed);
      })
      .catch(() => {});
  }, []);

  const selected = entries[selectedIdx] ?? null;
  const viewUrl = selected ? `/api/v1/reports/${selected.filename}` : null;
  const downloadUrl = selected ? `/api/v1/reports/${selected.filename}/download` : null;

  return (
    <div className="max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <FileText size={24} className="text-accent" /> Static Reports
        </h2>
        {downloadUrl && (
          <a href={downloadUrl}
            className="flex items-center gap-1 text-xs bg-accent text-white px-3 py-1.5 rounded hover:opacity-90 transition-opacity">
            <Download size={14} /> Download HTML
          </a>
        )}
      </div>

      {/* Report selector tabs */}
      {entries.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {entries.map((e, i) => (
            <button key={e.filename} onClick={() => setSelectedIdx(i)}
              className={clsx('text-xs px-3 py-1.5 rounded transition-colors',
                selectedIdx === i
                  ? 'bg-accent text-white'
                  : 'bg-bg-surface text-text-muted hover:text-text-primary border border-border'
              )}>
              {e.label}
            </button>
          ))}
        </div>
      )}

      {/* Description */}
      {selected && (
        <p className="text-sm text-text-muted leading-relaxed">
          {DESCRIPTIONS[selected.description] ?? ''}
        </p>
      )}

      {/* Embedded report */}
      {viewUrl ? (
        <iframe
          key={selected?.filename}
          src={viewUrl}
          title={selected?.label ?? 'Report'}
          className="w-full rounded-lg border border-border"
          style={{ height: 'calc(100vh - 260px)' }}
        />
      ) : (
        <div className="bg-bg-surface rounded-lg border border-border p-8 text-center text-text-muted">
          No reports generated yet. Run the pipeline first.
        </div>
      )}
    </div>
  );
}
