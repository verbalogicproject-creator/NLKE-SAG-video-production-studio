import {
  BrandRulesSchema,
  type BrandRules,
  type Palette,
  type CaptionRegisterRules,
} from '@verbalogix/lab-sdk';
import type { PlatformVariant } from '@verbalogix/lab-sdk';

/**
 * Parse a workspace's brand.skill.md into a validated BrandRules object.
 *
 * The skill markdown is hand-authored and forgiving — we tolerate missing
 * sections, reordered headings, and case mismatches. What we DON'T tolerate:
 * invalid hex colors or malformed section bodies. Those throw via Zod.
 *
 * Expected headings (case-insensitive, any H2/H3):
 *   ## Palette
 *     - primary: #0a0e1a
 *     - accent:  #ffb224
 *   ## Typography
 *     display: Söhne, Geist, system-ui
 *     body:    Söhne, system-ui
 *   ## Tone of voice
 *     - Direct, technical, confident.
 *   ## Forbidden phrases
 *     - revolutionary
 *     - game-changing
 *   ## Per-platform caption register
 *     ### LinkedIn
 *       tone: professional, 30–90s
 *       require-hook-first-line: true
 *       required-footer: Read the full build log at verbalogix.com
 */

const VARIANT_ALIASES: Record<string, PlatformVariant> = {
  linkedin:         'LINKEDIN_16_9',
  'linked in':      'LINKEDIN_16_9',
  'linkedin 16:9':  'LINKEDIN_16_9',
  'youtube long':   'YT_LONG_16_9',
  'youtube':        'YT_LONG_16_9',
  'youtube shorts': 'YT_SHORTS_9_16',
  'shorts':         'YT_SHORTS_9_16',
  tiktok:           'TIKTOK_9_16',
  instagram:        'IG_REELS_9_16',
  'ig reels':       'IG_REELS_9_16',
  reels:            'IG_REELS_9_16',
  facebook:         'FB_FEED_16_9',
  fb:               'FB_FEED_16_9',
};

export function parseBrandSkill(markdown: string, brand = 'Untitled Brand'): BrandRules {
  const sections = splitSections(markdown, /^(#{2,3})\s+(.+?)\s*$/gm);

  const palette = parsePalette(sections);
  const typography = parseTypography(sections);
  const forbiddenPhrases = parseBulletList(sections['forbidden phrases'] ?? '');
  const toneSamples = parseBulletList(sections['tone of voice'] ?? sections['tone'] ?? '');
  const perVariant = parsePerVariant(
    sections['per-platform caption register'] ??
    sections['per platform caption register'] ??
    '',
  );

  return BrandRulesSchema.parse({
    brand,
    palette,
    typography,
    forbiddenPhrases,
    toneSamples,
    perVariant,
  });
}

// ─── Internals ───────────────────────────────────────────────────────

type SectionMap = Record<string, string>;

/**
 * Split markdown into a map keyed by lowercase heading text. Works for H2
 * or H3 headings (caller provides the regex so the same helper parses the
 * top-level and per-variant sub-sections).
 */
function splitSections(markdown: string, headingRe: RegExp): SectionMap {
  const matches = Array.from(markdown.matchAll(headingRe));
  const out: SectionMap = {};
  for (let i = 0; i < matches.length; i++) {
    const m = matches[i]!;
    const name = (m[2] ?? '').trim().toLowerCase();
    const bodyStart = (m.index ?? 0) + m[0]!.length;
    const next = matches[i + 1];
    const bodyEnd = next ? (next.index ?? markdown.length) : markdown.length;
    out[name] = markdown.slice(bodyStart, bodyEnd).trim();
  }
  return out;
}

function parseBulletList(body: string): string[] {
  return body
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.startsWith('-') || l.startsWith('*'))
    .map((l) => l.replace(/^[-*]\s*/, '').replace(/^["'`]|["'`]$/g, '').trim())
    .filter(Boolean);
}

function parseKvBlock(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of body.split('\n')) {
    const t = line.trim().replace(/^-\s*/, '');
    const m = /^([a-z0-9\-_ ]+)\s*:\s*(.+)$/i.exec(t);
    if (!m) continue;
    const key = m[1]!.trim().toLowerCase();
    const val = m[2]!.trim();
    out[key] = val;
  }
  return out;
}

function parsePalette(sections: SectionMap): Palette {
  const body = sections['palette'] ?? '';
  const kv = parseKvBlock(body);
  const out: Palette = { custom: {} };
  for (const [k, v] of Object.entries(kv)) {
    const normalized = v.split(/\s+/)[0]!.toLowerCase();
    switch (k) {
      case 'primary':    out.primary    = normalized; break;
      case 'accent':     out.accent     = normalized; break;
      case 'background': out.background = normalized; break;
      case 'text':       out.text       = normalized; break;
      case 'signal-ok':
      case 'signalok':   out.signalOk   = normalized; break;
      case 'signal-live':
      case 'signallive': out.signalLive = normalized; break;
      default:
        out.custom![k] = normalized;
    }
  }
  return out;
}

function parseTypography(sections: SectionMap) {
  const body = sections['typography'] ?? '';
  const kv = parseKvBlock(body);
  const toStack = (s?: string) =>
    s ? s.split(',').map((t) => t.trim().replace(/^['"]|['"]$/g, '')).filter(Boolean) : [];
  return {
    displayFontStack: toStack(kv['display']),
    bodyFontStack:    toStack(kv['body']),
    monoFontStack:    toStack(kv['mono']),
  };
}

function parsePerVariant(body: string): Partial<Record<PlatformVariant, CaptionRegisterRules>> {
  if (!body.trim()) return {};
  const out: Partial<Record<PlatformVariant, CaptionRegisterRules>> = {};
  const sub = splitSections(body, /^###\s+(.+?)\s*$/gm);

  for (const [rawKey, subBody] of Object.entries(sub)) {
    const variant = VARIANT_ALIASES[rawKey];
    if (!variant) continue;
    const kv = parseKvBlock(subBody);
    out[variant] = {
      tone: kv['tone'],
      maxCharsPerLine: kv['max-chars-per-line']
        ? Number(kv['max-chars-per-line'])
        : undefined,
      requireHookFirstLine:
        kv['require-hook-first-line'] === 'true' ||
        kv['require-hook-first-line'] === 'yes',
      requiredFooter: kv['required-footer'],
    };
  }

  return out;
}
