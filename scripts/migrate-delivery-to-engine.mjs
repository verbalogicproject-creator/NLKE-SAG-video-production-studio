import { PrismaClient } from '@prisma/client';

const apply = process.argv.includes('--apply');
const projectArgument = process.argv.find((argument) => argument.startsWith('--project='));
const projectFilter = projectArgument?.slice('--project='.length);
const engineUrl = (process.env.SAG_ENGINE_URL ?? 'http://127.0.0.1:8080').replace(/\/$/, '');
const serviceToken = process.env.SAG_VIDEO_SERVICE_TOKEN;

if (apply && !serviceToken) throw new Error('SAG_VIDEO_SERVICE_TOKEN is required with --apply');

const prisma = new PrismaClient();

function profilePayload(profile) {
  return {
    id: profile.id,
    destination: profile.destination,
    aspect_ratio: profile.aspectRatio,
    width: profile.width,
    height: profile.height,
    caption_placement: profile.captionPlacement,
    safe_zone_x: profile.safeZoneX,
    safe_zone_y: profile.safeZoneY,
    metadata: profile.metadata ?? {},
    created_at: profile.createdAt.toISOString(),
    updated_at: profile.updatedAt.toISOString(),
  };
}

function approvalPayload(approval) {
  return {
    id: approval.id,
    project_revision: approval.sequenceRevision,
    bundle_hash: approval.bundleHash,
    artifact_hashes: approval.artifactHashes,
    destinations: approval.destinations,
    state: approval.state.toLowerCase(),
    approved_by: approval.approvedById,
    expires_at: approval.expiresAt.toISOString(),
    consumed_at: approval.consumedAt?.toISOString(),
    created_at: approval.createdAt.toISOString(),
    attempts: approval.attempts.map((attempt) => ({
      id: attempt.id,
      destination: attempt.destination,
      idempotency_key: attempt.idempotencyKey,
      state: attempt.state.toLowerCase(),
      external_id: attempt.externalId,
      bounded_error: attempt.boundedError,
      attempt: attempt.attempt,
      created_at: attempt.createdAt.toISOString(),
      updated_at: attempt.updatedAt.toISOString(),
    })),
  };
}

async function send(sequence, body) {
  const response = await fetch(`${engineUrl}/api/projects/${encodeURIComponent(sequence.engineProjectId)}/delivery/import`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-sag-service-token': serviceToken,
      'x-sag-workspace-id': sequence.project.workspaceId,
    },
    body: JSON.stringify(body),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`delivery import for ${sequence.id} failed (${response.status}): ${JSON.stringify(result)}`);
  return result;
}

try {
  const sequences = await prisma.studioSequence.findMany({
    where: projectFilter ? {
      OR: [{ id: projectFilter }, { projectId: projectFilter }, { engineProjectId: projectFilter }],
    } : undefined,
    include: {
      project: { select: { id: true, workspaceId: true } },
      deliveryProfiles: true,
      releaseApprovals: { include: { attempts: true }, orderBy: { createdAt: 'asc' } },
    },
    orderBy: { createdAt: 'asc' },
  });
  const report = [];
  for (const sequence of sequences) {
    const body = {
      profiles: sequence.deliveryProfiles.map(profilePayload),
      approvals: sequence.releaseApprovals.map(approvalPayload),
    };
    const counts = {
      profiles: body.profiles.length,
      approvals: body.approvals.length,
      attempts: body.approvals.reduce((total, approval) => total + approval.attempts.length, 0),
    };
    const result = apply && (counts.profiles || counts.approvals) ? await send(sequence, body) : null;
    report.push({
      controlProjectId: sequence.project.id,
      sequenceId: sequence.id,
      engineProjectId: sequence.engineProjectId,
      workspaceId: sequence.project.workspaceId,
      counts,
      applied: Boolean(result),
      engineIds: result ? { profiles: result.profiles, approvals: result.approvals, attempts: result.attempts } : undefined,
    });
  }
  console.log(JSON.stringify({ mode: apply ? 'apply' : 'dry-run', engineUrl, sequences: report }, null, 2));
  if (!apply) console.error('Dry run only. Re-run with --apply after reviewing the report.');
} finally {
  await prisma.$disconnect();
}
