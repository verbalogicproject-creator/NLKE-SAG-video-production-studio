/**
 * MCP manifest (re-exported). Import from '@verbalogix/lab-sdk/mcp' if you're
 * embedding the Lab as an MCP server inside a larger Claude-powered agent.
 *
 * Actual tool execution is done by the server — this manifest is discovery-only.
 */

export const LAB_MCP_MANIFEST_URL = (baseUrl = 'https://lab.verbalogix.com') =>
  `${baseUrl}/api/mcp`;

export const LAB_MCP_TOOL_NAMES = [
  'lab_list_projects',
  'lab_create_project',
  'lab_get_project',
  'lab_upload_asset',
  'lab_trigger_atomize',
  'lab_list_renders',
  'lab_publish_render',
  'lab_get_brand_skill',
  'lab_update_brand_skill',
] as const;

export type LabMcpToolName = (typeof LAB_MCP_TOOL_NAMES)[number];
