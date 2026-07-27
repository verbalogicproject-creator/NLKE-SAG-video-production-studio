# B-Roll Retrieval & Evidence-Safe Insertion

## The problem being solved
Manually finding and placing supplementary footage ("B-roll") to match spoken narration is one of the most time-consuming parts of video editing — hours spent searching for secondary footage and manually dragging clips to align with audio [web:174]. Automating this well requires semantic understanding of *what is being said*, not just keyword matching.

## Reference architecture: transcript-driven B-roll pipeline
A documented end-to-end open-source pipeline (`video-use` + `HyperFrames`) illustrates the full pattern [web:174]:
1. **Transcription**: extract a word-for-word transcript from the audio track.
2. **Semantic segmentation ("bits timeline")**: convert the transcript into a time-coded taxonomy of narrative subjects/topics, mapping exact time brackets to what's being discussed, with rigid boundaries so visual blocks never overlap.
3. **Scaffold preparation**: auto-generate local project folders for b-roll, animations, templates, scripts, and references.
4. **Candidate retrieval**: for every time bracket, query stock media APIs (Pexels, Pixabay, or similar) using the topic/subject extracted from that segment, downloading multiple candidate clips per bracket.
5. **Human-in-the-loop review ("picker")**: rather than blindly auto-selecting AI-chosen visuals (which produces disjointed, confusing edits), the pipeline pauses and generates a local HTML picker interface showing the transcript snippet alongside a grid of candidate videos for that moment — the human selects the single best match per segment.
6. **Blueprint compilation**: human selections compress into a single master JSON file, an immutable blueprint for the assembly/render phase.
7. **Handoff/render**: the JSON blueprint feeds back into the rendering engines, which apply established template rules (layout, colors, shapes, animations) and execute final render, synchronizing selected B-roll to the spoken track using exact timecodes [web:174].

This human-in-the-loop pattern is directly relevant to the "evidence-safe insertion" concern in your gap list — fully automated B-roll selection risks inserting *misleading* or *contextually wrong* footage (e.g., stock footage that looks like real evidence but isn't), so a review/approval gate before final render is a meaningful safety feature, not just a UX nicety.

## Commercial implementations and their design choices
- **CaptionX Auto B-Roll** (Premiere Pro plugin, in development): reads transcript → identifies visual opportunities per segment → generates AI search queries → searches Pexels/Storyblocks → presents matches with **confidence scores** for review/swap before insertion → inserts onto a **separate B-roll track**, leaving original footage untouched [web:176].
- **AutoCut AutoB-Rolls** (Premiere Pro/DaVinci Resolve plugin): similar transcript-driven detection, can process ~1h30m of footage in about a minute; explicitly frames automation as "removing the repetitive steps between finding a clip and placing it," not replacing editorial judgment — duration/position/replacement remain fully editable after automated placement [web:183][web:184]. Also supports **AI-generated custom images** as an alternative to stock footage when no good real match exists — useful for abstract/conceptual narration.
- **`sasoder/stockpile`** (open-source, Python + Gemini API): drop a clip in an input folder, AI transcribes and extracts key topics, searches YouTube for candidate b-roll per topic, AI evaluates/scores each candidate for quality and visual relevance, outputs organized folders of scored footage ready to edit — demonstrates the retrieval+scoring pattern without a UI dependency, suitable for headless pipeline integration [web:180].
- **B-Script** (academic, transcript-based B-roll editing research): formal research into determining both *content* and *position* of B-roll from transcripts and inserting it into the media timeline — relevant prior art for anyone building a scoring/placement algorithm from scratch [web:181].

## Design considerations for "evidence-safe" insertion
1. **Separate track, non-destructive**: always insert B-roll on its own track rather than overwriting original footage, preserving full reversibility [web:176].
2. **Confidence scoring + review gate**: never fully auto-commit AI-selected footage without a confidence score and an approval step, especially for factual/informational content where mismatched B-roll could misrepresent claims [web:176][web:174].
3. **Source provenance tracking**: since retrieved clips come from external stock libraries (Pexels/Storyblocks/YouTube), track and store license/attribution metadata per inserted clip for compliance — a gap not explicitly solved in any reviewed tool but essential for a commercial SaaS product to avoid copyright/licensing exposure.
4. **Semantic query generation via LLM**: all reviewed tools use an AI model (Gemini in `stockpile`, unspecified LLM in CaptionX/AutoCut) to convert a transcript segment into an effective stock-search query — this LLM step is the actual "semantic" part of "semantic B-roll retrieval," not the search engine itself [web:176][web:180][web:183].

## Recommendation for NLKE-SAG
Adopt the `video-use`/`HyperFrames`-style pipeline: transcript → segmented topic taxonomy → LLM-generated search queries → multi-source candidate retrieval (Pexels + Pixabay + user's own footage library) → confidence-scored picker UI for human approval → JSON blueprint → automated render onto a separate B-roll track. Build in license/attribution metadata tracking from day one given the SaaS marketplace's exposure to copyright risk at scale.
