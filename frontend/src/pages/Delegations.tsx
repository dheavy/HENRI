import { useDelegations } from '../hooks/useApi';

export default function Delegations() {
  const { data, isLoading } = useDelegations();

  if (isLoading) return <div className="text-text-secondary">Loading delegations...</div>;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold">Delegation Inventory</h2>
      <p className="text-text-secondary text-sm">
        {data?.total ?? 0} delegations loaded. Full interactive view in Phase 3d.
      </p>
    </div>
  );
}
