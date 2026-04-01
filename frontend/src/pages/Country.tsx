import { useParams, Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useCountryDetail } from '../hooks/useApi';

export default function Country() {
  const { iso2 } = useParams<{ iso2: string }>();
  const { data, isLoading } = useCountryDetail(iso2 ?? '');

  if (isLoading) return <div className="text-text-secondary">Loading...</div>;
  if (!data) return <div className="text-red-400">Country not found</div>;

  const country = (data as Record<string, Record<string, unknown>>).country ?? {};

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <Link to="/" className="inline-flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary">
        <ArrowLeft size={16} /> Back to dashboard
      </Link>
      <h2 className="text-2xl font-bold">{country.name as string}</h2>
      <div className="bg-surface rounded-lg border border-border p-4">
        <p className="text-text-secondary text-sm">
          Country detail page — full implementation in Phase 3d.
        </p>
        <pre className="mt-4 text-xs font-mono text-text-secondary overflow-auto max-h-96">
          {JSON.stringify(data, null, 2)}
        </pre>
      </div>
    </div>
  );
}
