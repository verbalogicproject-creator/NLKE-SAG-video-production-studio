/**
 * Gemini Live API — realtime, multilingual, paid (cheap). Quality upgrade over
 * Kokoro for talking-head narration. Used when project flag `tts: "gemini"`.
 *
 * Does NOT support voice cloning — escalate to ElevenLabs for that.
 */

export type GeminiTtsOptions = {
  text: string;
  /** BCP-47, e.g. "en-US", "es-ES" */
  language?: string;
  voiceName?: string;
};

export async function synthesizeGemini(opts: GeminiTtsOptions, outPath: string): Promise<string> {
  console.log('[gemini-tts] stub', opts, outPath);
  throw new Error('NotImplemented: synthesizeGemini — wire in Sprint 2');
}
