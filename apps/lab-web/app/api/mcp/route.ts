import { NextResponse } from 'next/server';
import { buildMcpManifest, LAB_MCP_TOOLS } from '@/lib/mcp-tools';

// GET /api/mcp — returns the MCP manifest (tool list) for discovery.
export async function GET(req: Request) {
  const url = new URL(req.url);
  return NextResponse.json(buildMcpManifest(`${url.protocol}//${url.host}`));
}

// POST /api/mcp — tool invocation endpoint.
// Body: { tool: string, input: object }
// Auth: Authorization: Bearer <workspace-api-key>
//
// Sprint 1 stub: validates the tool name exists, returns 501 until each
// handler is wired up (week 3, share REST handlers via /lib).
export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  if (!body || typeof body.tool !== 'string') {
    return NextResponse.json({ error: 'BadRequest', message: 'Body must be {tool, input}' }, { status: 400 });
  }
  const tool = LAB_MCP_TOOLS.find((t) => t.name === body.tool);
  if (!tool) {
    return NextResponse.json(
      { error: 'ToolNotFound', message: `Unknown tool: ${body.tool}` },
      { status: 404 },
    );
  }
  return NextResponse.json(
    { error: 'NotImplemented', message: `Handler for ${tool.name} lands in Sprint 1 Week 3.` },
    { status: 501 },
  );
}
