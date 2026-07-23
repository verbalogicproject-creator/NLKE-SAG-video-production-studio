'use client';

import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';

export type TickerEvent = {
  id: string;
  ts: number;       // epoch ms
  level: 'INFO' | 'WARN' | 'ERROR' | 'OK';
  message: string;
};

type Props = {
  events: TickerEvent[];
  className?: string;
  /** How many events to keep visible at once */
  maxVisible?: number;
};

/**
 * Bottom-of-screen live feed. Receives events (via SSE in prod, mocked
 * in the demo). Auto-scrolls to newest. Each line is monospace data-style
 * with a color swatch by level.
 *
 * Motion: instant scroll, no fade. This is a tool, not a showcase.
 */
export function LiveTicker({ events, className, maxVisible = 50 }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [events.length]);

  const visible = events.slice(-maxVisible);

  return (
    <div
      className={cn(
        'h-8 overflow-hidden border-t border-border-base bg-bg-0 px-3',
        'flex items-center',
        className,
      )}
    >
      <div className="data text-[10px] text-ink-3 shrink-0 mr-3">TICKER</div>
      <div className="flex-1 min-w-0 overflow-x-auto whitespace-nowrap">
        {visible.map((e) => (
          <span
            key={e.id}
            className="data text-[10px] mr-4 tabular-nums"
          >
            <span className="text-ink-3">{formatTs(e.ts)}</span>{' '}
            <span
              className={cn(
                e.level === 'OK'    && 'text-signal-ok',
                e.level === 'WARN'  && 'text-signal-warn',
                e.level === 'ERROR' && 'text-signal-live',
                e.level === 'INFO'  && 'text-ink-1',
              )}
            >
              [{e.level}]
            </span>{' '}
            <span className="text-ink-0">{e.message}</span>
          </span>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}

function formatTs(ms: number): string {
  const d = new Date(ms);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}
