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
    version: '1.0.0',
    serverUrl: `${baseUrl}/api/mcp`,
    transport: 'streamable-http',
    auth: { type: 'bearer', description: 'Workspace-scoped API key' },
    tools: LAB_MCP_TOOLS.map(({ requiredScope: _requiredScope, ...tool }) => tool),
  };
}
