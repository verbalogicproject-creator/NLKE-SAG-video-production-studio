# FFmpeg WASM & Browser-Native Offline Video Editing

## @ffmpeg/ffmpeg (ffmpeg.wasm)
- **What**: Pure WebAssembly/JavaScript port of FFmpeg enabling video/audio record, convert, and stream entirely inside the browser, no server round-trip [web:19][web:20].
- **Why it matters for offline**: Because processing happens client-side, this is the primary building block for "offline advanced video editing" in a TypeScript web/mobile-hybrid app — no uploads, no backend dependency, works airplane-mode/local-network [web:9][web:21].

### Architecture patterns (from real implementations)
- Run FFmpeg inside a **dedicated Web Worker** (with FFmpeg's own nested worker) so the UI thread stays responsive; post progress/results back via `postMessage` [web:11].
- Use **single-threaded WASM core** (`@ffmpeg/core@0.12.10`+) instead of multi-threaded, because multi-threading needs `SharedArrayBuffer` which requires `Cross-Origin-Isolation` (COOP/COEP headers) that break many third-party integrations [web:11].
- **CDN-load the ~30MB WASM binary** at first use via `toBlobURL()` rather than bundling it, then rely on browser cache thereafter [web:11].
- **Progress reporting**: parse `time=HH:MM:SS.ms` from ffmpeg's stderr log stream against known input duration for accurate progress bars; fallback to ffmpeg's built-in progress callback [web:11].
- **Cancellation**: use `AbortController` per run; on cancel, post a `terminate` message to the worker which calls `ffmpeg.terminate()` [web:11].
- **Command builder pattern**: a `commands.ts` module composes FFmpeg CLI arg arrays by layering enabled operations in fixed order: trim → rotate/flip → resize → codec/compression → audio → output format [web:11].
- **Resize / aspect-ratio fit modes** for social formats: Pad (`scale`+`pad`, black bars, all content preserved), Crop (`scale`+`crop`, fills frame, edges cut — default for Instagram/TikTok), Stretch (`scale` only, distorts) [web:11].
- **Quick presets**: one-click settings per platform (YouTube, Instagram Reel/Post, TikTok, X/Twitter, WhatsApp, iPhone, TV/Desktop) bundling resolution/format/bitrate/fit-mode; presets set values but remain user-editable afterward [web:11].

### Known limitations
- Codec support: H.264 and VP8/VP9 supported; **H.265/HEVC not supported** in WASM builds due to patent licensing [web:11].
- Audio handled automatically: MP4→AAC (`-c:a aac -b:a 128k`), WebM→Opus (`-c:a libopus -b:a 128k`) [web:11].
- Memory ceiling: entire file must fit in WASM heap; files over ~500MB risk out-of-memory errors in-browser — warn users and suggest compression/splitting [web:11].
- Encoding speed depends on client hardware; ~1-minute clip under 30s on mid-range laptops [web:11].

### WebCodecs API (lower-level alternative)
- **What**: Browser API giving direct, hardware-accelerated access to codecs for encode/decode without ffmpeg.wasm overhead; supported via `VideoDecoder`/`VideoEncoder`/`EncodedVideoChunk` [web:38][web:39].
- **Use case**: Real-time frame-level manipulation (filters, color correction, overlays) applied directly in the decode callback before re-encoding — lower latency than round-tripping through ffmpeg.wasm [web:38].
- **Tradeoff**: Lower-level, more manual pipeline construction (manual demux/mux, no built-in filter graph) versus ffmpeg.wasm's full CLI filter ecosystem [web:38][web:39].
- **Example project using this approach**: `flycut` (Vue3 + WebCodecs, CapCut-web-like) [web:43].

### Reference implementations to study
- Browser Video Editor (ffmpeg.abhikhatri.com) — trim, format convert, compress, extract frames/audio, filters, merge, all client-side [web:9].
- 2minclip.com — multi-clip upload, 9:16/16:9/1:1 canvas presets, trim+split, audio tracks with fade, MP4 H.264 export, zero backend [web:21].
- LosslessCut (`mifi/lossless-cut`) — Electron desktop app, TypeScript (98.2%), GPLv2, "swiss army knife" for lossless cut/merge/trim of video/audio/subtitles using FFmpeg under the hood; ~42k GitHub stars, actively maintained through 2026, includes HTTP API for automation, keyboard-bindable actions, GPS map rendering, JS-expression-based segment selection [web:67][web:69][web:76][web:75].
