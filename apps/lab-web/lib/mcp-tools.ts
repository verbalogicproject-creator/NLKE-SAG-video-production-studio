/**
 * MCP tool registry for the Lab.
 *
 * The same handlers that back `/api/*` REST routes are wrapped here into
 * MCP tool definitions. Auth: the MCP server validates a workspace API key
 * (SHA-256 hash matched against Workspace.apiKeyHash), in contrast to the
 * session-cookie-backed REST surface.
 *
 * Stubs return 501-shaped errors until Sprint 1 handlers land.
 */

export type McpTool = {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
};

export const LAB_MCP_TOOLS: McpTool[] = [
  {
    name: 'lab_list_projects',
    description: 'List projects in the caller\'s workspace.',
    inputSchema: {
      type: 'object',
      properties: {
        status: {
          type: 'string',
          enum: ['DRAFT', 'INGESTING', 'READY', 'ARCHIVED'],
          description: 'Optional status filter',
        },
        limit: { type: 'integer', default: 50, maximum: 200 },
      },
    },
  },
  {
    name: 'lab_create_project',
    description: 'Create a new project in the caller\'s workspace.',
    inputSchema: {
      type: 'object',
      required: ['name'],
      properties: {
        name:        { type: 'string', minLength: 1, maxLength: 200 },
        description: { type: 'string', maxLength: 2000 },
      },
    },
  },
  {
    name: 'lab_get_project',
    description: 'Fetch a project by id (with assets and renders).',
    inputSchema: {
      type: 'object',
      required: ['projectId'],
      properties: { projectId: { type: 'string' } },
    },
  },
  {
    name: 'lab_upload_asset',
    description:
      'Issue a presigned R2 PUT URL so the caller can upload a RAW asset directly. Returns the URL and the Asset id.',
    inputSchema: {
      type: 'object',
      required: ['projectId', 'filename', 'contentType', 'sizeBytes'],
      properties: {
        projectId:   { type: 'string' },
        filename:    { type: 'string' },
        contentType: { type: 'string' },
        sizeBytes:   { type: 'integer', minimum: 1 },
      },
    },
  },
  {
    name: 'lab_trigger_atomize',
    description:
      'Trigger the transcript atomizer for a project that already has a transcribed RAW asset. Enqueues render jobs for the workspace\'s default platform variants.',
    inputSchema: {
      type: 'object',
      required: ['projectId'],
      properties: {
        projectId: { type: 'string' },
        variants: {
          type: 'array',
          items: {
            type: 'string',
            enum: [
              'LINKEDIN_16_9',
              'YT_LONG_16_9',
              'YT_SHORTS_9_16',
              'TIKTOK_9_16',
              'IG_REELS_9_16',
              'FB_FEED_16_9',
            ],
          },
        },
      },
    },
  },
  {
    name: 'lab_list_renders',
    description: 'List render jobs for a project.',
    inputSchema: {
      type: 'object',
      required: ['projectId'],
      properties: { projectId: { type: 'string' } },
    },
  },
  {
    name: 'lab_publish_render',
    description:
      'Publish a completed render to one or more connected platforms. Fails if the workspace has not connected the platform or the render is not COMPLETED.',
    inputSchema: {
      type: 'object',
      required: ['renderJobId', 'platforms'],
      properties: {
        renderJobId: { type: 'string' },
        platforms: {
          type: 'array',
          items: {
            type: 'string',
            enum: ['YOUTUBE', 'LINKEDIN', 'TIKTOK', 'INSTAGRAM', 'FACEBOOK'],
          },
          minItems: 1,
        },
      },
    },
  },
  {
    name: 'lab_get_brand_skill',
    description: 'Read the workspace\'s brand.skill.md markdown contents.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'lab_update_brand_skill',
    description:
      'Replace the workspace\'s brand.skill.md contents. Bumps the version counter.',
    inputSchema: {
      type: 'object',
      required: ['markdown'],
      properties: { markdown: { type: 'string', maxLength: 100_000 } },
    },
  },
];

export function buildMcpManifest(baseUrl: string) {
  return {
    name: 'verbalogix-lab',
    version: '0.1.0',
    description: 'Verbalogix Lab — Claude-operated video editing. REST + MCP.',
    contact: {
      url: 'https://lab.verbalogix.com',
      email: 'support@verbalogix.com',
    },
    serverUrl: `${baseUrl}/api/mcp`,
    auth: {
      type: 'bearer',
      description:
        'Workspace API key. Generate in Lab UI → Settings → API Keys. Sent as Authorization: Bearer <key>.',
    },
    tools: LAB_MCP_TOOLS,
  };
}
