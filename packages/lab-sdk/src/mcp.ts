/**
 * MCP manifest (re-exported). Import from '@verbalogix/lab-sdk/mcp' if you're
 * embedding the Lab as an MCP server inside a larger Claude-powered agent.
 *
 * Actual tool execution is done by the server — this manifest is discovery-only.
 */

export const LAB_MCP_MANIFEST_URL = (baseUrl = 'https://lab.verbalogix.com') =>
  `${baseUrl}/api/mcp`;

export const LAB_MCP_TOOL_NAMES = [
  'projects.list',
  'drafts.review',
  'project.get',
  'focused_edit.apply',
  'render.start',
  'evidence.get',
  'approvals.list',
  'download.create',
  'youtube.publish_private',
] as const;

export type LabMcpToolName = (typeof LAB_MCP_TOOL_NAMES)[number];
