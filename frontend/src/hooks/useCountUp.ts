import { useEffect, useRef } from 'react';
import { CountUp } from 'countup.js';

interface Options {
  duration?: number;
  decimals?: number;
  separator?: string;
  suffix?: string;
  prefix?: string;
}

/**
 * Odometer-style count-up animation for numeric values.
 * Returns a ref to attach to the target DOM element.
 */
export function useCountUp(
  end: number,
  options: Options = {},
) {
  const ref = useRef<HTMLSpanElement>(null);
  const countUpRef = useRef<CountUp | null>(null);
  const prevEnd = useRef<number>(0);

  useEffect(() => {
    if (!ref.current) return;

    if (!countUpRef.current) {
      countUpRef.current = new CountUp(ref.current, end, {
        duration: options.duration ?? 1.5,
        decimalPlaces: options.decimals ?? 0,
        separator: options.separator ?? ',',
        suffix: options.suffix ?? '',
        prefix: options.prefix ?? '',
        useEasing: true,
        useGrouping: true,
      });
      countUpRef.current.start();
    } else if (end !== prevEnd.current) {
      countUpRef.current.update(end);
    }

    prevEnd.current = end;
  }, [end, options.duration, options.decimals, options.separator, options.suffix, options.prefix]);

  return ref;
}
