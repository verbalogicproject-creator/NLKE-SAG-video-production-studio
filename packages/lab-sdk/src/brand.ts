import { z } from 'zod';
const PlatformVariantSchema = z.enum(['YT_SHORTS_9_16', 'TIKTOK_9_16', 'IG_REELS_9_16']);

/**
 * BrandRules is the structured form of a workspace brand contract.
 *
 * Hand-authored markdown is friendlier for humans to maintain; this schema
 * is what candidate validation and rendering enforce at runtime.
 */

export const HexColorSchema = z
  .string()
  .regex(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i, 'Expected #rgb or #rrggbb');

export const PaletteSchema = z.object({
  primary: HexColorSchema.optional(),
  accent: HexColorSchema.optional(),
  background: HexColorSchema.optional(),
  text: HexColorSchema.optional(),
  signalOk: HexColorSchema.optional(),
  signalLive: HexColorSchema.optional(),
  /** Any additional named swatches the brand defines */
  custom: z.record(z.string(), HexColorSchema).default({}),
});
export type Palette = z.infer<typeof PaletteSchema>;

export const TypographySchema = z.object({
  displayFontStack: z.array(z.string()).default([]),
  bodyFontStack: z.array(z.string()).default([]),
  monoFontStack: z.array(z.string()).default([]),
});

export const CaptionRegisterRulesSchema = z.object({
  /** Human-language description of the tone an editorial provider should match. */
  tone: z.string().optional(),
  /** Hard character cap for caption text (useful for TikTok-style karaoke lines) */
  maxCharsPerLine: z.number().int().positive().optional(),
  /** Must the caption's first line contain a hook? */
  requireHookFirstLine: z.boolean().default(false),
  /** Required trailing CTA or legal footer text */
  requiredFooter: z.string().optional(),
});
export type CaptionRegisterRules = z.infer<typeof CaptionRegisterRulesSchema>;

export const BrandRulesSchema = z.object({
  /** Schema version for forward-compatibility */
  version: z.literal('1.0.0').default('1.0.0'),
  /** Human-readable brand name (mostly for debug logs + error messages) */
  brand: z.string().default('Untitled Brand'),
  palette: PaletteSchema.default({}),
  typography: TypographySchema.default({}),
  /**
   * Case-insensitive substrings that MUST NOT appear in caption text or
   * post copy. Used to halt renders before they upload.
   */
  forbiddenPhrases: z.array(z.string()).default([]),
  /**
   * Sample lines that exemplify the brand voice for provider-assisted ranking.
   */
  toneSamples: z.array(z.string()).default([]),
  /** Per-variant caption overrides. */
  perVariant: z
    .record(PlatformVariantSchema, CaptionRegisterRulesSchema)
    .default({}),
});
export type BrandRules = z.infer<typeof BrandRulesSchema>;

/** Produce an empty BrandRules object — safe default when no skill exists. */
export function emptyBrandRules(): BrandRules {
  return BrandRulesSchema.parse({});
}
