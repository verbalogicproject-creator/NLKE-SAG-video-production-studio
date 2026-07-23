import { Composition } from 'remotion';
import { edlDurationFrames, type Edl } from '@verbalogix/lab-sdk';

/**
 * Remotion root. One <Composition> per PlatformVariant. Each composition
 * reads its own EDL prop and renders captions, visuals, transitions.
 *
 * Compositions use a `calculateMetadata` callback so duration + resolution
 * are driven by the EDL at render time, not by the defaults below.
 */

import { LinkedinLongForm } from './compositions/LinkedinLongForm.js';
import { YouTubeShorts } from './compositions/YouTubeShorts.js';
import { TikTokVertical } from './compositions/TikTokVertical.js';
import { YouTubeLong } from './compositions/YouTubeLong.js';

type EdlProps = { edl: Edl | null; sourceUrl: string | null };

function metadataFromEdl({ props }: { props: EdlProps }) {
  if (!props.edl) return {}; // keep defaults if no EDL yet
  return {
    durationInFrames: Math.max(1, edlDurationFrames(props.edl)),
    fps: props.edl.output.fps,
    width: props.edl.output.width,
    height: props.edl.output.height,
  };
}

const defaultProps: EdlProps = { edl: null, sourceUrl: null };

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="LINKEDIN_16_9"
        component={LinkedinLongForm}
        durationInFrames={30 * 30}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={defaultProps}
        calculateMetadata={metadataFromEdl}
      />
      <Composition
        id="YT_SHORTS_9_16"
        component={YouTubeShorts}
        durationInFrames={45 * 30}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={defaultProps}
        calculateMetadata={metadataFromEdl}
      />
      <Composition
        id="TIKTOK_9_16"
        component={TikTokVertical}
        durationInFrames={45 * 30}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={defaultProps}
        calculateMetadata={metadataFromEdl}
      />
      <Composition
        id="YT_LONG_16_9"
        component={YouTubeLong}
        durationInFrames={60 * 30}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={defaultProps}
        calculateMetadata={metadataFromEdl}
      />
    </>
  );
};
