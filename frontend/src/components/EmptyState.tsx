import { useState, useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { RefreshCw, AlertCircle, CheckCircle } from 'lucide-react';
import { fetchPipelineStatus, triggerRegenerate } from '../api/client';
import type { PipelineStatus } from '../api/client';

interface EmptyStateProps {
  title?: string;
  message?: string;
}

export default function EmptyState({
  title = 'No data available',
  message = 'The pipeline has not been run yet. Generate reports to populate this page.',
}: EmptyStateProps) {
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

  // Poll while running
  useEffect(() => {
    if (!polling) return;
    const interval = setInterval(async () => {
      const s = await checkStatus();
      if (s && !s.running) {
        setPolling(false);
        if (s.status === 'done') {
          // Invalidate all queries to refresh data
          queryClient.invalidateQueries();
        }
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [polling, checkStatus, queryClient]);

  // Check status on mount (maybe pipeline is already running)
  useEffect(() => {
    checkStatus().then((s) => {
      if (s?.running) {
        setPolling(true);
        setTriggered(true);
      }
    });
  }, [checkStatus]);

  const handleRegenerate = async () => {
    try {
      const result = await triggerRegenerate();
      if (result.accepted) {
        setTriggered(true);
        setPolling(true);
      }
    } catch {
      // ignore
    }
  };

  const isRunning = status?.running || polling;
  const isDone = triggered && status?.status === 'done';
  const isError = triggered && status?.status === 'error';

  return (
    <div className="flex flex-col items-center justify-center py-16 px-8">
      <div className="bg-bg-surface border border-border p-8 max-w-md text-center space-y-4">
        {isDone ? (
          <>
            <CheckCircle size={40} className="mx-auto text-green" />
            <h3 className="text-lg font-medium text-text-primary">Reports generated</h3>
            <p className="text-sm text-text-muted">Data is ready. The page will refresh automatically.</p>
          </>
        ) : isError ? (
          <>
            <AlertCircle size={40} className="mx-auto text-error" />
            <h3 className="text-lg font-medium text-text-primary">Generation failed</h3>
            <p className="text-sm text-text-muted">{status?.error ?? 'An error occurred during pipeline execution.'}</p>
            <button onClick={handleRegenerate}
              className="px-4 py-2 bg-accent text-white text-sm hover:opacity-90 transition-opacity">
              Retry
            </button>
          </>
        ) : isRunning ? (
          <>
            <RefreshCw size={40} className="mx-auto text-accent animate-spin" />
            <h3 className="text-lg font-medium text-text-primary">Generating reports...</h3>
            <p className="text-sm text-text-muted">
              The pipeline is running. This typically takes 1–2 minutes.
              The page will refresh automatically when complete.
            </p>
          </>
        ) : (
          <>
            <div className="w-12 h-12 mx-auto rounded-full bg-bg-highlight flex items-center justify-center">
              <RefreshCw size={24} className="text-text-muted" />
            </div>
            <h3 className="text-lg font-medium text-text-primary">{title}</h3>
            <p className="text-sm text-text-muted">{message}</p>
            <button onClick={handleRegenerate}
              className="px-4 py-2 bg-accent text-white text-sm hover:opacity-90 transition-opacity">
              Generate reports
            </button>
          </>
        )}
      </div>
    </div>
  );
}
