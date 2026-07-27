# Cost and Quota Accounting (GPU/Inference Metering)

## Why this matters
NLKE-SAG's pipeline chains together multiple expensive AI calls (Veo video generation, Omni model reasoning, transcription, scoring, face tracking, rendering) — each with real infrastructure cost. Without granular cost tracking and quota enforcement, a SaaS marketplace has no way to price plans profitably or prevent any single tenant from consuming disproportionate resources.

## GPU compute billing complexity
GPU compute billing for AI infrastructure is described as uniquely complex compared to traditional cloud billing, requiring careful design of metering, pricing, progressive billing, and enterprise controls — with real-world deployments issuing hundreds of millions in invoices monthly built on these patterns [web:202]. Traditional cloud FinOps approaches (simple per-hour VM billing) break down for GPU workloads because usage is often fractional, bursty, and shared across tenants [web:208].

## Cost allocation models for shared/multi-tenant GPU workloads
Four general cost-allocation models exist for GPU workloads, along with Kubernetes tag propagation and per-token attribution techniques for shared inference infrastructure [web:208]. For a video pipeline specifically, the equivalent attribution units are:
- **Per-render-second** or **per-output-minute** of video generated (for Veo/Omni calls).
- **Per-inference-call** (for discrete steps like transcription, face detection, scoring — often cheaper individually but numerous).
- **Per-GPU-second** consumed during actual rendering compute (for local/self-hosted rendering via Remotion Lambda or similar).
- **Per-token** (if any LLM-based steps, e.g., B-roll query generation, virality scoring judge, are billed by token).

## Multi-tenant quota and isolation patterns
Building multi-tenant LLM/GPU serving requires designing per-customer token/compute quotas alongside "noisy-neighbor" isolation (ensuring one tenant's heavy usage doesn't degrade service for others) and billing metering as three coupled concerns, not separate afterthoughts [web:210]. Applied to NLKE-SAG:
- Each tenant (creator/workspace) should have a configurable quota (e.g., "N render-minutes per month," "N Veo generation calls per month") enforced at the job-submission layer — reject or queue-with-warning when a tenant exceeds quota, rather than allowing unlimited consumption that isn't billed for.
- Job scheduling should include fairness/isolation logic so that one tenant submitting a large batch job doesn't starve other tenants' render queues — this becomes increasingly important as the marketplace scales.

## Metering-first philosophy
The operators who succeed at AI-cloud billing are the ones who treat metering as a *control problem first and a billing problem second* — meaning usage tracking and quota enforcement need to be built into the system's real-time control flow (rate limiting, queue admission, job rejection), not bolted on afterward purely for invoice generation [web:199]. This has a direct architectural implication: cost/quota tracking should live in the same job orchestration layer described in doc 09 (idempotent job claims), not as a separate downstream analytics pipeline that only reports usage after the fact.

## Practical implementation pattern
- Every job (transcription, scoring, tracking, rendering, publishing) should emit a **metering event** at completion (or at defined checkpoints for long-running renders) recording: tenant ID, job type, resource units consumed (GPU-seconds, API calls, render-minutes), and a monetary cost estimate.
- These events feed both (a) real-time quota enforcement (checked before admitting a new job) and (b) downstream usage-based billing (aggregated periodically for invoicing).
- Tools like Lago (referenced as a real-world metering/billing backend used at scale for GPU compute) illustrate the pattern of a dedicated metering-and-billing service separate from the core application logic, ingesting usage events and handling pricing/invoicing/enterprise billing controls independently [web:202][web:203].

## Recommendation for NLKE-SAG
Design cost/quota accounting as a first-class concern integrated into the job orchestration layer (doc 09) from the start — every pipeline stage emits a metering event on completion, tenant quotas are checked at job-admission time (not after the fact), and a dedicated usage-aggregation layer (self-built or via a metering/billing platform like Lago) converts raw usage events into both real-time quota enforcement and periodic invoicing. Prioritize metering Veo/Omni model calls first, since these are almost certainly the highest per-unit-cost steps in the pipeline.
