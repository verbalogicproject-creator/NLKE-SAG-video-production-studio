# Security, Data Residency, Threat Modeling, SBOMs, Dependency Ownership

## Why this matters
A SaaS video pipeline handles sensitive assets (unpublished creator content, personal likeness via face tracking, payment/billing data) and depends on a large surface of third-party libraries (many identified across KB #1 and this KB — Remotion, Whisper bindings, ffmpeg.wasm, diarization models, social publishing SDKs). Each dependency and each data flow is a potential attack surface that needs deliberate, documented handling rather than ad hoc trust.

## STRIDE threat modeling methodology
**STRIDE** (developed by Microsoft) is the most widely used framework for systematically identifying and categorizing security threats in an application, organized into six threat categories, each mapped to a corresponding security control [web:237]:

| Threat Type | Description | Security Control |
|---|---|---|
| Spoofing | Accessing/using another user's identity or credentials | Authentication |
| Tampering | Maliciously modifying persistent data or data in transit | Integrity |
| Repudiation | Performing prohibited operations without traceability | Non-repudiation (logging/audit) |
| Information Disclosure | Reading data one isn't authorized to access | Confidentiality |
| Denial of Service | Denying access to legitimate users | Availability |
| Elevation of Privilege | Gaining unauthorized privileged access | Authorization |

### STRIDE process (4-step, OWASP-documented) [web:237][web:236]
1. **Scope the work**: draw data-flow diagrams (DFDs), identify entry/exit points, identify assets, define trust levels/trust boundaries.
2. **Determine threats**: apply STRIDE categorization against each component/data flow identified in the DFD, using the threat category table above to systematically enumerate what could go wrong at each trust boundary.
3. **Determine countermeasures and mitigation**: for each identified threat, choose to accept, eliminate, mitigate, or transfer the risk, prioritizing by likelihood × impact.
4. **Assess the work**: verify a completed diagram, threats list, and mitigations list exist and are documented.

### Mitigation techniques per threat type [web:237]
- **Spoofing**: appropriate authentication, protect secret data, avoid storing secrets in plaintext.
- **Tampering**: appropriate authorization, hashes/MACs/digital signatures, tamper-resistant protocols.
- **Repudiation**: digital signatures, timestamps, audit trails.
- **Information Disclosure**: authorization, privacy-enhanced protocols, encryption, avoid storing unnecessary secrets.
- **Denial of Service**: appropriate authentication/authorization, filtering, rate limiting/throttling, quality-of-service controls.
- **Elevation of Privilege**: run with least privilege everywhere.

### STRIDE applied to NLKE-SAG's specific architecture
Mapping the generic framework to this project's actual data flows and components:
- **Trust boundaries to diagram**: creator's browser/app ↔ NLKE-SAG API; NLKE-SAG backend ↔ Veo/Omni model APIs (external AI providers); NLKE-SAG backend ↔ social publishing APIs (Ayrshare/PostEverywhere, holding creators' connected-account OAuth tokens); render workers ↔ job queue/storage; multi-tenant workspace boundaries (one creator's data must never leak to another's).
- **High-value assets**: unpublished creator video content (competitive/reputational value if leaked pre-publish), OAuth tokens for connected social accounts (high-value credential — compromise enables posting-as-creator attacks), billing/payment data, brand kit assets (proprietary creative IP), face/biometric data processed during tracking (privacy-sensitive under regulations like GDPR/BIPA).
- **Notable Elevation-of-Privilege risk specific to multi-tenant SaaS**: the RBAC system from doc 08 is itself a STRIDE-relevant control — a broken permission check is a direct Elevation-of-Privilege vulnerability, reinforcing that RBAC enforcement must happen server-side, not just in UI.
- **Notable Information Disclosure risk specific to this domain**: face-tracking/diarization data (doc 02) constitutes biometric-adjacent processing; ensure this data is scoped, encrypted at rest, and not retained longer than necessary for the render pipeline to complete.

### STRIDE for AI/ML components specifically
Since NLKE-SAG's pipeline is heavily AI/ML-driven, a specialized variant — **STRIDE-AI** — exists specifically for asset-centered threat modeling of AI/ML systems, recognizing that ML models exhibit vulnerabilities (e.g., adversarial inputs, model extraction, training data poisoning) that conventional IT threat models don't cover [web:229][web:232]. This is directly relevant to the virality-scoring model (doc 01) and any custom-trained tracking/reframing models — worth a dedicated threat-modeling pass separate from the general application STRIDE exercise.

## SBOM (Software Bill of Materials)
An SBOM is described as a foundational practice for modern software supply-chain security, helping organizations reduce cyber risk from third-party dependencies and supporting agile development practices [web:224]. Given the very large number of third-party open-source dependencies identified across both knowledge bases (Remotion, Etro, Editly, ffmpeg.wasm, Whisper bindings, Pyannote, MediaPipe, Ayrshare SDK, and dozens more), maintaining an accurate, automatically-generated SBOM is essential for:
- Tracking which specific versions of which libraries are in production, enabling rapid response when a CVE is disclosed in any dependency.
- Supply-chain risk visibility — knowing not just direct dependencies but transitive ones (a compromised transitive dependency of, say, a video-processing library, is a real and increasingly common attack vector, as referenced by the `axios@1.14.1` supply-chain incident cited in trust-boundary security literature) [web:248].
- Licensing compliance — several libraries identified in KB #1 carry copyleft licenses (Etro is GPL-3.0, LosslessCut is GPL-2.0) which have real implications for how they can be integrated into a closed-source commercial SaaS product; an SBOM with license metadata surfaces this automatically rather than relying on manual tracking.

## Dependency ownership
While no single authoritative source in this research directly covered "dependency ownership" as a named practice, the STRIDE trust-boundary literature on modern supply-chain defense (referencing real 2026-era incidents like the `axios@1.14.1` compromise) implies the following as current best practice [web:248]:
- Assign an internal owner/team responsible for reviewing and approving version bumps of each critical dependency (especially those touching untrusted input, like video/audio parsing libraries, which are historically common vectors for memory-corruption vulnerabilities).
- Use lockfiles (`package-lock.json`/`pnpm-lock.yaml`) with automated dependency-update tooling that requires human review before merging, rather than fully automatic dependency upgrades in a media-processing pipeline where a compromised transitive dependency could execute arbitrary code during video processing.
- Maintain a documented "trust boundary" map (per the STRIDE DFD exercise above) specifically calling out which dependencies process untrusted external input (user-uploaded video/audio, AI-model responses) versus purely internal logic — untrusted-input-processing dependencies warrant the highest scrutiny.

## Data residency
Not covered in depth by any source found in this research round — this is a gap that will require dedicated follow-up research specific to your target markets' regulatory requirements (e.g., GDPR data-residency rules if serving EU creators, or platform-specific requirements from social media APIs regarding where OAuth tokens/user data may be stored/processed). Flag this explicitly as an open item requiring compliance/legal research beyond the technical scope of this knowledge base.

## Recommendation for NLKE-SAG
Run a formal STRIDE threat-modeling session before scaling past MVP, producing a data-flow diagram of the full pipeline (ingest → AI processing → render → publish) with explicit trust boundaries at each external API integration point (Veo/Omni, social publishing APIs) and each multi-tenant boundary. Generate an SBOM as part of the CI/CD pipeline (tools like Syft or the native `npm sbom`/`pnpm audit` commands can automate this) and gate dependency updates touching video/audio parsing behind mandatory human review given their history as attack vectors. Treat data residency as a dedicated compliance research item requiring legal input, not a purely technical decision.
