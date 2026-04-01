import { useState, useEffect } from 'react';
import { FileText, Download, ExternalLink } from 'lucide-react';

export default function Report() {
  const [reports, setReports] = useState<string[]>([]);
  const [selectedReport, setSelectedReport] = useState<string | null>(null);

  useEffect(() => {
    // Check if static reports exist via a quick API call
    fetch('/api/health')
      .then((r) => r.json())
      .then(() => {
        // Reports are generated at known paths
        const today = new Date().toISOString().slice(0, 10);
        setReports([
          `henri_field_${today}.html`,
          `henri_full_${today}.html`,
          'baseline_report_field.html',
          'baseline_report.html',
        ]);
        setSelectedReport(`henri_field_${today}.html`);
      })
      .catch(() => {});
  }, []);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <FileText size={24} className="text-accent" /> Static Reports
        </h2>
        <div className="flex gap-2">
          {reports.map((name) => (
            <button
              key={name}
              onClick={() => setSelectedReport(name)}
              className={`text-xs px-3 py-1.5 rounded transition-colors ${
                selectedReport === name
                  ? 'bg-accent text-white'
                  : 'bg-surface text-text-secondary hover:text-text-primary border border-border'
              }`}
            >
              {name.includes('field') ? 'Field' : 'Full'}
              {name.includes('henri_') ? ' (today)' : ' (latest)'}
            </button>
          ))}
        </div>
      </div>

      <div className="bg-surface rounded-lg border border-border p-4">
        <div className="flex items-center justify-between mb-4">
          <p className="text-sm text-text-secondary">
            {selectedReport ?? 'No report selected'}
          </p>
          {selectedReport && (
            <div className="flex gap-2">
              <a href={`/data/reports/${selectedReport}`} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs text-text-secondary hover:text-text-primary transition-colors">
                <ExternalLink size={14} /> Open in new tab
              </a>
              <a href={`/data/reports/${selectedReport}`} download
                className="flex items-center gap-1 text-xs text-text-secondary hover:text-text-primary transition-colors">
                <Download size={14} /> Download
              </a>
            </div>
          )}
        </div>
        <p className="text-sm text-text-secondary">
          Reports are generated daily by the HENRI pipeline. Use the Dashboard and
          Country pages for interactive exploration, or download the static HTML
          report for sharing via email or printing.
        </p>
      </div>
    </div>
  );
}
