import { cn } from '@/lib/utils';

type Platform = 'YOUTUBE' | 'LINKEDIN' | 'TIKTOK' | 'INSTAGRAM' | 'FACEBOOK';

type Props = {
  platform: Platform;
  connected?: boolean;
  selected?: boolean;
  onClick?: () => void;
  className?: string;
};

const SHORT: Record<Platform, string> = {
  YOUTUBE:   'YT',
  LINKEDIN:  'LI',
  TIKTOK:    'TT',
  INSTAGRAM: 'IG',
  FACEBOOK:  'FB',
};

/**
 * Platform pill. Amber ring when selected, muted when connected-but-unselected,
 * disabled grey-crossed when not connected. Clickable.
 */
export function TargetBadge({ platform, connected, selected, onClick, className }: Props) {
  const label = SHORT[platform];
  const isInteractive = typeof onClick === 'function' && connected;

  return (
    <button
      type="button"
      onClick={isInteractive ? onClick : undefined}
      disabled={!connected}
      aria-pressed={selected}
      className={cn(
        'data text-[11px] px-2 py-1 transition-colors duration-fast',
        'border-2 min-w-[40px] text-center',
        connected && selected    && 'bg-amber text-bg-0 border-amber',
        connected && !selected   && 'bg-bg-1 text-ink-1 border-border-strong hover:border-amber hover:text-amber',
        !connected               && 'bg-bg-1 text-ink-3 border-border-base line-through cursor-not-allowed',
        className,
      )}
      title={connected ? `${platform} — click to ${selected ? 'remove' : 'add'}` : `${platform} — not connected`}
    >
      {label}
    </button>
  );
}
