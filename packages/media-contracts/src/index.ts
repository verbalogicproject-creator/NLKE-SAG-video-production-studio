import { z } from 'zod';

export const VerticalVariantSchema = z.enum([
  'YT_SHORTS_9_16',
  'TIKTOK_9_16',
  'IG_REELS_9_16',
]);
export type VerticalVariant = z.infer<typeof VerticalVariantSchema>;

export const BrandContractSchema = z.object({
  version: z.number().int().positive(),
  contract_hash: z.string(),
  forbidden_phrases: z.array(z.string()).default([]),
  required_disclosures: z.record(z.string()).default({}),
  palette: z.array(z.string()).default([]),
  font_family: z.string().default('Noto Sans'),
  caption_preset: z.enum(['bold_pop', 'clean', 'minimal']).default('bold_pop'),
  text_color: z.string().default('#FFFFFF'),
  highlight_color: z.string().default('#F8E71C'),
  background_color: z.string().default('#000000B8'),
});
export type BrandContract = z.infer<typeof BrandContractSchema>;

export const DraftPlanSchema = z.object({
  contract_version: z.literal('chamber-draft-1.0'),
  target_variant: VerticalVariantSchema,
  source_project_id: z.string(),
  source_revision: z.number().int().positive(),
  source_asset_id: z.string(),
  source_sha256: z.string(),
  scenes: z.array(z.object({
    source_start_ticks: z.number().int().nonnegative(),
    source_end_ticks: z.number().int().positive(),
    word_ids: z.array(z.string()).min(1),
  })).min(1),
  hook_title: z.string().nullable().optional(),
  post_copy: z.string(),
  hashtags: z.array(z.string()),
  caption_register: z.enum(['casual', 'hook-first', 'polished']),
  score: z.number().min(0).max(100),
  score_components: z.record(z.number()),
  reason: z.string(),
  brand_version: z.number().int().positive(),
  brand_hash: z.string(),
  provider: z.record(z.unknown()),
  warnings: z.array(z.string()),
});
export type DraftPlan = z.infer<typeof DraftPlanSchema>;

export type EngineJob = {
  id: string;
  project_id: string;
  project_revision: number;
  kind: string;
  state: string;
  progress: number;
  stage?: string | null;
  status_message?: string | null;
  result_artifact_id?: string | null;
  error_code?: string | null;
  error_detail?: string | null;
};

export type EngineSuggestion = {
  id: string;
  project_id: string;
  source_revision: number;
  generator_kind: string;
  state: string;
  reason: string;
  confidence: number | null;
  job_id: string | null;
  evidence: {
    target_variant?: VerticalVariant | null;
    draft_plan?: DraftPlan | null;
    brand_violations?: Array<Record<string, unknown>>;
    words?: Array<Record<string, unknown>>;
    [key: string]: unknown;
  };
};

export type ChamberStartRequest = {
  sourceAssetId: string;
  engineProjectId: string;
  sourceRevision: number;
  sourceSha256: string;
  variants?: VerticalVariant[];
  language?: 'auto' | 'en' | 'he';
  prompt?: string;
};
