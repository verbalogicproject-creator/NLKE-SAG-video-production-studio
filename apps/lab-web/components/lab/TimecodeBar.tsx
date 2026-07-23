'use client';

import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

type Props = {
  workspace: string;
  channel?: string;
  live?: boolean;
  className?: string;
};

/**
 * Top-strip timecode bar. Always renders workspace name + live UTC clock +
 * channel indicator. Amber dot blinks when live=true (something is rendering
 * or publishing right now).
 *
 * Height is locked at 48px to preserve the panel grid rhythm.
 */
export function TimecodeBar({ workspace, channel = '01/04', live = false, className }: Props) {
  const [now, setNow] = useState<string>(() => utcClock());

  useEffect(() => {
    const id = setInterval(() => setNow(utcClock()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header
      className={cn(
        'h-12 px-4 flex items-center justify-between bg-bg-0',
        'hairline border-b border-border-base',
        className,
      )}
    >
      <div className="flex items-center gap-4">
        <span className="data text-xs text-ink-0 font-medium">
          {workspace.toUpperCase()}
        </span>
        <span className="data text-[10px] text-ink-3">·</span>
        <span className="data text-[11px] text-ink-2">
          {live ? (
            <span className="inline-flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 bg-signal-live rounded-full animate-live-pulse" />
              <span className="text-signal-live">LIVE</span>
            </span>
          ) : (
            <span>IDLE</span>
          )}
        </span>
      </div>

      <div className="flex items-center gap-4">
        <span className="data text-[11px] text-ink-1 tabular-nums">
          {now} <span className="text-ink-3">UTC</span>
        </span>
        <span className="data text-[10px] text-ink-3">·</span>
        <span className="data text-[11px] text-ink-2">
          CH <span className="text-amber">{channel}</span>
        </span>
      </div>
    </header>
  );
}

function utcClock(): string {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}
