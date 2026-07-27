# ADR 0003: Use hybrid-resilient compute

Status: accepted, 2026-07-27.

Privacy-sensitive and lightweight transcription/analysis runs locally when capabilities permit. Heavy or unsupported work uses the existing immutable job contract on managed workers. Both paths emit the same provider/version/settings identities, cancellation states, receipts, and recovery semantics.
