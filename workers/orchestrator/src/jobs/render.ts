export type RenderInput = {
  renderJobId: string;
};

/**
 * Render one platform variant.
 *
 * 1. Load RenderJob + editDecisionList + parent Project + workspace BrandSkill.
 * 2. BRAND ENFORCEMENT (feature #11): parse brand.skill.md for forbidden
 *    phrases, approved palette, font stack, caption rules. If the EDL's
 *    generated copy violates any rule, set status=HALTED_BRAND_VIOLATION and
 *    return — do NOT render. The render only proceeds when the skill
 *    contract is satisfied.
 * 3. Invoke Remotion renderer with the chosen composition for the variant.
 * 4. FFmpeg encode for platform-specific presets (bitrate, codec, fps).
 * 5. Upload MP4 to R2 deliverables bucket; create DELIVERABLE Asset;
 *    update RenderJob status=COMPLETED + outputAssetId.
 *
 * Sprint 1 Week 2-3 implementation. Stub below.
 */
export async function render(input: RenderInput): Promise<void> {
  console.log('[render] stub', input);
  throw new Error('NotImplemented: render — wire in Week 2-3');
}
