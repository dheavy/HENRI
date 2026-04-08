import { useState, useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { RefreshCw, CheckCircle, AlertCircle } from 'lucide-react';
import { fetchPipelineStatus, triggerRegenerate } from '../api/client';
import type { PipelineStatus } from '../api/client';

/**
 * Inline button that triggers a pipeline regeneration and reflects status.
 *
 * Same trigger/poll/invalidate flow as EmptyState, but rendered as a small
 * inline control instead of a full card. Use anywhere on the page that
 * stays visible after the dashboard has data.
 */
export default function RegenerateButton() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [polling, setPolling] = useState(false);
  const [triggered, setTriggered] = useState(false);

  const checkStatus = useCallback(async () => {
    try {
      const s = await fetchPipelineStatus();
      setStatus(s);
      return s;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    if (!polling) return;
    const interval = setInterval(async () => {
      const s = await checkStatus();
      if (s && !s.running) {
        setPolling(false);
        if (s.status === 'done') {
          queryClient.invalidateQueries();
        }
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [polling, checkStatus, queryClient]);

  // On mount: if a pipeline is already running (e.g. scheduler), join the
  // poll so the button reflects its progress.
  useEffect(() => {
    checkStatus().then((s) => {
      if (s?.running) {
        setPolling(true);
        setTriggered(true);
      }
    });
  }, [checkStatus]);

  const handleClick = async () => {
    if (polling || status?.running) return;
    try {
      const result = await triggerRegenerate();
      if (result.accepted) {
        setTriggered(true);
        setPolling(true);
      }
    } catch {
      // ignore — user can retry
    }
  };

  const isRunning = status?.running || polling;
  const isDone = triggered && !isRunning && status?.status === 'done';
  const isError = triggered && !isRunning && status?.status === 'error';

  let label: string;
  let Icon = RefreshCw;
  let spin = false;
  let disabled = false;
  let title: string | undefined;

  if (isRunning) {
    label = 'Generating…';
    spin = true;
    disabled = true;
    title = 'Pipeline is running. This typically takes 1–2 minutes.';
  } else if (isDone) {
    label = 'Generated';
    Icon = CheckCircle;
  } else if (isError) {
    label = 'Retry';
    Icon = AlertCircle;
    title = status?.error ?? 'Pipeline failed. Click to retry.';
  } else {
    label = 'Regenerate';
    title = 'Run the pipeline now to refresh all data.';
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled}
      title={title}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 text-data text-xs border border-border bg-bg-surface text-text-muted hover:text-text-primary hover:border-text-muted transition-colors disabled:opacity-60 disabled:cursor-wait"
    >
      <Icon size={12} className={spin ? 'animate-spin' : ''} />
      <span>{label}</span>
    </button>
  );
}
