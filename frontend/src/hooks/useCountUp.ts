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
 * Odometer-style count-up animation that starts when the element
 * scrolls into view (IntersectionObserver). Re-animates on value change
 * only if already visible.
 */
export function useCountUp(
  end: number,
  options: Options = {},
) {
  const ref = useRef<HTMLSpanElement>(null);
  const countUpRef = useRef<CountUp | null>(null);
  const prevEnd = useRef<number>(0);
  const hasStarted = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;

        if (!countUpRef.current) {
          countUpRef.current = new CountUp(el, end, {
            duration: options.duration ?? 1.5,
            decimalPlaces: options.decimals ?? 0,
            separator: options.separator ?? ',',
            suffix: options.suffix ?? '',
            prefix: options.prefix ?? '',
            useEasing: true,
            useGrouping: true,
          });
          countUpRef.current.start();
          hasStarted.current = true;
          prevEnd.current = end;
        }

        // Once started, disconnect — subsequent updates handled below
        observer.disconnect();
      },
      { threshold: 0.1 },
    );

    observer.observe(el);
    return () => observer.disconnect();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Handle value updates after initial animation
  useEffect(() => {
    if (hasStarted.current && countUpRef.current && end !== prevEnd.current) {
      countUpRef.current.update(end);
      prevEnd.current = end;
    }
  }, [end]);

  return ref;
}
