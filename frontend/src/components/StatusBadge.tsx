export default function StatusBadge({ status }: { status: string }) {
  const isOk = status === 'ok';
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className={`w-2 h-2 rounded-full ${isOk ? 'bg-green' : 'bg-error'}`} />
      <span className={isOk ? 'text-green' : 'text-error'}>{status}</span>
    </span>
  );
}
