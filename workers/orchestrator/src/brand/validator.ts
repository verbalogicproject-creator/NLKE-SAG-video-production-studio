import type { Edl, BrandRules } from '@verbalogix/lab-sdk';

/**
 * Brand-consistency runtime gate. Runs BEFORE the renderer produces pixels.
 * A render that fails validation has its RenderJob marked
 * HALTED_BRAND_VIOLATION and the worker moves on — no uploaded content,
 * no wasted GPU/CPU, no "oops we shipped 'game-changing' in a caption."
 *
 * The point is not to write a perfect brand safety net; it's to catch the
 * obvious violations that make an agency look amateur and give the atomizer
 * a reason to re-generate with tighter constraints.
 */

export type Violation = {
  severity: 'error' | 'warn';
  rule: string;
  message: string;
  /** Optional pointer into the EDL for UI highlighting */
  path?: string;
};

export type ValidationResult = {
  valid: boolean;
  violations: Violation[];
};

export function validateEdl(edl: Edl, brand: BrandRules): ValidationResult {
  const violations: Violation[] = [];

  // ── 1. Forbidden phrases in captions & post copy ───────────────
  if (brand.forbiddenPhrases.length > 0) {
    const lowerForbidden = brand.forbiddenPhrases.map((p) => p.toLowerCase());

    edl.captions.forEach((cap, ci) => {
      const text = cap.words.map((w) => w.text).join(' ').toLowerCase();
      for (const phrase of lowerForbidden) {
        if (text.includes(phrase)) {
          violations.push({
            severity: 'error',
            rule: 'forbidden-phrase',
            message: `Caption track #${ci + 1} contains forbidden phrase "${phrase}"`,
            path: `captions[${ci}]`,
          });
        }
      }
    });

    const postText = [
      edl.postCopy.title ?? '',
      edl.postCopy.description ?? '',
      ...(edl.postCopy.hashtags ?? []),
    ].join(' ').toLowerCase();

    for (const phrase of lowerForbidden) {
      if (postText.includes(phrase)) {
        violations.push({
          severity: 'error',
          rule: 'forbidden-phrase',
          message: `Post copy contains forbidden phrase "${phrase}"`,
          path: 'postCopy',
        });
      }
    }
  }

  // ── 2. Required footer for this variant ────────────────────────
  const variantRules = brand.perVariant[edl.variant];
  if (variantRules?.requiredFooter) {
    const footer = variantRules.requiredFooter.toLowerCase();
    const captionConcat = edl.captions
      .flatMap((c) => c.words.map((w) => w.text))
      .join(' ')
      .toLowerCase();
    const postConcat = (edl.postCopy.description ?? '').toLowerCase();
    if (!captionConcat.includes(footer) && !postConcat.includes(footer)) {
      violations.push({
        severity: 'error',
        rule: 'required-footer',
        message: `Missing required footer: "${variantRules.requiredFooter}"`,
        path: 'postCopy.description',
      });
    }
  }

  // ── 3. Hook-first-line rule ─────────────────────────────────────
  if (variantRules?.requireHookFirstLine) {
    const firstCaption = edl.captions[0];
    const firstWordsWindow = firstCaption?.words.slice(0, 12)
      .map((w) => w.text).join(' ') ?? '';
    // A "hook" is hard to detect rigorously; we heuristic: first line is
    // non-empty AND is NOT generic filler like "hello everyone" / "today i"
    const filler = /^(hello|hi|hey|today|so|um|uh|welcome)\b/i;
    if (!firstWordsWindow.trim()) {
      violations.push({
        severity: 'error',
        rule: 'hook-first-line',
        message: 'Variant requires a hook in the first caption line — no caption found.',
      });
    } else if (filler.test(firstWordsWindow)) {
      violations.push({
        severity: 'warn',
        rule: 'hook-first-line',
        message: `First-line copy starts with filler ("${firstWordsWindow.split(' ').slice(0, 3).join(' ')}…"). This is a hook-first variant.`,
      });
    }
  }

  // ── 4. Caption line length (karaoke variants care) ─────────────
  if (variantRules?.maxCharsPerLine) {
    const cap = variantRules.maxCharsPerLine;
    edl.captions.forEach((c, ci) => {
      // Group words by shared emphasis + approximate line breaks.
      // Approximation: each 4 words = 1 line.
      for (let i = 0; i < c.words.length; i += 4) {
        const chunk = c.words.slice(i, i + 4).map((w) => w.text).join(' ');
        if (chunk.length > cap) {
          violations.push({
            severity: 'warn',
            rule: 'max-chars-per-line',
            message: `Caption chunk "${chunk}" exceeds ${cap} chars for this variant.`,
            path: `captions[${ci}].words[${i}..${i + 4}]`,
          });
        }
      }
    });
  }

  const errorCount = violations.filter((v) => v.severity === 'error').length;
  return { valid: errorCount === 0, violations };
}
