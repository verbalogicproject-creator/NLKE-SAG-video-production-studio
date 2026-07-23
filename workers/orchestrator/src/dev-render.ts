/**
 * dev-render.ts — Local render harness.
 *
 * Usage:
 *   pnpm tsx src/dev-render.ts <edl.json> <sourceUrl> <out.mp4>
 *
 * Produces a real MP4 from a JSON EDL + a source video URL, without needing
 * the pg-boss queue, R2 credentials, or the DB to be wired. This is how you
 * iterate on Remotion compositions during Week 2 before the job pipeline is
 * running end-to-end.
 *
 * Example:
 *   pnpm tsx src/dev-render.ts fixtures/sample.edl.json \
 *     https://file-examples.com/.../sample-video.mp4 \
 *     out/sample-shorts.mp4
 */

import { readFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { bundle } from '@remotion/bundler';
import { renderMedia, selectComposition } from '@remotion/renderer';
import { EdlSchema } from '@verbalogix/lab-sdk';

async function main() {
  const [edlPath, sourceUrl, outPath] = process.argv.slice(2);
  if (!edlPath || !sourceUrl || !outPath) {
    console.error('usage: dev-render.ts <edl.json> <sourceUrl> <out.mp4>');
    process.exit(1);
  }

  const edlRaw = JSON.parse(readFileSync(resolve(edlPath), 'utf-8'));
  const edl = EdlSchema.parse(edlRaw);

  mkdirSync(dirname(resolve(outPath)), { recursive: true });

  console.log('[dev-render] bundling Remotion project…');
  const bundled = await bundle({
    entryPoint: resolve(__dirname, 'remotion/index.ts'),
    webpackOverride: (c) => c,
  });

  console.log(`[dev-render] selecting composition ${edl.variant}…`);
  const composition = await selectComposition({
    serveUrl: bundled,
    id: edl.variant,
    inputProps: { edl, sourceUrl },
  });

  console.log(`[dev-render] rendering ${composition.durationInFrames} frames at ${composition.fps}fps…`);
  await renderMedia({
    composition,
    serveUrl: bundled,
    codec: edl.output.codec === 'h265' ? 'h265' : 'h264',
    outputLocation: resolve(outPath),
    inputProps: { edl, sourceUrl },
    crf: edl.output.crf,
  });

  console.log(`[dev-render] wrote ${outPath}`);
}

main().catch((err) => {
  console.error('[dev-render] FAILED:', err);
  process.exit(1);
});
