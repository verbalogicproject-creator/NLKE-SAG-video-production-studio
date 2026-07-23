export { LabClient, LabClientError } from './client.js';
export type { LabClientOptions } from './client.js';
export type * from './types.js';

// EDL + Brand — shared contracts between web, worker, and SDK consumers.
export {
  EdlSchema,
  SceneSchema,
  CaptionSchema,
  CaptionWordSchema,
  AudioTrackSchema,
  OverlaySchema,
  OutputSpecSchema,
  PlatformVariantSchema,
  DEFAULT_OUTPUT,
  edlDurationMs,
  edlDurationFrames,
} from './edl.js';
export type { Edl, Caption, CaptionWord, AudioTrack } from './edl.js';

export {
  BrandRulesSchema,
  PaletteSchema,
  TypographySchema,
  CaptionRegisterRulesSchema,
  HexColorSchema,
  emptyBrandRules,
} from './brand.js';
export type { BrandRules, Palette, CaptionRegisterRules } from './brand.js';
export { parseBrandSkill } from './brand-parser.js';
