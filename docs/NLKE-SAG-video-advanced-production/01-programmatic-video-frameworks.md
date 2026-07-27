# Programmatic Video Frameworks (React / TypeScript)

## Remotion
- **What**: Framework for creating real MP4 videos programmatically using React + TypeScript, treating video as "a function of frames" [web:23][web:13].
- **Stack**: React, TypeScript, webpack-based bundler, requires ffmpeg locally for rendering [web:13].
- **Key packages**: `remotion`, `@remotion/cli`, `@remotion/player`, `@remotion/lambda` (serverless/parallel rendering) — all must match version [web:13].
- **Project structure**: `src/index.ts` (entry, calls `registerRoot`), `src/Root.tsx` (declares `<Composition>` elements: id, dimensions, fps, duration, component), `remotion.config.ts` (webpack/browser config), `tsconfig.json` (needs `jsx: react-jsx`, `moduleResolution: bundler`, `isolatedModules: true`) [web:13].
- **Workflow**: `npx create-video@latest` scaffolds; `npm run dev` launches Remotion Studio (browser preview, live prop editing, hot reload) on localhost:3000; `npx remotion render src/index.ts <CompositionId> out/video.mp4` renders to MP4/GIF/PNG sequence [web:13].
- **Timeline building**: Remotion's official docs describe building a full timeline editor — define `Item`/`Track` TS types, render tracks, keep `tracks` state, pass to `<Player inputProps={tracks}>`, build timeline UI on top [web:14].
- **Performance**: 30-sec 1080p video renders in 2-5 min locally; Remotion Lambda parallelizes on AWS for near-real-time rendering at scale [web:13].
- **Relevance to NLKE-SAG**: Ideal core rendering engine for turning AI-generated assets (Veo clips, omni-model outputs, TTS, captions) into deterministic, versioned, code-driven video compositions with full TypeScript type safety.

## Etro (etro-js)
- **What**: Framework-agnostic TypeScript library for programmatically editing video in the browser and Node, GPL-3.0 licensed [web:46][web:52].
- **Capabilities**: Composites layers (video, audio, image, text) with GLSL effects/filters; supports custom layers and custom effects in JS/GLSL [web:46][web:48].
- **Repos**: `etro-js/etro` (core lib), `etro-node` (Node wrapper), `etro-js.github.io` (docs site) [web:47].
- **Usage pattern**: `new etro.Movie({ canvas })`, then add `etro.layer.Video({ startTime, source })` layers to compose a timeline programmatically [web:57].
- **Relevance**: A lighter-weight, canvas-based alternative to Remotion for real-time browser-side compositing/preview — good fit for an in-app live editor preview layer while Remotion handles final high-quality export.

## designcombo/react-video-editor (CapCut/Canva clone)
- **What**: Full open-source online video editor built with React + TypeScript, using Remotion for rendering, explicitly modeled as a CapCut/Canva clone [web:49][web:59].
- **Features**: Multi-track editing, keyframe animations, real-time preview, high-quality export options comparable to commercial tools [web:59][web:50].
- **Stack**: React, TypeScript, Remotion, pnpm tooling; requires `PEXELS_API_KEY` env var for stock media [web:49].
- **Setup**: `git clone`, `pnpm install`, `pnpm dev` → runs at `localhost:3000` [web:49].
- **Sibling repos from DesignCombo org**: `react-video-editor-js` (JS starter variant), `react-design-editor` (Canva-style design editor using fabric.js), Remotion Timeline component [web:51].
- **Similar community forks**: `trykimu/videoeditor` ("Your Creative Copilot for Video Editing", React/TS/Remotion/CapCut-Canva style) [web:43]; `robinroy03/videoeditor` [web:58]; `AmitDigga/fabric-video-editor` (Next.js + React + TailwindCSS + MobX + TypeScript + fabric.js) [web:43].
- **Relevance**: Best reference architecture for NLKE-SAG's own timeline UI — it already solves multi-track state management, Remotion integration, and export pipelines end to end. Could be forked/adapted directly rather than built from scratch.

## flycut (x007xyz)
- **What**: Web-based video editor implemented with WebCodecs (not ffmpeg.wasm), similar to CapCut Web, built in Vue3 [web:43].
- **Relevance**: Demonstrates an alternative all-browser-native (no WASM ffmpeg) architecture using the WebCodecs API for hardware-accelerated encode/decode — worth benchmarking against ffmpeg.wasm for performance on mobile/offline scenarios.
