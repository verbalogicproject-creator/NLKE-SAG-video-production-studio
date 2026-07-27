# Production intelligence threat model

## STRIDE

| Threat | Boundary | Control |
|---|---|---|
| Spoofing | Workspace, actor, provider | Scoped pairing tokens, service authentication, provider identity snapshots |
| Tampering | Source, analysis, timeline, export | Content hashes, immutable revisions, optimistic writes, receipts, QC SHA-256 |
| Repudiation | Candidate and review decisions | Append-only feedback/review records with actor and timestamp |
| Information disclosure | Media, transcripts, face tracks, secrets | Workspace scoping, local-first analysis, redaction, bounded logs, explicit retention |
| Denial of service | Upload, analysis, provider, render | Admission reservation, immutable jobs, concurrency quotas, cancellation, leases, bounded retries |
| Elevation of privilege | Commands, approvals, delivery | Declared scopes, exact human confirmation, no authority from browser storage or model output |

## AI-specific threats

- Prompt injection in transcripts, repositories, captions, or metadata: treat source content as data and enforce structured output schemas.
- Hallucinated evidence: claims must bind authentic evidence; generated/stock assets never satisfy the binding.
- Score overclaim: label as editorial quality, expose evidence and confidence, version the policy, and ban reach promises.
- Model/provider drift: pin provider/model/version/settings in every analysis revision and preserve old results.
- Unsafe automatic insertion: candidates require an explicit human decision and idempotent insertion command.
- Cross-tenant retrieval: filter workspace assets before semantic ranking; provider queries contain only authorized bounded context.

## Biometric-derived retention

Face boxes, embeddings, voice embeddings, diarization identities, and face/speaker associations are sensitive derived data. Raw normalized boxes and anonymous speaker labels expire with the analysis retention class or within 30 days after project deletion, whichever is sooner. Reusable face or voice embeddings are disabled by default and require a documented lawful purpose, explicit consent, workspace policy, encryption, and a shorter configured retention period. Deletion removes derived indexes and cached provider artifacts; export receipts retain only non-biometric hashes and verification facts.

Dependency owners: engine/runtime, web/product, infrastructure, and security each own their lockfiles and container bases. CI emits a CycloneDX 1.7-compatible SBOM from the checked-out build context and validates it before image builds.
