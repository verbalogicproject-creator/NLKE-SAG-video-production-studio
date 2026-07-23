import { AbsoluteFill } from 'remotion';
import type { Edl } from '@verbalogix/lab-sdk';
import { EDLVideo } from '../EDLScene.js';
import { CaptionLayer } from '../Caption.js';

// LinkedIn: 16:9, 30–90s, professional register, business-value hook.
// Captions are block-style (not karaoke); on a professional feed, word-by-word
// highlighting reads as aggressive / TikTok-adjacent.
export const LinkedinLongForm: React.FC<{ edl: Edl | null; sourceUrl: string | null }> = ({ edl, sourceUrl }) => {
  if (!edl || !sourceUrl) {
    return <AbsoluteFill style={{ backgroundColor: '#0a0e1a' }} />;
  }
  return (
    <AbsoluteFill style={{ backgroundColor: '#0a0e1a' }}>
      <EDLVideo edl={edl} sourceUrl={sourceUrl} />
      {edl.captions.map((c, i) => (
        <CaptionLayer
          key={i}
          caption={{ ...c, style: 'block' }}
          defaultFill="#e8ecf5"
          defaultHighlight="#ffb224"
          defaultStroke="#0a0e1a"
        />
      ))}
    </AbsoluteFill>
  );
};
