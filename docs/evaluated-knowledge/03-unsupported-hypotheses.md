# Unsupported hypotheses and benchmark gates

The following are hypotheses, not requirements or marketing claims:

1. Clip Quality Score predicts retention, reach, or platform performance. Validate only against lawful, consented analytics with train/evaluation separation, calibration curves, confidence intervals, and content-profile slices.
2. Any exact retention uplift, correlation, or virality percentage copied from research. Reproduce against a documented dataset before citing it.
3. A fixed browser memory ceiling, universal maximum source duration, or universal mobile render limit. Benchmark the exact browser, codec, resolution, and device tier.
4. Competitor training data, model architecture, scoring features, or private infrastructure. Treat public UI behavior only as reference.
5. Diarization-to-face association is reliable enough to drive framing without review. Measure speaker-switch accuracy, identity swaps, overlap, and low-confidence fallback.
6. Proxy and original coordinate parity is exact for rotated, anamorphic, variable-frame-rate, or oddly padded media. Test normalized mapping and decoded frames for every fixture class.
7. Provider-reported prices remain current. Store the source and effective date; unknown remains `unknown`.

Every accepted benchmark records fixture hashes, tool versions, settings, hardware, warm/cold state, raw outputs, and a pass/fail threshold chosen before the run.
