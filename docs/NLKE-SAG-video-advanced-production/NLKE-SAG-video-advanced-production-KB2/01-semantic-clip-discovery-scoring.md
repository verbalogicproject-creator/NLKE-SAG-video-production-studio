# Semantic Clip Discovery & Virality/Hook/Retention Scoring

## Why this matters
Turning one long video into many short clips requires deciding *which* segments are worth extracting. Naive uniform-length chunking produces mostly mediocre clips; the entire value proposition of an OpusClip-class tool is **ranking moments by predicted performance**, not just cutting them out.

## OpusClip's Virality Score model
- OpusClip assigns a 0-99 **Virality Score** to each candidate clip, sorting results by score by default so creators triage the best moments first [web:132].
- The score is a composite of four evaluated dimensions, each independently graded [web:132][web:135]:
  - **Hook**: does the intro grab attention and directly relate to the main topic?
  - **Flow**: does the video progress logically with a satisfying conclusion?
  - **Value**: does it offer value, resonate emotionally, create a personal connection?
  - **Trend**: does it align with current trends/audience interests?
- Additional prompt-relevance checks run when using "ClipAnything" mode (natural-language clip requests) [web:132].
- Feature is gated behind Pro/Starter plans — a monetization lever worth considering for NLKE-SAG's own tiering [web:132].
- UI pattern: per-clip letter grades for each sub-dimension (hook/flow/engagement/trend) alongside the overall numeric score, plus a like/dislike signal that personalizes future ranking to the user's taste [web:135].

## Multi-modal moment scoring (developer-level architecture)
Based on OpusClip's public API documentation for viral-moment detection [web:134]:
- **Signal categories** combined into one score:
  - Transcript-level: hook strength, narrative arc completion (setup→payoff→conclusion), information density, emotional valence (surprise/humor/conviction/insight), quotability (self-contained shareable statements).
  - Audio dynamics: pitch range, pace shifts, laughter detection.
  - Visual cues: gesture intensity, facial expression.
- Models are trained on **real (clip, performance) pairs** scraped/licensed from actual TikTok/Reels/Shorts posts — hundreds of thousands to millions of data points — making this fundamentally a supervised learning problem grounded in observed engagement, not a hand-tuned heuristic [web:134].
- **API design pattern** worth replicating: two integration modes — (1) *standalone scoring* (submit arbitrary start/end timestamps, get back a score — useful for grading your own rough cuts) and (2) *auto-select* (model proposes top-N moments above a configurable threshold as part of the generation workflow) [web:134].
- **Calibration caveats to design around**:
  - Score scales and thresholds are not standardized across vendors — document what "70+" actually means for your own model.
  - Granularity varies: fixed windows (30s/60s) vs. continuous scoring with free window selection — continuous is more flexible and should be the design target.
  - Strong content-type bias: models trained heavily on podcast/talking-head content score B-roll-heavy, music, and animated content systematically lower — plan per-content-type threshold tuning [web:134].
  - Recommended calibration workflow: sample 50 scored clips, manually rate on a 5-point scale, find the threshold where ~70%+ of clips above it would be editorially approved; track actual published-clip performance as ongoing ground truth to recalibrate per-show/per-creator over time [web:134].

## Hook-specific scoring research (retention-focused, independent of OpusClip)
A 4,000-hook study cross-validated a retention-scoring model against actual YouTube/TikTok API retention curves, achieving r²=0.74 overall and r²=0.81 within short-form content specifically [web:136]. Key mechanical findings, directly actionable as scoring-model features or as content-QA rules:
- **Cut cadence**: high-scoring hooks (85+) land their first hard cut between 1.4-1.7 seconds; average creators cut at 2.4s — this single change is worth ~13 retention points [web:136].
- **Promise length**: high scorers average 6.2 words in the opening spoken line; hooks over 10 words score ~14 points lower — compression forces cognitive commitment [web:136].
- **Visual proof**: 88% of high-scoring hooks show concrete visual evidence of the stated promise within the first 3 seconds; talking-head-only openings cap around 72 [web:136].
- **Planned payoff timing**: curiosity gaps resolved between seconds 22-29 correlate with sustained retention; payoffs after second 35 collapse at the well-known "28-second retention dip" in 84% of cases [web:136].
- Together these four traits (cadence, promise length, visual proof, payoff timing) explain ~78% of variance in 30-second retention in the sampled dataset — a strong candidate feature set for an in-house hook-scoring model [web:136].
- Seven common failure modes to flag automatically: late first cut (>2.4s), overlong opening line (>10 words), no visual proof in first 3s, promise without stakes, late-resolving curiosity gap (>35s), generic/fake-feeling stock B-roll, and static talking-head with no motion in frame [web:136].

## Semantic video moment retrieval (academic grounding)
- **Ranked Video Moment Retrieval (RVMR)**: a formal task framework splitting semantic search into segment retrieval → proposal generation → moment refinement/re-ranking, using precomputed embeddings indexed offline for scalable retrieval regardless of video length — directly applicable architecture for indexing a creator's full video library for semantic search ("find all moments where I talk about pricing") [web:124].
- Approach: divide videos into equal-length segments, embed both segments and text queries into a shared vector space, retrieve approximate nearest neighbors, then refine/re-rank top candidates — a standard RAG-style pattern applicable to video content specifically [web:124].

## Recommendation for NLKE-SAG
Build a **two-stage scoring pipeline**: (1) a transcript/embedding-based semantic segment retriever (RVMR-style) to generate candidate clip windows from Whisper transcripts, then (2) a multi-modal scorer combining hook mechanics (cadence, promise length, visual proof, payoff timing — all programmatically measurable from transcript timestamps + scene-cut detection) with an LLM-based qualitative judge (narrative arc, emotional valence, quotability) for a final composite score. Expose both standalone scoring and auto-select modes as API surfaces, and build in per-content-type and per-creator calibration from day one rather than a single global threshold.
