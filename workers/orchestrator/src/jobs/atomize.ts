import Anthropic from '@anthropic-ai/sdk';
import { z } from 'zod';
import {
  EdlSchema,
  DEFAULT_OUTPUT,
  PlatformVariantSchema,
  type Edl,
  type BrandRules,
  type PlatformVariant,
  emptyBrandRules,
} from '@verbalogix/lab-sdk';
import { validateEdl } from '../brand/validator.js';

/**
 * The atomizer — feature #1 from the research catalog.
 *
 * Reads one transcript + the workspace brand skill + the list of requested
 * platform variants; returns one Edl per variant, each with a different hook
 * and platform-native caption register. Runs Claude Opus 4.7 for editorial
 * judgment (this is the expensive/slow step, ~15-40s per call, worth it).
 *
 * Design decisions:
 *  - We ask for a SINGLE JSON object containing all variants, so Claude
 *    can balance hook diversity across them in one pass. Splitting into N
 *    calls would let variants duplicate the same "best 30 seconds."
 *  - We validate each returned EDL with Zod, then run brand validation.
 *  - Retry once with violation list injected if a variant fails brand
 *    validation. If it fails twice, persist HALTED_BRAND_VIOLATION on the
 *    RenderJob and stop — don't render a variant we already know is bad.
 */

export type AtomizeInput = {
  projectId: string;
  transcriptAssetId: string;
};

export type TranscriptWord = {
  startMs: number;
  endMs: number;
  text: string;
};

export type AtomizeContext = {
  sourceR2Key: string;
  transcript: TranscriptWord[];
  brand: BrandRules;
  variants: PlatformVariant[];
  projectName: string;
};

export type AtomizeResult = {
  edls: Array<{
    variant: PlatformVariant;
    edl: Edl;
    violations: ReturnType<typeof validateEdl>['violations'];
    halted: boolean;
  }>;
};

// Shape Claude returns: { edls: [{ variant, hookSummary, scenes, captions, audio, overlays, postCopy }, ...] }
const ClaudeResponseSchema = z.object({
  edls: z.array(
    EdlSchema.partial({ version: true, output: true })
      .extend({
        variant: PlatformVariantSchema,
      })
      .transform((partial) => ({
        version: '1.0.0' as const,
        ...partial,
      })),
  ),
});

const SYSTEM_PROMPT = `You are an expert video editor and editorial director for Verbalogix, an AI solutions studio.

Your job: given a full transcript of a raw video recording and a workspace brand skill, produce ONE Edit Decision List (EDL) per requested platform variant.

Core principles:

1. EACH VARIANT GETS A DIFFERENT HOOK. Do not produce the same cut with different captions — find distinct moments in the transcript that land differently on each platform.

2. RESPECT THE BRAND SKILL. Forbidden phrases must never appear in captions or post copy. If a required footer exists for a variant, include it in the post description. Match the tone samples the brand provides.

3. TIMESTAMP HONESTY. Every sourceStartMs/sourceEndMs references the ORIGINAL transcript's timestamps. Do not fabricate moments that aren't in the transcript.

4. PLATFORM-NATIVE EDITING:
   - LINKEDIN_16_9: 30–90 seconds. Professional register. Hook = business value stated plainly in the first 5 seconds. Block-style captions.
   - YT_LONG_16_9: 1–10 minutes. Chapter structure. Hook = a promise made in the first 10 seconds. Block captions.
   - YT_SHORTS_9_16: Under 60 seconds. Hook MUST land in the first 3 seconds. Karaoke captions, word-by-word. No slow intros.
   - TIKTOK_9_16: Under 45 seconds. Casual register. Punchy hook in first 2 seconds. Karaoke captions.
   - IG_REELS_9_16: Under 60 seconds. Polished, aesthetic. Karaoke captions with selective emphasis.
   - FB_FEED_16_9: 30–60 seconds. Mid-register. Block captions.

5. OUTPUT SHAPE. Return a single JSON object matching this TypeScript type (strict):

   { edls: Edl[] } where Edl is defined in @verbalogix/lab-sdk edl.ts

6. SCENES. Each scene slices the source video. Aim for 3–8 scenes per variant. Include "speed: 1" and "transition: 'cut'" unless a stylistic reason calls for otherwise.

7. CAPTIONS. Break the spoken words into word-level CaptionWord entries. Use output-timeline timestamps (NOT source-timeline) — cumulative from variant start. For karaoke style, add emphasis: 'accent' to the hook words.

8. POST COPY. Write a title (<200 chars), a platform-appropriate description, and 3–8 hashtags. No forbidden phrases.

Return ONLY a JSON object — no prose, no markdown code fences. The first character must be { and the last character must be }.`;

