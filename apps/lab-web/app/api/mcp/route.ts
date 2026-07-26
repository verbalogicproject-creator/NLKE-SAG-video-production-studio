import { randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { sagEngine } from '@/lib/engine';
import { apiError, jsonSafe } from '@/lib/http';
import { buildMcpManifest, LAB_MCP_TOOLS } from '@/lib/mcp-tools';
import { storage } from '@/lib/storage';
import { requireApiKey } from '@/lib/workspace';
import { resolveBrandContract } from '@/lib/brand-contract';

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
  if (name.startsWith('sequence.') || name.startsWith('action.') || name.startsWith('spatial.') || name.startsWith('semantic.') || name.startsWith('journal.')) {
    const sequence = await db.studioSequence.findFirst({
      where: { id: String(input.sequenceId), project: { workspaceId }, archivedAt: null },
      include: { project: true },
    });
    if (!sequence) throw Object.assign(new Error('sequence not found'), { status: 404 });
    if (name === 'sequence.context') {
      const context = await sagEngine.context(workspaceId, sequence.engineProjectId);
      return { sequence, context };
    }
    if (name === 'spatial.snapshot' || name === 'spatial.focus' || name === 'spatial.hierarchy') {
      const snapshot = await sagEngine.spatialSnapshot(workspaceId, sequence.engineProjectId, {
        focusId: name === 'spatial.snapshot' ? String(input.focusId ?? '') || null : null,
        depth: name === 'spatial.hierarchy' ? 'system' : String(input.depth ?? 'context'),
        hopCount: Number(input.hopCount ?? 2),
      });
      return name === 'spatial.focus' ? {
        projectId: sequence.engineProjectId, revision: snapshot.canonical_revision,
        projectionHash: snapshot.projection_hash, focus: snapshot.focus,
      } : snapshot;
    }
    if (name === 'spatial.neighborhood') return sagEngine.spatialNeighborhood(
      workspaceId, sequence.engineProjectId, String(input.entityId), Number(input.hopCount ?? 2),
    );
    if (name === 'spatial.blast_radius') return sagEngine.spatialBlastRadius(
      workspaceId, sequence.engineProjectId, String(input.entityId),
    );
    if (name === 'spatial.directive') return sagEngine.requestSpatialDirective(
      workspaceId, sequence.engineProjectId, {
        action: input.action, target_ids: input.targetIds ?? [], expected_revision: input.expectedRevision,
        expected_projection_hash: input.expectedProjectionHash, trace_id: input.traceId,
        intended_observed_effect: { target_ids: input.targetIds ?? [] },
      },
    );
    if (name === 'spatial.receipt.verify') {
      const receipt = await sagEngine.receipt(workspaceId, String(input.receiptId));
      if (receipt.project_id !== sequence.engineProjectId || !String(receipt.command).startsWith('spatial.')) {
        throw Object.assign(new Error('receipt is outside the requested sequence or is not spatial'), { status: 403 });
      }
      return {
        receiptId: receipt.id, command: receipt.command, status: receipt.status,
        observed: ['observed_success', 'observed_failure', 'timeout'].includes(String(receipt.status)),
        payload: receipt.payload,
      };
    }
    if (name === 'semantic.graph') return sagEngine.semanticGraph(
      workspaceId, sequence.engineProjectId, input.revision === undefined ? undefined : Number(input.revision),
    );
    if (name === 'semantic.neighborhood') return sagEngine.semanticNeighborhood(
      workspaceId, sequence.engineProjectId, {
        schema_version: 'sag-neighborhood/0.1-draft', scope_uri: input.scopeUri, seed_uris: input.seedUris,
        mode: input.mode ?? 'adjacent', relationship_kinds: input.relationshipKinds ?? [],
        max_hops: input.maxHops ?? 2, entity_limit: input.entityLimit ?? 200,
        edge_limit: input.edgeLimit ?? 400, include_provenance: input.includeProvenance ?? true,
      },
    );
    if (name === 'journal.list') return sagEngine.journalEntries(
      workspaceId, sequence.engineProjectId, Number(input.limit ?? 200),
    );
    if (name === 'journal.verify') return sagEngine.verifyJournal(workspaceId, sequence.engineProjectId);
    if (name === 'journal.append') return sagEngine.appendJournalEntry(
      workspaceId, sequence.engineProjectId, {
        id: input.entryId, kind: input.kind, content: input.content, created_at: input.createdAt,
        metadata: input.metadata ?? {}, tags: input.tags ?? [], session_id: input.sessionId,
      },
    );
    if (name === 'action.catalog') return sagEngine.activeCommands(workspaceId, sequence.engineProjectId);
    if (name === 'action.propose') return sagEngine.propose(
      workspaceId, sequence.engineProjectId,
      input.commands as Array<{ command: string; arguments: Record<string, unknown> }>,
      Number(input.expectedRevision),
    );
    if (name === 'action.execute') return sagEngine.command(
      workspaceId, sequence.engineProjectId, String(input.command),
      input.arguments as Record<string, unknown>, Number(input.expectedRevision), String(input.requestId),
    );
    if (name === 'action.batch') return sagEngine.batch(
      workspaceId, sequence.engineProjectId,
      input.commands as Array<{ command: string; arguments: Record<string, unknown> }>,
      Number(input.expectedRevision), String(input.requestId),
    );
  }
  if (name === 'operations.queue') {
    const [activeHeavy, byState] = await Promise.all([
      db.canonicalJob.count({ where: { kind: { in: ['ANALYSIS', 'RENDER'] }, state: { in: ['CLAIMED', 'RUNNING'] } } }),
      db.canonicalJob.groupBy({ by: ['state'], _count: { _all: true } }),
    ]);
    return { activeHeavy, configuredHeavyLimit: Number(process.env.GLOBAL_HEAVY_JOB_LIMIT ?? '2'), byState };
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
    const catalog = await sagEngine.activeCommands(workspaceId, row.engineProjectId) as { eligibility?: Array<{ name: string; eligible: boolean }> };
    if (!catalog.eligibility?.some((entry) => entry.name === command && entry.eligible)) {
      throw Object.assign(new Error('command is not eligible in the effective registry'), { status: 422 });
    }
    const result = await sagEngine.command(
      workspaceId, row.engineProjectId, command, input.arguments as Record<string, unknown>,
      Number(input.expectedRevision), String(input.requestId),
    );
    const project = (result as { project?: { revision?: number } }).project;
    if (project?.revision) await db.chamberVariant.update({ where: { id: row.id }, data: { engineRevision: project.revision } });
    return result;
  }
  if (name === 'render.start') {
    if (process.env.CLOUD_EXECUTION_ENABLED === 'true') {
      const revision = Number(input.projectRevision);
      const requestId = String(input.requestId);
      if (!Number.isInteger(revision) || revision !== row.engineRevision) {
        throw Object.assign(new Error(`stale project revision: expected ${row.engineRevision}, received ${revision}`), { status: 409 });
      }
      const workspace = await db.workspace.findUniqueOrThrow({ where: { id: workspaceId } });
      const startOfDay = new Date();
      startOfDay.setUTCHours(0, 0, 0, 0);
      const brand = await resolveBrandContract(workspaceId);
      if (brand.contract_hash !== row.chamberRun.brandContractHash) {
        throw Object.assign(new Error('brand contract changed; regenerate drafts'), { status: 409 });
      }
      const jobId = randomUUID();
      const acceptedJobId = await db.$transaction(async (tx) => {
        await tx.$executeRaw`SELECT pg_advisory_xact_lock(hashtext(${`sag-render:${workspaceId}`}))`;
        const duplicate = await tx.canonicalJob.findUnique({
          where: { workspaceId_requestId: { workspaceId, requestId } },
        });
        if (duplicate) {
          if (duplicate.kind !== 'RENDER' || duplicate.canonicalEntityId !== row.id) {
            throw Object.assign(new Error('request ID was already used for another mutation'), { status: 409 });
          }
          return duplicate.id;
        }
        const lockedActive = await tx.chamberVariant.count({
          where: { chamberRun: { project: { workspaceId } }, status: { in: ['RENDERING', 'VERIFYING'] } },
        });
        if (lockedActive >= workspace.renderConcurrencyLimit) {
          throw Object.assign(new Error('render concurrency quota exceeded'), { status: 409 });
        }
        const lockedDaily = await tx.quotaLedger.aggregate({
          where: { workspaceId, kind: 'RENDER_DAILY', occurredAt: { gte: startOfDay } }, _sum: { amount: true },
        });
        if ((lockedDaily._sum.amount ?? 0n) >= BigInt(workspace.dailyRenderLimit)) {
          throw Object.assign(new Error('daily render quota exceeded'), { status: 409 });
        }
        await tx.canonicalJob.create({ data: {
          id: jobId, workspaceId, projectId: row.chamberRun.projectId, kind: 'RENDER',
          state: 'DISPATCH_PENDING', requestId, canonicalEntityId: row.id,
          inputVersion: 'sag-render-job-1', inputSnapshot: {
            workspaceId, chamberRunId: runId, chamberVariantId: row.id, variant,
            engineProjectId: row.engineProjectId, projectRevision: revision,
            requestId, brandContractHash: brand.contract_hash,
          }, outbox: { create: {} },
        } });
        await tx.chamberVariant.update({ where: { id: row.id }, data: { engineRevision: revision, renderJobId: jobId, status: 'RENDERING' } });
        await tx.chamberRun.update({ where: { id: runId }, data: { status: 'RENDERING' } });
        await tx.quotaLedger.create({ data: { workspaceId, kind: 'RENDER_DAILY', amount: 1, requestId, metadata: { chamberRunId: runId, variant } } });
        return jobId;
      });
      return { id: null, status: 'accepted', payload: { job_id: acceptedJobId }, project_revision: revision };
    }
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
        serverInfo: { name: 'sag-video', version: '2.0.0' },
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
