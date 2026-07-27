# Brand Kits & Reusable Templates

## Why this matters for a SaaS marketplace
For a multi-tenant platform serving many creators, requiring every video to be manually re-styled defeats the purpose of automation. Brand kits let a creator (or a business managing multiple creators) define visual identity once — colors, fonts, logo placement, intro/outro cards, lower-thirds, watermarks — and have every generated video automatically conform to it.

## Core brand kit concept
Brand kits make it possible for an individual or entire team to create on-brand videos quickly by defining reusable branded templates once and applying them repeatedly rather than rebuilding styling per video [web:187].

## Elements typically included in a brand kit
Based on the OpenCutAI feature description, a brand kit system should let users "define your brand once and apply intro/outro cards, lower thirds, watermarks in one click" [web:159] — implying the minimum component set:
- Color palette (primary/secondary/accent colors)
- Typography (font families, weight/size presets for titles vs. captions vs. body text)
- Logo assets and placement rules (corner position, size, opacity)
- Intro/outro card templates
- Lower-third templates (name/title overlays for speakers)
- Watermark configuration

## Template system architecture (informed by reviewed editor codebases)
- `designcombo/react-video-editor` (covered in depth in KB #1) is built as a Remotion-based React app — its component architecture (reusable `<Composition>` definitions parameterized by props) is directly suited to a template system: a "template" is simply a parameterized Remotion composition where brand-kit variables (colors, logo URL, font) are injected as props at render time [web:49].
- Creatomate's template model (also covered in KB #1) demonstrates the cloud-render equivalent: design a template visually once, then programmatically inject per-render `modifications` (a dict of field→new value) such as swapping in a new background video URL, updated caption text, or brand colors — this pattern generalizes directly to a local Remotion-based system by treating brand-kit fields as the same kind of "modifications" dictionary passed as composition props [web:99].

## Multi-tenant implications
Because NLKE-SAG's stated goal includes a SaaS marketplace, brand kits should be modeled as a **first-class tenant-scoped entity** (not per-video settings) — i.e., a brand kit belongs to a creator/workspace and is referenced by ID when submitting a render job, analogous to how Ayrshare's `profileKey` scopes social publishing credentials per tenant (see KB #1 doc 06). This allows:
- Creators managing multiple brands/shows to switch brand kits per project without re-entering settings.
- Template reuse across a creator's entire content library.
- Potential future marketplace feature: creators could sell/share brand kit templates with each other.

## Recommendation for NLKE-SAG
Model brand kits as a tenant-scoped database entity with fields for color palette, typography, logo assets, and reusable intro/outro/lower-third/watermark component references, implemented as parameterized Remotion compositions. Pass brand-kit data into the render pipeline as a props object at job-submission time (mirroring the Creatomate `modifications` pattern), and store a `brandKitId` reference on every render job for consistent application and, longer-term, marketplace template sharing between tenants.
