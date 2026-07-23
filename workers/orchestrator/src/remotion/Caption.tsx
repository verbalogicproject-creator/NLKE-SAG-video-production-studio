import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import type { Caption as CaptionType, CaptionWord } from '@verbalogix/lab-sdk';

/**
 * Caption overlay component. Renders a Caption from an EDL as styled text
 * synced to the output timeline. Handles three styles:
 *
 *  · block    — static multi-word chunks, fades in/out at word group boundaries
 *  · karaoke  — current word highlighted in accent color, others at normal fill
 *  · ticker   — scrolling bottom ticker (Sprint 2+)
 */

const GROUP_SIZE = 4; // words per visible "line" in block/karaoke

type Props = {
  caption: CaptionType;
  /** Fallback colors when the caption doesn't specify */
  defaultFill?: string;
  defaultHighlight?: string;
  defaultStroke?: string;
};

export function CaptionLayer({
  caption,
  defaultFill = '#ffffff',
  defaultHighlight = '#ffb224',
  defaultStroke = '#0a0e1a',
}: Props) {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const nowMs = (frame / fps) * 1000;

  const fill = caption.fillColor ?? defaultFill;
  const highlight = caption.highlightColor ?? defaultHighlight;
  const stroke = caption.strokeColor ?? defaultStroke;

  // Which word group is active right now?
  const activeGroup = findActiveGroup(caption.words, nowMs);
  if (!activeGroup) return null;

  const { words, groupStart, groupEnd } = activeGroup;
  const activeIdx = words.findIndex((w) => nowMs >= w.startMs && nowMs < w.endMs);

  // Compose position — anchor-aware.
  const { position } = caption;
  const left = position.x * width;
  const top  = position.y * height;

  let transform: string;
  switch (position.anchor) {
    case 'top-left':       transform = 'translate(0, 0)'; break;
    case 'center':         transform = 'translate(-50%, -50%)'; break;
    case 'bottom-center':  transform = 'translate(-50%, -100%)'; break;
    case 'bottom-left':    transform = 'translate(0, -100%)'; break;
    default:               transform = 'translate(-50%, -50%)';
  }

  const fade = fadeAt(nowMs, groupStart, groupEnd);

  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div
        style={{
          position: 'absolute',
          left,
          top,
          transform,
          opacity: fade,
          maxWidth: width * 0.9,
          display: 'flex',
          flexWrap: 'wrap',
          gap: '0.3em',
          justifyContent: 'center',
          fontFamily: 'IBM Plex Mono, monospace',
          fontSize: 64,
          fontWeight: 700,
          lineHeight: 1.1,
          textAlign: 'center',
          WebkitTextStroke: `3px ${stroke}`,
          textShadow: `0 4px 16px ${stroke}cc`,
        }}
      >
        {words.map((w, i) => {
          const isActive = i === activeIdx;
          const isEmph = w.emphasis !== 'none';
          const color =
            caption.style === 'karaoke' && isActive ? highlight :
            caption.style === 'karaoke' && !isActive ? fill :
            isEmph ? highlight : fill;

          return (
            <span
              key={i}
              style={{
                color,
                transform: isActive && caption.style === 'karaoke' ? 'scale(1.06)' : 'scale(1)',
                transformOrigin: 'center',
                transition: 'transform 80ms ease-out, color 80ms ease-out',
                textTransform: caption.style === 'karaoke' ? 'uppercase' : 'none',
              }}
            >
              {w.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
}

function findActiveGroup(words: CaptionWord[], nowMs: number):
  | { words: CaptionWord[]; groupStart: number; groupEnd: number }
  | null
{
  for (let i = 0; i < words.length; i += GROUP_SIZE) {
    const group = words.slice(i, i + GROUP_SIZE);
    const groupStart = group[0]!.startMs;
    const groupEnd = group[group.length - 1]!.endMs;
    if (nowMs >= groupStart - 200 && nowMs < groupEnd + 200) {
      return { words: group, groupStart, groupEnd };
    }
  }
  return null;
}

/** Fade in over 120ms, hold, fade out over 120ms */
function fadeAt(nowMs: number, start: number, end: number): number {
  const FADE = 120;
  if (nowMs < start) return Math.max(0, 1 - (start - nowMs) / FADE);
  if (nowMs > end)   return Math.max(0, 1 - (nowMs - end) / FADE);
  return 1;
}
