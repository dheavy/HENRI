function dotColor(score: number): string {
  if (score < 25) return '#A8C97A';
  if (score < 50) return '#E5C46B';
  if (score < 70) return '#D88A6C';
  return '#D83C3B';
}

export function generateSparkline(score: number, seed: string): number[] {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = ((h << 5) - h + seed.charCodeAt(i)) | 0;
  return Array.from({ length: 30 }, () => {
    h = (h * 1103515245 + 12345) & 0x7fffffff;
    const jitter = ((h % 21) - 10) * 0.5;
    return Math.max(0, Math.min(100, score + jitter));
  });
}

export default function DotSparkline({ data }: { data: number[] }) {
  return (
    <svg viewBox="0 0 90 20" width="90" height="20">
      {data.map((val, i) => {
        const x = i * 3;
        const y = 20 - (val / 100) * 16 + 2;
        const isLast = i === data.length - 1;
        return (
          <circle
            key={i}
            cx={x}
            cy={y}
            r={isLast ? 2 : 1.5}
            fill={dotColor(val)}
          />
        );
      })}
    </svg>
  );
}
