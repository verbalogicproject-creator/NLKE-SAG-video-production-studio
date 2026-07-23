import { createHash } from 'node:crypto';
import { parseBrandSkill } from '@verbalogix/lab-sdk';
import type { BrandContract, VerticalVariant } from '@verbalogix/media-contracts';
import { db } from '@/lib/db';

const VARIANTS: VerticalVariant[] = ['YT_SHORTS_9_16', 'TIKTOK_9_16', 'IG_REELS_9_16'];

export async function resolveBrandContract(workspaceId: string): Promise<BrandContract> {
  const skill = await db.brandSkill.findUnique({ where: { workspaceId } });
  const rules = parseBrandSkill(skill?.markdown ?? '', 'Local Chamber');
  const required_disclosures = Object.fromEntries(
    VARIANTS.flatMap((variant) => rules.perVariant[variant]?.requiredFooter
      ? [[variant, rules.perVariant[variant]!.requiredFooter!]]
      : []),
  );
  const colors = [rules.palette.primary, rules.palette.accent, rules.palette.background, rules.palette.text]
    .filter((value): value is string => Boolean(value));
  return {
    version: skill?.version ?? 1,
    contract_hash: createHash('sha256').update(skill?.markdown ?? '').digest('hex'),
    forbidden_phrases: rules.forbiddenPhrases,
    required_disclosures,
    palette: colors,
    font_family: rules.typography.bodyFontStack[0] ?? 'Noto Sans',
    caption_preset: 'bold_pop',
    text_color: normalizeColor(rules.palette.text, '#FFFFFF'),
    highlight_color: normalizeColor(rules.palette.accent, '#F8E71C'),
    background_color: `${normalizeColor(rules.palette.background, '#000000')}B8`,
  };
}

function normalizeColor(value: string | undefined, fallback: string): string {
  if (!value) return fallback;
  if (/^#[0-9a-f]{6}$/i.test(value)) return value.toUpperCase();
  if (/^#[0-9a-f]{3}$/i.test(value)) {
    return `#${value.slice(1).split('').map((part) => part.repeat(2)).join('')}`.toUpperCase();
  }
  return fallback;
}
