# Social Media Auto-Publishing APIs (SaaS Marketplace / Distribution Layer)

## Ayrshare
- **What**: Unified Social Media API letting apps/platforms/AI agents post, schedule, analyze, and manage engagement across 13+ social networks through one integration (Facebook, Instagram, X/Twitter, LinkedIn, TikTok, YouTube, Reddit, Telegram, Threads, Pinterest, etc.) [web:86][web:94][web:88].
- **Node.js SDK**: npm package `social-media-api` — wraps RESTful calls; `npm i social-media-api` [web:90].
- **Core usage**:
```javascript
const SocialPost = require("social-media-api");
const social = new SocialPost(API_KEY);
const post = await social.post({
  post: "Caption text",
  platforms: ["twitter", "facebook", "linkedin", "instagram", "tiktok"],
  mediaUrls: ["https://example.com/video.mp4"],
  scheduleDate: "2025-12-01T10:00:00Z"
});
const history = await social.history();
await social.delete({ id: post.id });
```
[web:90][web:94]
- **Multi-tenant SaaS support**: `profileKey` parameter lets one app manage many end-users' connected social accounts under a single Ayrshare Business account — directly relevant to the "SaaS marketplace" revenue model, since NLKE-SAG could onboard creators and post on their behalf via per-user Profile Keys [web:90].
- **X/Twitter caveat**: As of March 31 2026, X-bound posts require the developer's own X Developer App credentials (BYO keys) attached via `setTwitterByo(apiKey, apiSecret)` on the SDK instance — plan for this compliance/config step [web:90].
- **Demo reference app**: `ayrshare/social-api-demo` — React + Node.js reference implementation showing compose/schedule/post UI across multiple networks, useful as a UI/UX starting template [web:97].
- **Additional integration surface**: no-code guides for Airtable, Bubble.io, Make, n8n (AI agent → MCP server), Notion, Retool, plus a Python SDK — useful if any part of the pipeline needs low-code glue [web:85].

## upload-post
- **What**: Alternative Node.js/npm client library (`upload-post`) for cross-platform social media upload — TikTok, Instagram, YouTube, LinkedIn, Facebook, Pinterest, Threads, Reddit, Bluesky, X/Twitter [web:81].
- **Relevance**: A lighter-weight, upload-focused alternative to Ayrshare if the pipeline mainly needs "publish video" rather than full scheduling/analytics/DM management.

## PostEverywhere
- **What**: Official Node.js SDK for scheduling/publishing to Instagram, X, TikTok, LinkedIn, YouTube, Facebook, Threads, Pinterest "from code or AI agents" — explicitly markets AI-agent compatibility and an MCP server for LLM-driven publishing workflows [web:71][web:78].
- **Relevance**: Positions itself as agent-native, which aligns with NLKE-SAG's AI-orchestrated pipeline — worth evaluating against Ayrshare for cost and platform coverage (11 platforms via typed SDK + hosted MCP server).

## Comparison Table

| Service | SDK | Platforms | Scheduling | Analytics | Multi-tenant (SaaS) support | AI-agent oriented |
|---|---|---|---|---|---|---|
| Ayrshare [web:86][web:90] | Node.js `social-media-api` | 13+ | Yes | Yes | Yes (`profileKey`) | Via n8n/MCP guide |
| upload-post [web:81] | Node.js `upload-post` | 9 | Limited/unclear | Unclear | Unclear | Not stated |
| PostEverywhere [web:71][web:78] | Node.js SDK | 8-11 | Yes | Yes | Unclear | Explicit (MCP server) |

**Recommendation**: For a SaaS marketplace serving multiple creators, Ayrshare's `profileKey`-based multi-tenant model is currently the most mature/documented option; PostEverywhere is worth a pilot given its explicit AI-agent/MCP focus, which may reduce custom glue code in an LLM-orchestrated pipeline.
