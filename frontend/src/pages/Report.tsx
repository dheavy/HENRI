import { useState, useEffect } from 'react';
import { FileText, Download, ExternalLink } from 'lucide-react';
import clsx from 'clsx';

export default function Report() {
  const [reports, setReports] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/v1/reports')
      .then((r) => r.json())
      .then((data) => {
        const files: string[] = data.reports ?? [];
        setReports(files);
        if (files.length > 0) setSelected(files[0]);
      })
      .catch(() => {});
  }, []);

  const reportUrl = selected ? `/api/v1/reports/${selected}` : null;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <FileText size={24} className="text-accent" /> Static Reports
        </h2>
        {reportUrl && (
          <div className="flex gap-2">
            <a href={reportUrl} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs bg-surface border border-border px-3 py-1.5 rounded text-text-secondary hover:text-text-primary transition-colors">
              <ExternalLink size={14} /> Open in new tab
            </a>
            <a href={reportUrl} download={selected}
              className="flex items-center gap-1 text-xs bg-accent text-white px-3 py-1.5 rounded hover:opacity-90 transition-opacity">
              <Download size={14} /> Download
            </a>
          </div>
        )}
      </div>

      {/* Report selector */}
      {reports.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {reports.map((name) => (
            <button key={name} onClick={() => setSelected(name)}
              className={clsx('text-xs px-3 py-1.5 rounded transition-colors',
                selected === name
                  ? 'bg-accent text-white'
                  : 'bg-surface text-text-secondary hover:text-text-primary border border-border'
              )}>
              {name}
            </button>
          ))}
        </div>
      )}

      {/* Embedded report */}
      {reportUrl ? (
        <iframe
          src={reportUrl}
          title={selected ?? 'Report'}
          className="w-full rounded-lg border border-border bg-white"
          style={{ height: 'calc(100vh - 220px)' }}
        />
      ) : (
        <div className="bg-surface rounded-lg border border-border p-8 text-center text-text-secondary">
          No reports generated yet. Run the pipeline first.
        </div>
      )}
    </div>
  );
}
