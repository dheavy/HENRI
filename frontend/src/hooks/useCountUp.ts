import { useEffect, useRef } from 'react';
import { CountUp } from 'countup.js';

interface Options {
  duration?: number;
  decimals?: number;
  separator?: string;
  suffix?: string;
  prefix?: string;
  /** Start immediately instead of waiting for IntersectionObserver */
  immediate?: boolean;
}

export function useCountUp(
  end: number,
  options: Options = {},
) {
  const ref = useRef<HTMLSpanElement>(null);
  const countUpRef = useRef<CountUp | null>(null);
  const prevEnd = useRef<number>(0);
  const hasStarted = useRef(false);

  const startCountUp = (el: HTMLElement) => {
    if (countUpRef.current) return;
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
  };

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    if (options.immediate) {
      startCountUp(el);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        startCountUp(el);
        observer.disconnect();
      },
      { threshold: 0.1 },
    );

    observer.observe(el);
    return () => observer.disconnect();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (hasStarted.current && countUpRef.current && end !== prevEnd.current) {
      countUpRef.current.update(end);
      prevEnd.current = end;
    }
  }, [end]);

  return ref;
}
