import clsx from 'clsx';

export default function StatusBadge({ status }: { status: string }) {
  const isOk = status === 'ok';
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className={clsx('w-2 h-2 rounded-full', isOk ? 'bg-green-500' : 'bg-red-500')} />
      <span className={isOk ? 'text-green-400' : 'text-red-400'}>{status}</span>
    </span>
  );
}
