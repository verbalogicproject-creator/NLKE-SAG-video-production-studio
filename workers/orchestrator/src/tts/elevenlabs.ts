/**
 * ElevenLabs — voice cloning + 29-language dubbing. OPT-IN only.
 * Used when the project explicitly requests a workspace-cloned voice.
 *
 * Feature #2 "Voice-Consistent Auto-Dub" lives here. Deprioritized after
 * China market was dropped, but kept as an opt-in escalation path for
 * Spanish / Portuguese / etc.
 */

export type ElevenLabsOptions = {
  text: string;
  /** ElevenLabs voice_id for the workspace's cloned voice */
  voiceId: string;
  /** Target language code for cross-lingual synthesis */
  language?: string;
  modelId?: 'eleven_multilingual_v2' | 'eleven_turbo_v2_5';
};

export async function synthesizeElevenLabs(opts: ElevenLabsOptions, outPath: string): Promise<string> {
  console.log('[elevenlabs] stub', opts, outPath);
  throw new Error('NotImplemented: synthesizeElevenLabs — enable in a later sprint');
}
