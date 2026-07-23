import { cn, formatEta } from '@/lib/utils';

type Variant =
  | 'LINKEDIN_16_9'
  | 'YT_LONG_16_9'
  | 'YT_SHORTS_9_16'
  | 'TIKTOK_9_16'
  | 'IG_REELS_9_16'
  | 'FB_FEED_16_9';

type Status =
  | 'QUEUED'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'HALTED_BRAND_VIOLATION'
  | 'CANCELLED';

type Props = {
  variant: Variant;
  status: Status;
  /** 0–1 */
  progress: number;
  /** ms remaining */
  etaMs?: number;
  className?: string;
};

const VARIANT_LABEL: Record<Variant, string> = {
  LINKEDIN_16_9:   'LI · 16:9',
  YT_LONG_16_9:    'YT · 16:9',
  YT_SHORTS_9_16:  'YT · 9:16',
  TIKTOK_9_16:     'TT · 9:16',
  IG_REELS_9_16:   'IG · 9:16',
  FB_FEED_16_9:    'FB · 16:9',
};

const STATUS_COLOR: Record<Status, string> = {
  QUEUED:                 'text-ink-2',
  RUNNING:                'text-amber',
  COMPLETED:              'text-signal-ok',
  FAILED:                 'text-signal-live',
  HALTED_BRAND_VIOLATION: 'text-signal-live',
  CANCELLED:              'text-ink-3',
};

/**
 * One row of the Renders panel. Thin horizontal progress strip with amber
 * fill, tick marks every 10%, platform label on left, ETA on right.
 * Linear fill — NO pulsing (the live dot in TimecodeBar owns that).
 */
export function RenderProgressStrip({ variant, status, progress, etaMs, className }: Props) {
  const pct = Math.max(0, Math.min(1, progress));
  return (
    <div className={cn('px-3 py-2 border-b border-border-base last:border-b-0', className)}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="data text-[11px] text-ink-0">{VARIANT_LABEL[variant]}</span>
        <span className={cn('data text-[10px]', STATUS_COLOR[status])}>
          {status === 'RUNNING' && etaMs !== undefined
            ? `${Math.round(pct * 100)}% · ETA ${formatEta(etaMs)}`
            : status.replace(/_/g, ' ')}
        </span>
      </div>

      {/* track */}
      <div className="relative h-1.5 bg-bg-2 hairline">
        {/* fill */}
        <div
          className={cn(
            'absolute left-0 top-0 h-full transition-[width]',
            'duration-slow ease-mech',
            status === 'RUNNING'               && 'bg-amber',
            status === 'COMPLETED'             && 'bg-signal-ok',
            status === 'FAILED'                && 'bg-signal-live',
            status === 'HALTED_BRAND_VIOLATION'&& 'bg-signal-live',
            status === 'QUEUED'                && 'bg-ink-3',
            status === 'CANCELLED'             && 'bg-ink-3',
          )}
          style={{ width: `${pct * 100}%` }}
        />
        {/* tick marks every 10% */}
        <div className="absolute inset-0 flex items-center pointer-events-none">
          {Array.from({ length: 9 }, (_, i) => (
            <div
              key={i}
              className="h-full"
              style={{
                marginLeft: i === 0 ? '10%' : '10%',
                width: '1px',
                background: 'rgb(var(--border-strong) / 0.5)',
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
