---
name: model-cascade
description: Plan and execute auditable, cost-aware repository work through Sol, Terra, and Luna. Use when work should be decomposed into architecture, bulk read-only discovery, implementation, verification, escalation, and final review with explicit model roles and budgets.
---

# Model Cascade

Read `references/routing-policy.md`, then use the contracts under `.codex/cascade/`.

## Workflow

1. Ask `sol-planner` for a typed DAG and acceptance contract.
2. Validate every task envelope with `scripts/validate_cascade.py` before spawning work.
3. Send extraction, classification, inventories, and log triage to `luna-operator`.
4. Send bounded writes, integration, debugging, and tests to `terra-builder`.
5. Serialize writes. Parallelize only independent read-only tasks.
6. Escalate Luna to Terra on ambiguity or required writes. Escalate Terra to Sol on architecture, security, migrations, or two failed attempts.
7. Ask `sol-reviewer` to inspect the evidence bundle for cross-cutting or high-risk work.
8. Return one consolidated result with tests, risks, and observed usage when available.

## Invariants

- Fail closed when a configured model is unavailable. Never silently substitute a model.
- Give workers task slices and file references, not the entire conversation.
- Keep Luna read-only and disallow recursive worker delegation.
- Require acceptance criteria, write scopes, verification, and instruction hashes.
- Model output cannot grant approval, publication, credential, or destructive authority.
