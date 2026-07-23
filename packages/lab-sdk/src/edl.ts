import { z } from 'zod';

/**
 * Edit Decision List — the contract between the atomizer and the renderer.
 *
 * The atomizer (Claude Opus 4.7) reads a transcript + brand skill + project
 * metadata and emits one EDL per PlatformVariant. The render worker reads
 * the EDL and drives a Remotion composition to produce the final MP4.
 *
 * Design principles:
 * 1. Every timestamp is milliseconds from the ORIGINAL source clip (not the
 *    output timeline). The renderer maps source-ms → output-frames.
 * 2. Captions carry word-level timing so platform-specific caption styles
 *    (TikTok karaoke vs LinkedIn blocks) can share one EDL.
 * 3. Visual + audio are decoupled: an EDL can reference a source video, a
 *    different audio bed, and stock B-roll overlays independently.
 * 4. The EDL is self-contained — a renderer should never need to re-read
 *    the transcript or consult the brand skill directly (the atomizer
 *    already did that work).
 */

// ─── Primitives ─────────────────────────────────────────────────────

export const MillisecondsSchema = z.number().int().nonnegative();
export const NormalizedSchema = z.number().min(0).max(1); // 0..1 for positions / opacities

export const PlatformVariantSchema = z.enum([
  'LINKEDIN_16_9',
  'YT_LONG_16_9',
  'YT_SHORTS_9_16',
  'TIKTOK_9_16',
  'IG_REELS_9_16',
  'FB_FEED_16_9',
]);
export type PlatformVariant = z.infer<typeof PlatformVariantSchema>;

// ─── Source segment ─────────────────────────────────────────────────
// A slice of the original raw video the editor wants to keep.

export const SceneSchema = z.object({
  /** Source-clip start, ms */
  sourceStartMs: MillisecondsSchema,
  /** Source-clip end, ms (exclusive) */
  sourceEndMs: MillisecondsSchema,
  /** Optional crop/zoom within the source frame */
  crop: z
    .object({
      x: NormalizedSchema,        // 0..1 left edge
      y: NormalizedSchema,        // 0..1 top edge
      width: NormalizedSchema,    // 0..1 width
      height: NormalizedSchema,   // 0..1 height
    })
    .optional(),
  /** Playback speed multiplier; 1 = normal, 1.5 = 1.5x */
  speed: z.number().positive().default(1),
  /** Optional transition OUT of this scene into the next */
  transition: z.enum(['cut', 'fade', 'wipe', 'dip']).default('cut'),
  /** Optional transition duration in ms */
  transitionDurationMs: MillisecondsSchema.default(0),
}).refine((s) => s.sourceEndMs > s.sourceStartMs, {
  message: 'sourceEndMs must be greater than sourceStartMs',
});

// ─── Caption track ──────────────────────────────────────────────────
// Captions live on the OUTPUT timeline (not the source timeline) because
// the atomizer may rewrite wording or add hooks not present in the source.

export const CaptionWordSchema = z.object({
  /** Output-timeline start, ms */
  startMs: MillisecondsSchema,
  /** Output-timeline end, ms */
  endMs: MillisecondsSchema,
  text: z.string().min(1),
  /** Visual emphasis for word-by-word karaoke styling */
  emphasis: z.enum(['none', 'primary', 'accent']).default('none'),
});
export type CaptionWord = z.infer<typeof CaptionWordSchema>;

export const CaptionSchema = z.object({
  style: z.enum([
    'block',       // LinkedIn / YT long — static 2-line blocks
    'karaoke',     // TikTok / Shorts — word-by-word highlight
    'ticker',      // bottom ticker for news-style
  ]),
  /** Per-word timing for karaoke; block/ticker styles concatenate whole lines */
  words: z.array(CaptionWordSchema).min(1),
  /** Position on the output frame, normalized 0..1 */
  position: z.object({
    x: NormalizedSchema.default(0.5),
    y: NormalizedSchema.default(0.85),
    anchor: z.enum(['top-left', 'center', 'bottom-center', 'bottom-left']).default('center'),
  }).default({}),
  /** Override colors (else falls back to brand palette) */
  fillColor: z.string().optional(),          // CSS hex
  highlightColor: z.string().optional(),
  strokeColor: z.string().optional(),
});
export type Caption = z.infer<typeof CaptionSchema>;

// ─── Audio ──────────────────────────────────────────────────────────

