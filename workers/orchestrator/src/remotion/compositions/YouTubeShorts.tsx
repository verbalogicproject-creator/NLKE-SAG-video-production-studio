import { AbsoluteFill } from 'remotion';
import type { Edl } from '@verbalogix/lab-sdk';
import { EDLVideo } from '../EDLScene.js';
import { CaptionLayer } from '../Caption.js';

/**
 * YouTube Shorts — 9:16 vertical, under 60s, retention-first.
 *
 * Takes a full EDL prop. The EDL is the single source of truth; this
 * composition only decides *styling* (caption colors, font weights, the
 * presence of a safe-area mask for the YouTube UI overlay).
 *
 * The first real composition wired end-to-end. Others (TikTok, LinkedIn,
 * YT long) follow the same pattern with different styling knobs.
 */

type Props = {
  edl: Edl | null;
  /** Public or presigned URL to the source video in R2 */
  sourceUrl: string | null;
};

export const YouTubeShorts: React.FC<Props> = ({ edl, sourceUrl }) => {
  if (!edl || !sourceUrl) {
    return (
      <AbsoluteFill
        style={{
          backgroundColor: '#0a0e1a',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ffb224',
          fontFamily: 'IBM Plex Mono, monospace',
        }}
      >
        <div style={{ fontSize: 32 }}>NO EDL</div>
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{ backgroundColor: '#0a0e1a' }}>
      {/* 1. Source footage via the EDL's scene sequence */}
      <EDLVideo edl={edl} sourceUrl={sourceUrl} />

      {/* 2. Caption layers — karaoke style by default on 9:16 */}
      {edl.captions.map((c, i) => (
        <CaptionLayer
          key={i}
          caption={c}
          defaultFill="#ffffff"
          defaultHighlight="#ffb224"
          defaultStroke="#0a0e1a"
        />
      ))}

      {/* 3. YouTube Shorts safe zone — avoid the right-side UI column.
           10% right margin is the documented safe area for Shorts UI. */}
      <AbsoluteFill
        style={{
          pointerEvents: 'none',
          background:
            'linear-gradient(to left, rgba(10,14,26,0.0) 90%, rgba(10,14,26,0.0) 100%)',
        }}
      />
    </AbsoluteFill>
  );
};