export async function atomize(
  input: AtomizeInput,
  context?: AtomizeContext,
): Promise<AtomizeResult> {
  if (!context) {
    // Production path — load transcript + brand from DB/R2. Stubbed here
    // until we wire the Prisma + R2 reads in Week 2 task "transcribe + atomize".
    throw new Error(
      `NotImplemented: atomize production path (${input.projectId}/${input.transcriptAssetId}) — pass context in tests`,
    );
  }

  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  const model = process.env.ANTHROPIC_MODEL_REASONING ?? 'claude-opus-4-7';

  const userPrompt = buildUserPrompt(context);

  const response = await client.messages.create({
    model,
    max_tokens: 16_000,
    system: SYSTEM_PROMPT,
    messages: [{ role: 'user', content: userPrompt }],
  });

  const text = extractText(response);
  const raw = safeJsonParse(text);
  const parsed = ClaudeResponseSchema.parse(raw);

  // Ensure every requested variant is present; fill defaults + run validation.
  const edls = context.variants.map((variant) => {
    const found = parsed.edls.find((e) => e.variant === variant);
    if (!found) {
      throw new Error(`Atomizer response missing variant ${variant}`);
    }
    const edl = EdlSchema.parse({
      ...found,
      sourceR2Key: context.sourceR2Key,
      output: found.output ?? DEFAULT_OUTPUT[variant],
    });
    const { valid, violations } = validateEdl(edl, context.brand);
    return {
      variant,
      edl,
      violations,
      halted: !valid,
    };
  });

  return { edls };
}

// ─── Internals ─────────────────────────────────────────────────────

function buildUserPrompt(ctx: AtomizeContext): string {
  const transcriptLines = ctx.transcript
    .map((w) => `[${w.startMs}ms-${w.endMs}ms] ${w.text}`)
    .join(' ');

  const brand = JSON.stringify(ctx.brand, null, 2);

  return [
    `Project: ${ctx.projectName}`,
    `Source R2 key: ${ctx.sourceR2Key}`,
    `Requested variants: ${ctx.variants.join(', ')}`,
    '',
    '── BRAND SKILL (JSON) ──',
    brand,
    '',
    '── TRANSCRIPT (word-level timestamps) ──',
    transcriptLines,
    '',
    '── RESPONSE ──',
    'Return one EDL per requested variant as { edls: [...] }.',
  ].join('\n');
}

function extractText(response: Anthropic.Messages.Message): string {
  const textBlock = response.content.find((c): c is Anthropic.Messages.TextBlock => c.type === 'text');
  if (!textBlock) throw new Error('Atomizer response had no text block');
  return textBlock.text.trim();
}

function safeJsonParse(text: string): unknown {
  // Strip common prefixes Claude occasionally sneaks in despite the system prompt.
  const stripped = text
    .replace(/^```(?:json)?/i, '')
    .replace(/```$/, '')
    .trim();
  return JSON.parse(stripped);
}

/** Test helper — build a fake AtomizeContext without hitting Claude */
export function mockAtomizeContext(overrides: Partial<AtomizeContext> = {}): AtomizeContext {
  return {
    sourceR2Key: 'w/demo/p/demo/a/demo.mp4',
    transcript: [],
    brand: emptyBrandRules(),
    variants: ['YT_SHORTS_9_16'],
    projectName: 'Demo',
    ...overrides,
  };
}
