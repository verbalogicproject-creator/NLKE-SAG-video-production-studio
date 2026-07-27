# SAG-aligned unified production architecture

```text
Repository -> evidence -> brief -> storyboard -> generation candidates -+
                                                                    |
Source video -> immutable analysis -> ranked clip candidates --------+-> canonical timeline
                                                                         -> finish
                                                                         -> review
                                                                         -> verified export
```

The production session is a durable cursor, not a media authority. It binds workflow mode, early intake projection, shared stage, focus, active analysis/generation revisions, variant, and review context to the canonical project.

Source analysis is keyed by source hash, proxy hash, transcription provider/version, content profile, and settings hash. Word timestamps, speaker turns, subject boxes, and crop trajectories carry confidence and provenance in normalized source coordinates. Missing or uncertain tracking produces a visible centered/manual fallback.

Candidate scores preserve their original score-policy version and component evidence. Later calibration creates a new policy or calibration revision and never rewrites historical scores. Feedback is append-only.

B-roll search returns candidates on a separate non-destructive track. Approval requires provenance and an acceptable license state. `authentic_evidence=false` prevents generated or stock visuals from satisfying factual evidence requirements.

Brand kits and variants are immutable revisioned records. Projects, render jobs, and exports pin exact revisions. The native FFmpeg renderer produces the canonical artifact; browser behavior remains preview-only.

Exports begin through the existing render receipt/job contract. Verification owns dimensions, duration, frame rate, representative decode, scene and caption checks, safe areas, audio, loudness, true peak, and SHA-256. Publication is not an export side effect.
