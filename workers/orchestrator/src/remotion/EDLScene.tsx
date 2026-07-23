import {
  AbsoluteFill,
  OffthreadVideo,
  Sequence,
  useVideoConfig,
} from 'remotion';
import type { Edl } from '@verbalogix/lab-sdk';

/**
 * EDLScene — renders one scene of an EDL.
 *
 * A scene is a slice of the source video (sourceStartMs → sourceEndMs)
 * played at an optional speed multiplier, with optional crop.
 * The containing EDLVideo component is responsible for sequencing scenes
 * in the output timeline via <Sequence from={...} durationInFrames={...}>.
 */

type Props = {
  /** R2 HTTPS URL (either presigned or public-CDN) for the source clip */
  sourceUrl: string;
  scene: Edl['scenes'][number];
};

export function EDLScene({ sourceUrl, scene }: Props) {
  const { fps, width, height } = useVideoConfig();

  // Remotion's OffthreadVideo wants a source media time in seconds.
  const startFrom = scene.sourceStartMs / 1000;
  const endAt = scene.sourceEndMs / 1000;

  const { crop } = scene;

  const cropStyle: React.CSSProperties = crop
    ? {
        width:  width  / crop.width,
        height: height / crop.height,
        position: 'absolute',
        left: -(crop.x * (width  / crop.width)),
        top:  -(crop.y * (height / crop.height)),
      }
    : { width, height };

  return (
    <AbsoluteFill style={{ overflow: 'hidden', background: '#000' }}>
      <OffthreadVideo
        src={sourceUrl}
        startFrom={Math.round(startFrom * fps)}
        endAt={Math.round(endAt * fps)}
        playbackRate={scene.speed}
        style={cropStyle}
        muted={false}
      />
    </AbsoluteFill>
  );
}

/** Render a full EDL as a sequenced timeline of scenes. */
export function EDLVideo({ edl, sourceUrl }: { edl: Edl; sourceUrl: string }) {
  const { fps } = useVideoConfig();
  let cursorFrames = 0;

  return (
    <AbsoluteFill>
      {edl.scenes.map((scene, i) => {
        const rawDurMs = scene.sourceEndMs - scene.sourceStartMs;
        const outDurMs = Math.round(rawDurMs / scene.speed);
        const durationInFrames = Math.max(1, Math.round((outDurMs / 1000) * fps));
        const from = cursorFrames;
        cursorFrames += durationInFrames;
        return (
          <Sequence
            key={i}
            from={from}
            durationInFrames={durationInFrames}
          >
            <EDLScene sourceUrl={sourceUrl} scene={scene} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
}
