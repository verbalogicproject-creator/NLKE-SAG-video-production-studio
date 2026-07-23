/**
 * Kokoro 82M — local ONNX TTS. FREE, ~8 English voices, CPU-only.
 *
 * This is the DEFAULT TTS in the routing hierarchy:
 *   Kokoro (default) → Gemini Live (quality upgrade) → ElevenLabs (voice clone only).
 *
 * Model is pre-downloaded during Docker build so the first job doesn't pay
 * the cost. KOKORO_MODEL_PATH points at the onnx files.
 */

export type KokoroVoice =
  | 'af_bella'
  | 'af_nicole'
  | 'am_michael'
  | 'am_adam'
  | 'bf_emma'
  | 'bf_isabella'
  | 'bm_george'
  | 'bm_lewis';

export type KokoroSynthOptions = {
  text: string;
  voice?: KokoroVoice;
  /** 0.5 – 2.0; default 1.0 */
  speed?: number;
};

/** Synthesize speech, write wav to `outPath`. Returns the output path. */
export async function synthesizeKokoro(opts: KokoroSynthOptions, outPath: string): Promise<string> {
  // Sprint 1 stub. Will shell-out to a short Python entrypoint that wraps
  // kokoro-onnx + soundfile, because official JS bindings aren't shipped yet.
  console.log('[kokoro] stub', opts, outPath);
  throw new Error('NotImplemented: synthesizeKokoro — wire in Week 2');
}
