# Collaboration & Workspace Permissions (RBAC)

## Why this matters
A SaaS marketplace serving multiple creators/teams needs to control who can view, edit, approve, publish, and administer billing within a shared workspace — a single-user permission model won't scale to agencies or teams managing multiple creator accounts.

## Role-Based Access Control (RBAC) fundamentals
RBAC is the standard approach for building a secure access-control layer with clearly defined roles, permissions, and enforcement strategies for modern SaaS applications [web:225]. Core building blocks:
- **Roles**: named bundles of permissions (e.g., Owner, Editor, Reviewer, Publisher, Viewer) assigned to users within a workspace/tenant.
- **Permissions**: fine-grained capabilities (e.g., `render:create`, `render:approve`, `publish:execute`, `brandkit:edit`, `billing:view`) that roles are composed from.
- **Enforcement strategy**: permission checks must be enforced consistently at every access point (API layer, not just UI) — a common failure mode is UI-only permission hiding without backend enforcement, which is a security vulnerability, not just a UX gap.

## Suggested role model for a video-production SaaS
Drawing on the general RBAC pattern applied to this domain's workflow stages (per KB #1's pipeline: generate → edit → review → publish):
- **Owner/Admin**: full control including billing, workspace settings, brand kit management, user invitations.
- **Editor**: can create/edit render jobs, adjust reframing/captions/b-roll selections, but cannot publish or manage billing.
- **Reviewer/Approver**: can view generated clips and virality scores, approve or reject B-roll insertions and final cuts (ties directly into the "evidence-safe insertion" human-in-the-loop pattern from doc 05), but cannot create new jobs.
- **Publisher**: can schedule/publish approved clips to connected social accounts (via Ayrshare/PostEverywhere per KB #1 doc 06) but may not need edit access.
- **Viewer**: read-only access to analytics/results, common for stakeholders who need visibility without edit rights.

## Multi-tenant scoping
Given the SaaS marketplace model, permissions must be scoped per-workspace (tenant), not globally — a user who is an Owner in one creator's workspace should have zero implicit access to another creator's workspace. This mirrors the tenant-scoping pattern already noted for brand kits (doc 06) and Ayrshare's `profileKey` model (KB #1 doc 06) — all three (brand kits, social publishing credentials, and RBAC roles) should share the same workspace/tenant ID as their scoping key for architectural consistency.

## Enforcement implementation notes
- Permission checks should happen server-side on every API call, not just conditionally rendered UI elements — the RBAC guide specifically emphasizes "enforcement strategies" as a distinct concern from role/permission definition [web:225].
- Consider a policy-as-code approach (e.g., embedding permission logic in a dedicated authorization library/service) rather than scattering `if (user.role === 'admin')` checks across the codebase, to keep the permission model auditable and consistent as the product grows more roles/permissions over time.

## Note on source coverage
Direct documentation of collaboration/permission architecture specific to OpusClip-class video tools was not found in public sources — most reviewed competitor products (OpusClip, OpenClip, Cliphi, etc.) do not publicly document their team/workspace permission systems in technical detail. This document synthesizes general RBAC best practice applied to the specific workflow stages of a video-production pipeline, and should be validated against your own team's collaboration requirements (e.g., how many roles are actually needed at MVP stage) rather than treated as an industry-standard blueprint.
