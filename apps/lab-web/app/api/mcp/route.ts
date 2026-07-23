import { randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { sagEngine } from '@/lib/engine';
import { apiError, jsonSafe } from '@/lib/http';
import { buildMcpManifest, LAB_MCP_TOOLS } from '@/lib/mcp-tools';
import { storage } from '@/lib/storage';
import { requireApiKey } from '@/lib/workspace';

const EDIT_COMMANDS = new Set([
  'timeline.trim_clip', 'timeline.set_title', 'timeline.set_caption_style',
  'timeline.set_crop_keyframes', 'timeline.set_clip_transform', 'timeline.set_audio_gain',
]);

export async function GET(request: Request) {
  try {
    await requireApiKey(request, ['projects:read']);
    const url = new URL(request.url);
    return NextResponse.json(buildMcpManifest(url.origin));
  } catch (error) { return apiError(error); }
}

async function callTool(request: Request, name: string, input: Record<string, unknown>) {
  const tool = LAB_MCP_TOOLS.find((entry) => entry.name === name);
  if (!tool) throw Object.assign(new Error(`unknown tool: ${name}`), { status: 404, code: 'tool_not_found' });
  const principal = await requireApiKey(request, [tool.requiredScope]);
  const workspaceId = principal.workspaceId;
  if (name === 'projects.list') {
    return db.project.findMany({ where: { workspaceId }, include: { assets: true }, orderBy: { updatedAt: 'desc' } });
  }
  if (name === 'drafts.review') {
    return db.chamberRun.findFirstOrThrow({ where: { id: String(input.runId), project: { workspaceId } }, include: { variants: true } });
  }
  if (name === 'approvals.list') {
    return db.publicationApproval.findMany({ where: { workspaceId }, orderBy: { createdAt: 'desc' }, take: 50 });
  }
  if (name === 'download.create') {
    const asset = await db.asset.findFirst({ where: { id: String(input.artifactAssetId), project: { workspaceId }, kind: 'DELIVERABLE' }, include: { storageObject: true } });
    if (!asset?.verifiedAt || !asset.sha256 || !asset.storageObject) throw Object.assign(new Error('verified stored artifact required'), { status: 409 });
    return { url: await storage().signedDownload(asset.storageObject, 900), expiresInSeconds: 900, sha256: asset.sha256 };
  }
  if (name === 'youtube.publish_private') {
    const response = await fetch(new URL('/api/youtube/publish', request.url), {
      method: 'POST', headers: { authorization: request.headers.get('authorization')!, 'content-type': 'application/json' },
      body: JSON.stringify({ approvalId: input.approvalId }),
    });
    const body = await response.json();
    if (!response.ok) throw Object.assign(new Error(String(body.message ?? body.error)), { status: response.status });
    return body;
  }
  const runId = String(input.runId);
  if (name === 'evidence.get') {
    const run = await db.chamberRun.findFirst({ where: { id: runId, project: { workspaceId } }, include: { variants: true } });
    if (!run) throw Object.assign(new Error('chamber run not found'), { status: 404 });
    const receipt = await sagEngine.receipt(workspaceId, String(input.receiptId));
    const receiptProject = String(receipt.project_id ?? '');
    const allowedProjects = new Set([run.engineProjectId, ...run.variants.map((entry) => entry.engineProjectId).filter(Boolean)]);
    if (!allowedProjects.has(receiptProject)) throw Object.assign(new Error('receipt is outside the requested run'), { status: 403 });
    return receipt;
  }
  const variant = String(input.variant);
  const row = await db.chamberVariant.findFirst({
    where: { chamberRunId: runId, variant: variant as never, chamberRun: { project: { workspaceId } } },
    include: { chamberRun: true },
  });
  if (!row?.engineProjectId) throw Object.assign(new Error('accepted draft not found'), { status: 404 });
  if (name === 'project.get') return sagEngine.project(workspaceId, row.engineProjectId);
  if (name === 'focused_edit.apply') {
    const command = String(input.command);
    if (!EDIT_COMMANDS.has(command)) throw Object.assign(new Error('command is outside focused-edit scope'), { status: 422 });
    const result = await sagEngine.command(
      workspaceId, row.engineProjectId, command, input.arguments as Record<string, unknown>,
      Number(input.expectedRevision), String(input.requestId),
    );
    const project = (result as { project?: { revision?: number } }).project;
    if (project?.revision) await db.chamberVariant.update({ where: { id: row.id }, data: { engineRevision: project.revision } });
    return result;
  }
  if (name === 'render.start') {
    const receipt = await sagEngine.render(workspaceId, row.engineProjectId, Number(input.projectRevision), String(input.requestId));
    await db.chamberVariant.update({ where: { id: row.id }, data: {
      engineRevision: Number(input.projectRevision), renderJobId: receipt.payload.job_id, receiptId: receipt.id, status: 'RENDERING',
    } });
    await db.chamberRun.update({ where: { id: runId }, data: { status: 'RENDERING' } });
    return receipt;
  }
  throw Object.assign(new Error(`unhandled tool: ${name}`), { status: 500 });
}

export async function POST(request: Request) {
  let id: unknown = null;
  try {
    const body = await request.json() as { jsonrpc?: string; id?: unknown; method?: string; params?: Record<string, unknown> };
    id = body.id ?? null;
    if (body.jsonrpc !== '2.0' || !body.method) return NextResponse.json({ jsonrpc: '2.0', id, error: { code: -32600, message: 'Invalid Request' } }, { status: 400 });
    if (body.method === 'notifications/initialized') return new NextResponse(null, { status: 202 });
    if (body.method === 'initialize') {
      await requireApiKey(request, ['projects:read']);
      return NextResponse.json({ jsonrpc: '2.0', id, result: {
        protocolVersion: '2025-03-26', capabilities: { tools: { listChanged: false } },
        serverInfo: { name: 'sag-video-chamber', version: '1.0.0' },
      } }, { headers: { 'mcp-session-id': randomUUID() } });
    }
    if (body.method === 'tools/list') {
      await requireApiKey(request, ['projects:read']);
      return NextResponse.json({ jsonrpc: '2.0', id, result: { tools: LAB_MCP_TOOLS.map(({ requiredScope: _scope, ...tool }) => tool) } });
    }
    if (body.method === 'tools/call') {
      const params = body.params as { name?: string; arguments?: Record<string, unknown> };
      const result = await callTool(request, String(params?.name ?? ''), params?.arguments ?? {});
      return NextResponse.json({ jsonrpc: '2.0', id, result: { content: [{ type: 'text', text: JSON.stringify(jsonSafe(result)) }] } });
    }
    return NextResponse.json({ jsonrpc: '2.0', id, error: { code: -32601, message: 'Method not found' } }, { status: 404 });
  } catch (error) {
    const value = error as { message?: string; status?: number };
    return NextResponse.json({ jsonrpc: '2.0', id, error: { code: -32000, message: value.message ?? 'Tool execution failed' } }, { status: value.status ?? 500 });
  }
}
