# Speech-to-Text, Auto-Captioning & Automated Editing (Offline-Capable)

## Whisper bindings for Node/TypeScript
### whisper-node
- Node.js bindings for OpenAI's Whisper, **runs fully local on CPU** (including Apple Silicon ARM) — no cloud dependency, matching the offline requirement [web:117].
- Output formats: JSON, TXT, SRT, VTT; timestamp precision down to the single word [web:117].
- Install: `npm install whisper-node`, then `npx whisper-node download` to fetch a model locally [web:117].
- Usage: `const transcript = await whisper("sample.wav")` → returns `[{start, end, speech}]` array [web:117].

### node-whisper (Pnlvfx)
- A TypeScript package wrapping OpenAI's Whisper for speech-to-text [web:119].
- Install: `npm install node-whisper`.
- Usage: `whisper(audioFilePath, { output_format: 'all', output_dir: 'subtitles' })` → generates json/tsv/srt/txt/vtt caption files simultaneously [web:119].
- **Relevance**: Either whisper-node or node-whisper can power fully offline auto-captioning/subtitle generation directly inside the TypeScript app, feeding directly into Remotion `<Caption>`-style overlay components or burned-in subtitles via ffmpeg.wasm.

## Automated silence/jump-cut editing (Python, but architecturally relevant)
### auto-editor (WyattBlue/auto-editor)
- CLI tool for automatically editing video/audio by analyzing loudness, motion, or unrecognized speech; can output **trimmed MP4, FCPXML for DaVinci Resolve/Final Cut Pro, and SRT subtitles**, and is "Powered by whisper.cpp" in some derivative variants [web:116][web:122].
- Install: `pip install auto-editor`; basic usage `auto-editor video.mp4` [web:113][web:122].
- Key flags: `--edit motion:threshold=0.02` (cut on stillness instead of silence), `--margin 0.2sec` (padding around cuts), `--cut-out 0,30sec` / `--add-in` (manual force include/exclude ranges), `--export resolve` / `--export premiere` (round-trip into professional NLEs) [web:122][web:115].
- **Relevance**: Even though it's Python, it is directly invocable as a subprocess/CLI step from a TypeScript orchestration layer (e.g., Node `child_process`), making it a pragmatic way to add "auto-editing" (silence/dead-space removal) to the pipeline without reimplementing loudness/motion detection in TS. Its FCPXML export also gives a clean bridge to desktop NLEs for manual polish.

### jumpcutter (carykh / emkademy fork)
- Simpler Python script/pip package that speeds up or removes silent segments of video, re-encoding via ffmpeg; predecessor concept to auto-editor [web:110][web:111][web:114].

### automatic_video_editing (Winston-503)
- Python + MoviePy + Vosk (offline speech recognition) — cuts video based on either silence detection or **spoken control words** marking clip start/end, fully offline with local Vosk models [web:120].
- **Relevance**: Demonstrates a fully-offline alternative to Whisper (Vosk) for environments needing zero external model downloads or lower resource usage; also shows the "voice command editing" pattern (say "cut here") which could be a distinctive AI-assisted UX feature for NLKE-SAG.

## Summary: offline speech/caption/auto-cut stack recommendation
1. **Transcription/captions**: `whisper-node` or `node-whisper` (both local, TS-native) for word-level timestamps → auto-generated burned-in captions.
2. **Silence/dead-space removal**: shell out to `auto-editor` (Python CLI) as a pre-processing step before ingesting raw AI/human footage into the Remotion/Editly pipeline, or port its loudness-based logic into a native TS module using Web Audio API / ffmpeg silencedetect filter for a pure-TS stack.
3. **NLE round-trip**: leverage auto-editor's FCPXML export (or Editly/Remotion project state) to allow manual fine-tuning in DaVinci Resolve/Premiere when full manual control is needed.
