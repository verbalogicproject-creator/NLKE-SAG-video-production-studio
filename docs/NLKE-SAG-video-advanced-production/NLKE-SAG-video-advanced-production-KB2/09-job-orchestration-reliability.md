# Job Recovery, Cancellation, Replay, and Deduplication

## Why this matters
An AI video pipeline is a multi-stage, long-running, expensive job (transcription, scoring, tracking, reframing, rendering, publishing) running across potentially unreliable infrastructure. Without proper job orchestration discipline, failures cause duplicate charges, duplicate social posts, wasted GPU/render time, and confused users.

## Core concepts: idempotency vs. deduplication
These are complementary, not interchangeable [web:204]:
- **Idempotency**: a function/operation can be called multiple times without changing the result after the first successful call — makes retries *safe*.
- **Deduplication**: proactively detecting and skipping jobs that have already been processed (or are already queued) — prevents *unnecessary* retries/duplicate work in the first place.
- In distributed systems using message queues (Kafka, Redis Streams, SQS), **at-least-once delivery is the norm**, meaning a worker *will* sometimes receive the same job twice — this is a fundamental property of distributed systems, not a bug to "fix away" [web:204].

## Real-world failure modes from missing idempotency (directly applicable)
Documented failure patterns from a general backend engineering source, mapped to NLKE-SAG's domain [web:204]:
- Double-charging users during a payment/credit retry → in NLKE-SAG, double-deducting render credits/quota for a single video job.
- Sending the same notification/email multiple times → duplicate "your clips are ready" notifications.
- Triggering external APIs more than once → **duplicate social media posts** if a publish job is retried without deduplication (a especially damaging failure mode for a publishing SaaS — posting the same clip twice to a creator's TikTok account is a visible, embarrassing bug).
- Generating multiple invoices → duplicate billing line items for a single render.

## Idempotent job queue design pattern (Redis-based, directly implementable)
A concrete, reusable pattern for safe distributed job processing [web:204]:
```
dedup_key = f"idempotency:{job_id}"
if r.set(dedup_key, "processing", nx=True, ex=3600):  # atomic claim
    try:
        process(payload)
        mark_complete(job_id)
        r.set(dedup_key, "done", ex=86400)
    except Exception:
        r.delete(dedup_key)  # release lock, allow retry
        retry_later(job_id)
else:
    log("Duplicate job. Skipping.")
```
Key properties: `NX` (set-if-not-exists) ensures only one worker claims a job; a TTL prevents permanent deadlock if a worker crashes mid-processing; the dedup key is only marked "done" after full success, so a mid-failure retry is still allowed to proceed cleanly [web:204].

## Idempotency keys for external side-effecting operations
For any call to an external API with real-world side effects (charging a payment, publishing a social post), use the external API's own idempotency-key mechanism when available — e.g., Stripe/Razorpay pattern of passing an `Idempotency-Key` header derived from your internal job ID, so that even if your own retry logic misfires, the external service itself deduplicates the effect [web:204]. Given NLKE-SAG's use of Ayrshare/PostEverywhere for publishing (KB #1 doc 06), check whether these APIs support idempotency keys for post-creation calls — this is the single most damaging failure mode to leave unhandled.

## Established deduplication strategies (from GitLab's production Sidekiq implementation)
GitLab's job-processing framework documents two named deduplication strategies applicable to any queue system [web:197]:
- **`until_executing`**: takes a lock when a job is enqueued, releases the lock right before the job starts running. Appropriate when a second identical job scheduled *before* the first one starts is genuinely redundant (e.g., "recalculate this video's virality score" — if two identical recalculation requests queue up before either runs, the second is pointless once the first executes).
- **`until_executed`**: takes a lock when enqueued, releases only after the job *finishes*. Appropriate for preventing the same job from running concurrently in parallel workers (e.g., prevent two workers from rendering the same clip simultaneously).
- Deduplication depends on a Redis-backed idempotency key with a TTL (default ~10 minutes in GitLab's implementation) — if a job neither executes nor completes within the TTL, the dedup key expires and a duplicate could theoretically be allowed through; this TTL should be tuned per job type (a video render job may need a much longer TTL than a lightweight metadata update) [web:197].
- GitLab also supports an `if_deduplicated: :reschedule_once` option — ensuring that if deduplication drops a job while another is running, one additional run is guaranteed after the current one finishes, so the *latest* input state is never silently lost due to a race condition [web:197].

## Job queue architecture checklist (synthesized)
A complete distributed job system for NLKE-SAG should include [web:204][web:197]:
- A durable queue (Redis Streams, Kafka, or managed equivalent) for job distribution across pipeline stages.
- Workers pulling from queues with explicit idempotency-key claiming (the `SET NX` pattern above) before starting work.
- Persistent job-status tracking (queued / processing / done / failed) in a database, separate from the ephemeral Redis lock.
- Retry logic with exponential backoff and jitter.
- A **Dead Letter Queue (DLQ)** for jobs that exceed max retry attempts, so poison messages don't loop forever and consume resources — surfaced to an ops dashboard for manual investigation.
- Explicit **cancellation** support: a running render/AI job should be interruptible (e.g., via an `AbortController` pattern, as already noted for ffmpeg.wasm in KB #1 doc 02) with cleanup of partial outputs and released quota/credits.
- Explicit **replay** support: the ability to re-run a specific historical job (e.g., "re-render this clip with a different brand kit") using the same immutable job input (source video reference + configuration snapshot), which requires storing job configuration as an immutable, versioned record rather than mutable state.

## Recommendation for NLKE-SAG
Implement the Redis `SET NX` + TTL idempotency-claim pattern for every stage of the pipeline (transcription, scoring, reframing, rendering, publishing), with per-stage-appropriate TTLs. Treat the **publish-to-social step as the highest-priority stage for idempotency-key enforcement**, given the reputational damage of duplicate posts, and check whether Ayrshare/PostEverywhere expose native idempotency-key support before building a custom dedup layer on top. Store every job's full configuration (source asset reference, brand kit ID, tracking mode, target aspect ratios, etc.) as an immutable snapshot at submission time to support clean replay.