export const AudioTrackSchema = z.object({
  /** 'source' = use the raw clip's audio; 'external' = use a separate asset */
  kind: z.enum(['source', 'external', 'tts']),
  /** R2 key for external / tts audio (tts renders to R2 first) */
  r2Key: z.string().optional(),
  /** Volume 0..1 */
  gain: NormalizedSchema.default(1),
  /** Duck when captions are speaking? */
  duckUnderSpeech: z.boolean().default(false),
});
export type AudioTrack = z.infer<typeof AudioTrackSchema>;

// ─── B-roll overlays (Sprint 2+ feature, schema-ready now) ─────────

export const OverlaySchema = z.object({
  /** Output-timeline window when this overlay is visible */
  startMs: MillisecondsSchema,
  endMs: MillisecondsSchema,
  kind: z.enum(['image', 'video', 'shape', 'text']),
  r2Key: z.string().optional(),       // for image/video
  text: z.string().optional(),         // for text kind
  /** Normalized position + size */
  box: z.object({
    x: NormalizedSchema,
    y: NormalizedSchema,
    width: NormalizedSchema,
    height: NormalizedSchema,
  }),
  opacity: NormalizedSchema.default(1),
});

// ─── Output spec ────────────────────────────────────────────────────

export const OutputSpecSchema = z.object({
  width: z.number().int().positive(),
  height: z.number().int().positive(),
  fps: z.number().int().positive().default(30),
  codec: z.enum(['h264', 'h265']).default('h264'),
  /** Target bitrate in kbps; 0 = CRF-based */
  bitrateKbps: z.number().int().nonnegative().default(0),
  /** CRF quality (18–28 reasonable); only used when bitrateKbps=0 */
  crf: z.number().int().min(0).max(51).default(23),
});

// ─── Root EDL ───────────────────────────────────────────────────────

export const EdlSchema = z.object({
  /** Semantic versioning; bump when the schema breaks compatibility */
  version: z.literal('1.0.0'),
  /** The platform variant this EDL targets */
  variant: PlatformVariantSchema,
  /** R2 key for the source raw video */
  sourceR2Key: z.string().min(1),
  /** Short human-readable hook summarizing why THIS variant was cut this way */
  hookSummary: z.string().min(1).max(500),
  /** Sequential scenes composed into the final cut */
  scenes: z.array(SceneSchema).min(1),
  /** One or more caption tracks (usually just one) */
  captions: z.array(CaptionSchema).default([]),
  /** Audio track — source, external bed, or TTS narration */
  audio: AudioTrackSchema,
  /** Optional B-roll/graphic overlays */
  overlays: z.array(OverlaySchema).default([]),
  /** Output encoding spec */
  output: OutputSpecSchema,
  /** Per-platform caption register hint so the renderer can pick styling */
  captionRegister: z.enum(['professional', 'casual', 'hook-first', 'chaptered']).default('casual'),
  /** Post-publish copy: the post body/description for the platform */
  postCopy: z.object({
    title: z.string().max(200).optional(),
    description: z.string().max(5000).optional(),
    hashtags: z.array(z.string()).default([]),
  }).default({}),
});
export type Edl = z.infer<typeof EdlSchema>;

// ─── Canonical output-spec helper ───────────────────────────────────
// Convenience: default output specs per platform variant.

export const DEFAULT_OUTPUT: Record<PlatformVariant, z.input<typeof OutputSpecSchema>> = {
  LINKEDIN_16_9:  { width: 1920, height: 1080, fps: 30, codec: 'h264', bitrateKbps: 0, crf: 23 },
  YT_LONG_16_9:   { width: 1920, height: 1080, fps: 30, codec: 'h264', bitrateKbps: 0, crf: 20 },
  YT_SHORTS_9_16: { width: 1080, height: 1920, fps: 30, codec: 'h264', bitrateKbps: 0, crf: 22 },
  TIKTOK_9_16:    { width: 1080, height: 1920, fps: 30, codec: 'h264', bitrateKbps: 0, crf: 22 },
  IG_REELS_9_16:  { width: 1080, height: 1920, fps: 30, codec: 'h264', bitrateKbps: 0, crf: 22 },
  FB_FEED_16_9:   { width: 1920, height: 1080, fps: 30, codec: 'h264', bitrateKbps: 0, crf: 23 },
};

/** Total output duration in ms based on scenes + speed */
export function edlDurationMs(edl: Edl): number {
  return edl.scenes.reduce((sum, s) => {
    const raw = s.sourceEndMs - s.sourceStartMs;
    return sum + Math.round(raw / s.speed);
  }, 0);
}

/** Total output duration in frames (rounded) */
export function edlDurationFrames(edl: Edl): number {
  return Math.round((edlDurationMs(edl) / 1000) * edl.output.fps);
}
