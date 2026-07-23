export type TranscribeInput = {
  projectId: string;
  assetId: string;
};

/**
 * Pull the RAW asset from R2 to /tmp, run whisper.cpp with word-level
 * timestamps, write the transcript JSON back to R2 as a TRANSCRIPT asset,
 * update the Asset row, then enqueue job.atomize.
 *
 * Sprint 1 Week 2 implementation. Stubbed here for scaffolding.
 */
export async function transcribe(input: TranscribeInput): Promise<void> {
  console.log('[transcribe] stub', input);
  throw new Error('NotImplemented: transcribe — wire in Week 2');
}
