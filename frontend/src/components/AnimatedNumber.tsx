import { useCountUp } from '../hooks/useCountUp';

interface Props {
  value: number;
  decimals?: number;
  suffix?: string;
  prefix?: string;
  duration?: number;
  className?: string;
  /** Start animation immediately instead of waiting for scroll into view */
  immediate?: boolean;
}

export default function AnimatedNumber({
  value,
  decimals = 0,
  suffix = '',
  prefix = '',
  duration = 1.5,
  className,
  immediate = false,
}: Props) {
  const ref = useCountUp(value, { decimals, suffix, prefix, duration, immediate });
  return <span ref={ref} className={className} />;
}
