import { useState, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  Upload, Trash2, FileText, Database, Globe, Server,
  ChevronDown, ChevronRight, Terminal, CheckCircle, AlertCircle,
} from 'lucide-react';
import { useFixtures } from '../hooks/useApi';
import { uploadFixture, deleteFixture, triggerRegenerate } from '../api/client';
import type { FixtureSlot, FixtureFileInfo } from '../api/client';
import RegenerateButton from '../components/RegenerateButton';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
  }) + ' UTC';
}

const CATEGORY_ICONS: Record<string, typeof Globe> = {
  servicenow: Database,
  osint: Globe,
  internal: Server,
};

const CATEGORY_LABELS: Record<string, string> = {
  servicenow: 'ServiceNow',
  osint: 'OSINT Sources',
  internal: 'Internal Sources',
};

// ── File info display ───────────────────────────────────────────────

function FileInfoRow({ info, onDelete }: {
  info: FixtureFileInfo;
  onDelete?: () => void;
}) {
  if (!info.exists) {
    return (
      <div className="text-xs text-text-muted italic">Not uploaded</div>
    );
  }
  return (
    <div className="flex items-center gap-3 text-xs text-text-body py-1">
      <FileText size={14} className="text-text-muted shrink-0" />
      <span className="font-medium text-text-primary">{info.name}</span>
      <span className="text-text-muted">
        {info.size_bytes != null && formatBytes(info.size_bytes)}
      </span>
      {info.rows != null && (
        <span className="text-text-muted">{info.rows.toLocaleString()} rows</span>
      )}
      {info.record_count != null && (
        <span className="text-text-muted">{info.record_count.toLocaleString()} records</span>
      )}
      {info.modified_at && (
        <span className="text-text-muted">{formatDate(info.modified_at)}</span>
      )}
      {onDelete && (
        <button
          onClick={onDelete}
          className="ml-auto text-text-muted hover:text-error transition-colors"
          title="Delete this file"
        >
          <Trash2 size={13} />
        </button>
      )}
    </div>
  );
}

// ── Refresh info panel ──────────────────────────────────────────────

