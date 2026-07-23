export type PublishInput = {
  renderJobId: string;
  platforms: Array<'YOUTUBE' | 'LINKEDIN' | 'TIKTOK' | 'INSTAGRAM' | 'FACEBOOK'>;
};

/**
 * Publish a completed render to N platforms.
 *
 * For each platform:
 * 1. Load PlatformConnection for the render's workspace.
 * 2. Decrypt tokens via GCP KMS.
 * 3. Rewrite caption for the platform's tone/length register (Claude Sonnet).
 * 4. Upload via platform-specific API:
 *    - YouTube: Data API v3 resumable upload
 *    - LinkedIn: UGC Posts + video assets
 *    - TikTok (Sprint 2): Content Posting API
 *    - Instagram / FB (Sprint 2): Graph API
 * 5. Write PlatformPublication row with platformPostId + postUrl.
 *
 * Sprint 1 Week 3 implementation — YouTube + LinkedIn only.
 */
export async function publish(input: PublishInput): Promise<void> {
  console.log('[publish] stub', input);
  throw new Error('NotImplemented: publish — wire in Week 3');
}
