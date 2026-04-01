import { useCountUp } from '../hooks/useCountUp';

interface Props {
  value: number;
  decimals?: number;
  suffix?: string;
  prefix?: string;
  duration?: number;
  className?: string;
}

/**
 * Renders a number with an odometer count-up animation.
 * Re-animates when the value changes.
 */
export default function AnimatedNumber({
  value,
  decimals = 0,
  suffix = '',
  prefix = '',
  duration = 1.5,
  className,
}: Props) {
  const ref = useCountUp(value, { decimals, suffix, prefix, duration });
  return <span ref={ref} className={className} />;
}
