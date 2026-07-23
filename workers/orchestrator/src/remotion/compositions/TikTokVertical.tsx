import { AbsoluteFill } from 'remotion';
import type { Edl } from '@verbalogix/lab-sdk';
import { EDLVideo } from '../EDLScene.js';
import { CaptionLayer } from '../Caption.js';

// TikTok: 9:16 vertical, <60s, viral-caption style (word-by-word highlights).
export const TikTokVertical: React.FC<{ edl: Edl | null; sourceUrl: string | null }> = ({ edl, sourceUrl }) => {
  if (!edl || !sourceUrl) return <AbsoluteFill style={{ backgroundColor: '#0a0e1a' }} />;
  return (
    <AbsoluteFill style={{ backgroundColor: '#0a0e1a' }}>
      <EDLVideo edl={edl} sourceUrl={sourceUrl} />
      {edl.captions.map((c, i) => (
        <CaptionLayer
          key={i}
          caption={{ ...c, style: 'karaoke' }}
          defaultFill="#ffffff"
          defaultHighlight="#ffb224"
          defaultStroke="#0a0e1a"
        />
      ))}
    </AbsoluteFill>
  );
};