function RefreshInfoPanel({ slot }: { slot: FixtureSlot }) {
  const [open, setOpen] = useState(false);
  const ri = slot.refresh_info;
  if (!ri) return null;

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-text-muted hover:text-text-body transition-colors"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        How to refresh from source
      </button>
      {open && (
        <div className="mt-2 p-3 bg-bg-deepest border border-border text-xs space-y-2">
          <div>
            <span className="text-text-muted">Prerequisites: </span>
            <span className="text-text-body">{ri.prerequisites}</span>
          </div>
          {ri.env_vars.length > 0 && (
            <div>
              <span className="text-text-muted">Environment variables: </span>
              <span className="text-data font-mono text-text-body">
                {ri.env_vars.join(', ')}
              </span>
            </div>
          )}
          <div>
            <span className="text-text-muted">CLI command: </span>
            <code className="bg-bg-base px-1.5 py-0.5 text-accent font-mono">
              <Terminal size={10} className="inline mr-1" />
              {ri.cli}
            </code>
          </div>
          {ri.notes && (
            <div className="text-text-muted italic">{ri.notes}</div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Upload dropzone ─────────────────────────────────────────────────

function UploadZone({ slot, onUploaded }: {
  slot: FixtureSlot;
  onUploaded: () => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    setResult(null);
    try {
      for (const f of Array.from(files)) {
        await uploadFixture(slot.id, f);
      }
      setResult({ ok: true, msg: `Uploaded ${files.length} file(s)` });
      onUploaded();
    } catch (err: unknown) {
      setResult({ ok: false, msg: err instanceof Error ? err.message : 'Upload failed' });
    } finally {
      setUploading(false);
    }
  }, [slot.id, onUploaded]);

  const accept = slot.type === 'csv' ? '.csv' : '.json';

  return (
    <div className="mt-2">
      <label
        className={`
          flex items-center justify-center gap-2 p-3 border border-dashed
          cursor-pointer transition-colors text-xs
          ${dragging
            ? 'border-accent bg-bg-highlight text-text-primary'
            : 'border-border text-text-muted hover:border-text-muted hover:text-text-body'
          }
          ${uploading ? 'opacity-50 pointer-events-none' : ''}
        `}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
      >
        <Upload size={14} />
        <span>
          {uploading
            ? 'Uploading…'
            : `Drop ${slot.type.toUpperCase()} file${slot.multi ? '(s)' : ''} here or click to browse`
          }
        </span>
        <input
          type="file"
          accept={accept}
          multiple={slot.multi}
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </label>
      {result && (
        <div className={`mt-1 flex items-center gap-1 text-xs ${result.ok ? 'text-green' : 'text-error'}`}>
          {result.ok ? <CheckCircle size={12} /> : <AlertCircle size={12} />}
          {result.msg}
        </div>
      )}
    </div>
  );
}

// ── Fixture card ────────────────────────────────────────────────────

function FixtureCard({ slot, onRefresh }: {
  slot: FixtureSlot;
  onRefresh: () => void;
}) {
  const queryClient = useQueryClient();

  const handleDelete = async (filename: string) => {
    if (!confirm(`Delete ${filename}?`)) return;
    try {
      await deleteFixture(slot.id, filename);
      queryClient.invalidateQueries({ queryKey: ['fixtures'] });
    } catch {
      // ignore
    }
  };

  return (
    <div className="bg-bg-surface border border-border p-4 space-y-2">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-sm font-medium text-text-primary">{slot.label}</h3>
          <p className="text-xs text-text-muted mt-0.5">{slot.description}</p>
        </div>
        <span className="text-data text-xs font-mono text-text-muted uppercase">
          {slot.type}
        </span>
      </div>

      {/* Current files */}
      <div className="space-y-0.5">
        {slot.multi && slot.files ? (
          slot.files.length > 0 ? (
            slot.files.map((f) => (
              <FileInfoRow
                key={f.name}
                info={f}
                onDelete={() => handleDelete(f.name)}
              />
            ))
          ) : (
            <div className="text-xs text-text-muted italic">No files uploaded</div>
          )
        ) : slot.file ? (
          <FileInfoRow info={slot.file} />
        ) : null}
      </div>

      {/* Required columns hint for CSVs */}
      {slot.required_columns && slot.required_columns.length > 0 && (
        <div className="text-xs text-text-muted">
          Required columns: <span className="font-mono">{slot.required_columns.join(', ')}</span>
        </div>
      )}

      <UploadZone slot={slot} onUploaded={onRefresh} />
      <RefreshInfoPanel slot={slot} />
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────

export default function Fixtures() {
  const { data, isLoading } = useFixtures();
  const queryClient = useQueryClient();
  const [regenTriggered, setRegenTriggered] = useState(false);

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['fixtures'] });
  };

  const handleRegenAfterUpload = async () => {
    handleRefresh();
    try {
      const result = await triggerRegenerate();
      if (result.accepted) setRegenTriggered(true);
    } catch {
      // ignore
    }
  };

  if (isLoading) {
    return <div className="text-text-muted p-8">Loading fixtures…</div>;
  }

  const fixtures = data?.fixtures ?? [];
  const categories = ['servicenow', 'osint', 'internal'] as const;

  return (
    <div className="max-w-[960px] mx-auto space-y-8 p-4">
      <div>
        <h1 className="text-heading text-xl">Data Fixtures</h1>
        <p className="text-sm text-text-muted mt-1">
          Upload updated source data when live API access is unavailable.
          After uploading, regenerate the pipeline to refresh the dashboard.
        </p>
        <div className="mt-3 flex items-center gap-3">
          <RegenerateButton />
          {regenTriggered && (
            <span className="text-xs text-green">Pipeline triggered after upload</span>
          )}
        </div>
      </div>

      {categories.map((cat) => {
        const slots = fixtures.filter((f) => f.category === cat);
        if (slots.length === 0) return null;
        const Icon = CATEGORY_ICONS[cat] || Globe;
        return (
          <section key={cat}>
            <h2 className="flex items-center gap-2 text-sm font-medium text-text-body uppercase tracking-wider mb-3">
              <Icon size={16} />
              {CATEGORY_LABELS[cat] || cat}
            </h2>
            <div className="grid gap-3">
              {slots.map((slot) => (
                <FixtureCard
                  key={slot.id}
                  slot={slot}
                  onRefresh={handleRegenAfterUpload}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
