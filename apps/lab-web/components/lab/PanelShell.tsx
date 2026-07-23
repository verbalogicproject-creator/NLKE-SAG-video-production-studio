import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

type Props = {
  title: string;
  subtitle?: string;
  action?: ReactNode;     // right-aligned header slot (e.g. count, button)
  footer?: ReactNode;     // timestamp, counters, shortcuts
  children: ReactNode;
  className?: string;
  /** Makes the panel stretch to fill its parent's height */
  fill?: boolean;
};

/**
 * The standard panel wrapper in the Cutting Room grammar.
 * Hairline border, header strip with data-mono title, optional footer.
 * Use inside a grid. No rounded corners (industrial feel).
 */
export function PanelShell({
  title,
  subtitle,
  action,
  footer,
  children,
  className,
  fill,
}: Props) {
  return (
    <section
      className={cn(
        'bg-bg-1 hairline flex flex-col',
        fill && 'h-full',
        className,
      )}
    >
      <header className="flex items-center justify-between px-3 py-2 border-b border-border-base">
        <div className="flex items-baseline gap-2 min-w-0">
          <h2 className="data text-[11px] text-ink-1 truncate">
            {title.toUpperCase()}
          </h2>
          {subtitle && (
            <span className="data text-[10px] text-ink-3 truncate">
              {subtitle}
            </span>
          )}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </header>

      <div className="flex-1 min-h-0 overflow-auto">{children}</div>

      {footer && (
        <footer className="px-3 py-1.5 border-t border-border-base text-ink-3">
          <div className="data text-[10px] flex items-center justify-between">
            {footer}
          </div>
        </footer>
      )}
    </section>
  );
}
