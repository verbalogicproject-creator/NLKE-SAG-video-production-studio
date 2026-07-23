import { createHash } from 'node:crypto';
import type { BrandContract, VerticalVariant } from '@verbalogix/media-contracts';
import { db } from '@/lib/db';

const VARIANTS: VerticalVariant[] = ['YT_SHORTS_9_16', 'TIKTOK_9_16', 'IG_REELS_9_16'];

export async function resolveBrandContract(workspaceId: string): Promise<BrandContract> {
  const skill = await db.brandSkill.findUnique({ where: { workspaceId } });
  const rules = parseBrandSkill(skill?.markdown ?? '');
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

function parseBrandSkill(markdown: string) {
  const sections: Record<string, string> = {};
  const matches = [...markdown.matchAll(/^#{2,3}\s+(.+?)\s*$/gm)];
  matches.forEach((match, index) => {
    const start = (match.index ?? 0) + match[0].length;
    sections[String(match[1]).trim().toLowerCase()] = markdown.slice(start, matches[index + 1]?.index ?? markdown.length).trim();
  });
  const keyValues = (body: string) => Object.fromEntries(body.split('\n').flatMap((line) => {
    const match = /^\s*-?\s*([a-z0-9_-]+)\s*:\s*(.+)\s*$/i.exec(line);
    return match ? [[match[1]!.toLowerCase(), match[2]!.trim()]] : [];
  }));
  const palette = keyValues(sections.palette ?? '');
  const typography = keyValues(sections.typography ?? '');
  const bullets = (body: string) => body.split('\n').map((line) => line.replace(/^\s*[-*]\s*/, '').trim()).filter(Boolean);
  const perVariant = Object.fromEntries(VARIANTS.flatMap((variant) => {
    const names: Record<VerticalVariant, string[]> = {
      YT_SHORTS_9_16: ['youtube shorts', 'shorts'], TIKTOK_9_16: ['tiktok'], IG_REELS_9_16: ['instagram reels', 'reels'],
    };
    const heading = names[variant].find((name) => sections[name]);
    const values = keyValues(heading ? sections[heading]! : '');
    return values['required-footer'] ? [[variant, { requiredFooter: values['required-footer'] }]] : [];
  }));
  return {
    forbiddenPhrases: bullets(sections['forbidden phrases'] ?? ''),
    palette: { primary: palette.primary, accent: palette.accent, background: palette.background, text: palette.text },
    typography: { bodyFontStack: (typography.body ?? '').split(',').map((value) => value.trim()).filter(Boolean) },
    perVariant,
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
