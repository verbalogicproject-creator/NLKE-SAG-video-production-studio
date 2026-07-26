export type McpTool = {
  name: string;
  description: string;
  requiredScope: string;
  inputSchema: Record<string, unknown>;
};

const object = (properties: Record<string, unknown>, required: string[] = []) => ({
  type: 'object', properties, required, additionalProperties: false,
});

export const LAB_MCP_TOOLS: McpTool[] = [
  { name: 'projects.list', description: 'List projects in the authenticated workspace.', requiredScope: 'projects:read', inputSchema: object({}) },
  { name: 'sequence.context', description: 'Read compact grounded context for one shared master sequence.', requiredScope: 'drafts:read', inputSchema: object({ sequenceId: { type: 'string' } }, ['sequenceId']) },
  { name: 'spatial.snapshot', description: 'Read the deterministic Studio spatial projection around an optional stable entity.', requiredScope: 'drafts:read', inputSchema: object({ sequenceId: { type: 'string' }, focusId: { type: 'string' }, depth: { type: 'string', enum: ['edit', 'context', 'system'] }, hopCount: { type: 'integer', minimum: 0, maximum: 6 } }, ['sequenceId']) },
  { name: 'spatial.focus', description: 'Read the exact current focus identities and projection hash.', requiredScope: 'drafts:read', inputSchema: object({ sequenceId: { type: 'string' } }, ['sequenceId']) },
  { name: 'spatial.neighborhood', description: 'Read a bounded causal neighborhood around one stable local entity ID.', requiredScope: 'drafts:read', inputSchema: object({ sequenceId: { type: 'string' }, entityId: { type: 'string' }, hopCount: { type: 'integer', minimum: 0, maximum: 6 } }, ['sequenceId', 'entityId']) },
  { name: 'spatial.hierarchy', description: 'Read the production-wide semantic hierarchy used by System depth.', requiredScope: 'drafts:read', inputSchema: object({ sequenceId: { type: 'string' } }, ['sequenceId']) },
  { name: 'spatial.blast_radius', description: 'Trace bounded downstream effects from one stable local entity ID.', requiredScope: 'drafts:read', inputSchema: object({ sequenceId: { type: 'string' }, entityId: { type: 'string' } }, ['sequenceId', 'entityId']) },
  { name: 'spatial.frame.current', description: 'Read the latest revision-bound viewport declaration and semantic region bindings.', requiredScope: 'drafts:read', inputSchema: object({ sequenceId: { type: 'string' } }, ['sequenceId']) },
  { name: 'spatial.region.resolve', description: 'Resolve one semantic entity, adaptive-grid cell, or normalized point in a declared frame.', requiredScope: 'drafts:read', inputSchema: object({ sequenceId: { type: 'string' }, frameId: { type: 'string' }, entityId: { type: 'string' }, cell: { type: 'string' }, point: object({ x: { type: 'number', minimum: 0, maximum: 1 }, y: { type: 'number', minimum: 0, maximum: 1 } }, ['x', 'y']), minimumConfidence: { type: 'number', minimum: 0, maximum: 1 } }, ['sequenceId', 'frameId']) },
  { name: 'spatial.directive', description: 'Dispatch a registry-declared view action; visible success requires a later browser ACK.', requiredScope: 'edits:write', inputSchema: object({ sequenceId: { type: 'string' }, action: { type: 'string' }, targetIds: { type: 'array', maxItems: 24, items: { type: 'string' } }, expectedRevision: { type: 'integer', minimum: 1 }, expectedProjectionHash: { type: 'string' }, expectedFrameId: { type: 'string' }, bindingId: { type: 'string' }, traceId: { type: 'string' } }, ['sequenceId', 'action', 'expectedRevision', 'expectedProjectionHash']) },
  { name: 'spatial.receipt.verify', description: 'Verify the browser-observed terminal state of one spatial directive receipt.', requiredScope: 'evidence:read', inputSchema: object({ sequenceId: { type: 'string' }, receiptId: { type: 'string' } }, ['sequenceId', 'receiptId']) },
  { name: 'semantic.graph', description: 'Read the provider-neutral X1 draft graph over the same authoritative spatial identities.', requiredScope: 'drafts:read', inputSchema: object({ sequenceId: { type: 'string' }, revision: { type: 'integer', minimum: 1 } }, ['sequenceId']) },
  { name: 'semantic.neighborhood', description: 'Run deterministic URI-based adjacent, upstream, downstream, or blast-radius traversal.', requiredScope: 'drafts:read', inputSchema: object({ sequenceId: { type: 'string' }, scopeUri: { type: 'string' }, seedUris: { type: 'array', minItems: 1, maxItems: 32, items: { type: 'string' } }, mode: { type: 'string', enum: ['adjacent', 'upstream', 'downstream', 'blast-radius'] }, relationshipKinds: { type: 'array', maxItems: 32, items: { type: 'string' } }, maxHops: { type: 'integer', minimum: 0, maximum: 6 }, entityLimit: { type: 'integer', minimum: 1, maximum: 1000 }, edgeLimit: { type: 'integer', minimum: 0, maximum: 2000 }, includeProvenance: { type: 'boolean' } }, ['sequenceId', 'scopeUri', 'seedUris']) },
  { name: 'journal.list', description: 'List bounded durable causal entries; disposable runtime telemetry is excluded.', requiredScope: 'journal:read', inputSchema: object({ sequenceId: { type: 'string' }, limit: { type: 'integer', minimum: 1, maximum: 1000 } }, ['sequenceId']) },
  { name: 'journal.verify', description: 'Verify the tamper-evident journal chain and report its first continuity break.', requiredScope: 'journal:read', inputSchema: object({ sequenceId: { type: 'string' } }, ['sequenceId']) },
  { name: 'journal.append', description: 'Append one registered, bounded, idempotent causal journal entry.', requiredScope: 'journal:write', inputSchema: object({ sequenceId: { type: 'string' }, entryId: { type: 'string' }, kind: { type: 'string' }, content: { type: 'string' }, createdAt: { type: 'string' }, metadata: { type: 'object' }, tags: { type: 'array', maxItems: 100, items: { type: 'string' } }, sessionId: { type: 'string' } }, ['sequenceId', 'entryId', 'kind', 'content', 'createdAt']) },
  { name: 'action.catalog', description: 'Read the effective registry-driven action catalog and eligibility reasons.', requiredScope: 'drafts:read', inputSchema: object({ sequenceId: { type: 'string' } }, ['sequenceId']) },
  { name: 'action.propose', description: 'Preview an atomic semantic edit batch without mutating the sequence.', requiredScope: 'drafts:read', inputSchema: object({ sequenceId: { type: 'string' }, expectedRevision: { type: 'integer', minimum: 1 }, commands: { type: 'array', minItems: 1, items: { type: 'object' } } }, ['sequenceId', 'expectedRevision', 'commands']) },
  { name: 'action.execute', description: 'Execute one registry-declared, revision-checked action.', requiredScope: 'edits:write', inputSchema: object({ sequenceId: { type: 'string' }, command: { type: 'string' }, arguments: { type: 'object' }, expectedRevision: { type: 'integer', minimum: 1 }, requestId: { type: 'string' } }, ['sequenceId', 'command', 'arguments', 'expectedRevision', 'requestId']) },
  { name: 'action.batch', description: 'Commit an all-or-nothing batch of safe registry-declared actions.', requiredScope: 'edits:write', inputSchema: object({ sequenceId: { type: 'string' }, expectedRevision: { type: 'integer', minimum: 1 }, commands: { type: 'array', minItems: 1, items: { type: 'object' } }, requestId: { type: 'string' } }, ['sequenceId', 'expectedRevision', 'commands', 'requestId']) },
  { name: 'operations.queue', description: 'Read aggregate canonical queue pressure and heavy-job concurrency.', requiredScope: 'operations:read', inputSchema: object({}) },
  { name: 'drafts.review', description: 'Review the three platform drafts and their source evidence.', requiredScope: 'drafts:read', inputSchema: object({ runId: { type: 'string' } }, ['runId']) },
  { name: 'project.get', description: 'Read the canonical SAG project and exact revision for an accepted draft.', requiredScope: 'drafts:read', inputSchema: object({ runId: { type: 'string' }, variant: { type: 'string', enum: ['YT_SHORTS_9_16', 'TIKTOK_9_16', 'IG_REELS_9_16'] } }, ['runId', 'variant']) },
  { name: 'focused_edit.apply', description: 'Apply one revision-checked trim, title, caption, crop, gain, or mute edit.', requiredScope: 'edits:write', inputSchema: object({ runId: { type: 'string' }, variant: { type: 'string' }, command: { type: 'string' }, arguments: { type: 'object' }, expectedRevision: { type: 'integer', minimum: 1 }, requestId: { type: 'string' } }, ['runId', 'variant', 'command', 'arguments', 'expectedRevision', 'requestId']) },
  { name: 'render.start', description: 'Render one exact accepted draft revision.', requiredScope: 'renders:write', inputSchema: object({ runId: { type: 'string' }, variant: { type: 'string' }, projectRevision: { type: 'integer', minimum: 1 }, requestId: { type: 'string' } }, ['runId', 'variant', 'projectRevision', 'requestId']) },
  { name: 'evidence.get', description: 'Read a causal render or edit receipt with observation evidence.', requiredScope: 'evidence:read', inputSchema: object({ receiptId: { type: 'string' }, runId: { type: 'string' } }, ['receiptId', 'runId']) },
  { name: 'approvals.list', description: 'List publication approvals. Agents cannot create approvals.', requiredScope: 'approvals:read', inputSchema: object({}) },
  { name: 'download.create', description: 'Create a short-lived download for a verified deliverable.', requiredScope: 'downloads:read', inputSchema: object({ artifactAssetId: { type: 'string' } }, ['artifactAssetId']) },
  { name: 'youtube.publish_private', description: 'Publish one verified artifact using an existing single-use human approval.', requiredScope: 'youtube:publish', inputSchema: object({ approvalId: { type: 'string' } }, ['approvalId']) },
];

export function buildMcpManifest(baseUrl: string) {
  return {
    name: 'sag-video-chamber',
    version: '2.0.0',
    serverUrl: `${baseUrl}/api/mcp`,
    transport: 'streamable-http',
    auth: { type: 'bearer', description: 'Workspace-scoped API key' },
    tools: LAB_MCP_TOOLS.map(({ requiredScope: _requiredScope, ...tool }) => tool),
  };
}
