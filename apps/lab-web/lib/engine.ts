import type {
  BrandContract,
  ChamberStartRequest,
  EngineJob,
  EngineSuggestion,
} from '@verbalogix/media-contracts';
import { GoogleAuth } from 'google-auth-library';

export type DirectorInput = {
  repository_url: string;
  ref?: string;
  creative_instructions: string;
  audience: string;
  goal: string;
  duration_seconds: number;
  visual_style: string;
  target_platform: string;
  brand_kit: string;
  reference_assets: string[];
};

export type RepositoryEvidence = {
  repository_url: string; ref: string; name: string; description: string; readme: string;
  files: string[]; manifests: Record<string, string>; languages: Record<string, number>;
};

export type CreativeBrief = {
  title: string; logline: string; audience_promise: string; tone: string; visual_language: string;
  narrative_arc: string[]; omni_prompt: string; veo_prompt: string; music_prompt: string;
  narration_guidance: string; evidence_revision: string; unsupported_claim_warnings: string[];
};

export type StoryboardScene = {
  id: string; start_seconds: number; duration_seconds: number; purpose: string; narration: string;
  visual_direction: string; evidence_refs: string[]; generation_model: string; locked?: boolean;
};

export type Storyboard = {
  title: string; hook: string; call_to_action: string; scenes: StoryboardScene[]; evidence_revision: string;
};

export type EngineReceipt = {
  id: string; command: string; status: string; actor: string; project_revision: number;
  created_at: string; updated_at?: string; payload?: Record<string, unknown>;
};

export type GenerationOperation = {
  kind: 'video' | 'music' | 'narration'; scene_id?: string; request_id: string; model: string;
  provider?: string; operation_name: string; state: string; asset_id?: string; error_code?: string;
  error_detail?: string; output?: Record<string, unknown>;
};

const baseUrl = () => (process.env.SAG_ENGINE_URL ?? 'http://127.0.0.1:8080').replace(/\/$/, '');

export const sagEngineUrl = baseUrl;

let identityClient: Awaited<ReturnType<GoogleAuth['getIdTokenClient']>> | undefined;

async function headers(workspaceId: string, json = true): Promise<HeadersInit> {
  const value: Record<string, string> = {
    'x-sag-workspace-id': workspaceId,
  };
  if (process.env.NODE_ENV === 'production') {
    identityClient ??= await new GoogleAuth().getIdTokenClient(baseUrl());
    Object.assign(value, await identityClient.getRequestHeaders());
  } else {
    value['x-sag-service-token'] = process.env.SAG_VIDEO_SERVICE_TOKEN ?? 'local-chamber-service';
  }
  if (json) value['content-type'] = 'application/json';
  return value;
}

export async function engineHeaders(workspaceId: string, json = true): Promise<HeadersInit> {
  return headers(workspaceId, json);
}

async function engineFetch<T>(workspaceId: string, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${baseUrl()}${path}`, {
    ...init,
    headers: { ...await headers(workspaceId, !(init.body instanceof FormData)), ...init.headers },
    cache: 'no-store',
  });
  const body = await response.json().catch(() => ({ detail: response.statusText }));
  if (!response.ok) {
    const error = new Error(String(body.detail ?? 'SAG engine request failed')) as Error & { code?: string; status?: number };
    error.code = body.code;
    error.status = response.status;
    throw error;
  }
  return body as T;
}

export const sagEngine = {
  health: () => fetch(`${baseUrl()}/health`, { cache: 'no-store' }).then((r) => r.json()),
  createProject: (workspaceId: string, name: string) => engineFetch<{ project: { id: string; revision: number } }>(
    workspaceId, '/api/projects', { method: 'POST', body: JSON.stringify({ name, preset: 'landscape_1080p', workspace_id: workspaceId }) },
  ),
  project: (workspaceId: string, projectId: string) => engineFetch<{ project: { id: string; revision: number; tracks?: Array<Record<string, unknown>> } }>(
    workspaceId, `/api/projects/${projectId}`,
  ),
  upload: (workspaceId: string, projectId: string, form: FormData) => engineFetch<Record<string, unknown>>(
    workspaceId, `/api/projects/${projectId}/assets/uploads`, { method: 'POST', body: form },
  ),
  startAnalysis: (workspaceId: string, request: ChamberStartRequest, brand: BrandContract) => engineFetch<EngineJob>(
    workspaceId, `/api/projects/${request.engineProjectId}/shorts/jobs`, {
      method: 'POST',
      body: JSON.stringify({
        source_revision: request.sourceRevision,
        asset_id: request.sourceAssetId,
        prompt: request.prompt,
        language: request.language ?? 'auto',
        candidate_count: Math.max(3, request.variants?.length ?? 3),
        min_duration_ticks: 1_800_000,
        max_duration_ticks: 7_200_000,
        aspect_ratio: '9:16',
        target_variants: request.variants ?? ['YT_SHORTS_9_16', 'TIKTOK_9_16', 'IG_REELS_9_16'],
        brand_contract: brand,
      }),
    },
  ),
  suggestShorts: (workspaceId: string, projectId: string, sourceRevision: number, assetId: string) => engineFetch<Record<string, unknown>>(
    workspaceId, `/api/projects/${projectId}/shorts/jobs`, {
      method: 'POST', body: JSON.stringify({
        source_revision: sourceRevision, asset_id: assetId, language: 'auto', candidate_count: 5,
        min_duration_ticks: 1_800_000, max_duration_ticks: 10_800_000, aspect_ratio: '9:16',
        target_variants: [], brand_contract: {},
      }),
    },
  ),
  job: (workspaceId: string, jobId: string) => engineFetch<EngineJob>(workspaceId, `/api/jobs/${jobId}`),
  suggestions: (workspaceId: string, projectId: string, jobId?: string) => engineFetch<{ suggestions: EngineSuggestion[] }>(
    workspaceId, `/api/projects/${projectId}/suggestions${jobId ? `?job_id=${encodeURIComponent(jobId)}` : ''}`,
  ),
  accept: (workspaceId: string, suggestionId: string, requestId: string, name?: string) => engineFetch<{
    project: { id: string; revision: number };
    receipt: { id: string };
  }>(workspaceId, `/api/suggestions/${suggestionId}/accept`, {
    method: 'POST', body: JSON.stringify({ request_id: requestId, actor: 'verbalogix-orchestrator', expected_state: 'pending', name }),
  }),
  render: (workspaceId: string, projectId: string, revision: number, requestId: string) => engineFetch<{
    id: string;
    payload: { job_id: string };
  }>(workspaceId, `/api/projects/${projectId}/renders`, {
    method: 'POST', body: JSON.stringify({ project_revision: revision, request_id: requestId, actor: 'verbalogix-orchestrator' }),
  }),
  receipt: (workspaceId: string, receiptId: string) => engineFetch<Record<string, unknown>>(workspaceId, `/api/receipts/${receiptId}`),
  artifact: (workspaceId: string, artifactId: string) => engineFetch<{
    id: string; managed_uri: string; sha256: string; byte_size: number; mime_type: string | null; provenance: Record<string, unknown>;
  }>(workspaceId, `/api/artifacts/${artifactId}`),
  cancel: (workspaceId: string, jobId: string) => engineFetch<EngineJob>(workspaceId, `/api/jobs/${jobId}/cancel`, { method: 'POST' }),
  command: (workspaceId: string, projectId: string, command: string, arguments_: Record<string, unknown>, expectedRevision: number, requestId: string, confirmationId?: string) =>
    engineFetch<Record<string, unknown>>(workspaceId, `/api/projects/${projectId}/commands`, {
      method: 'POST',
      body: JSON.stringify({
        command, arguments: arguments_, expected_revision: expectedRevision,
        request_id: requestId, actor: 'verbalogix-web', confirmation_id: confirmationId,
      }),
    }),
  context: (workspaceId: string, projectId: string) => engineFetch<Record<string, unknown>>(
    workspaceId, `/api/projects/${projectId}/context`,
  ),
  activeCommands: (workspaceId: string, projectId: string) => engineFetch<Record<string, unknown>>(
    workspaceId, `/api/projects/${projectId}/commands/active`,
  ),
  receipts: (workspaceId: string, projectId: string) => engineFetch<Record<string, unknown>>(
    workspaceId, `/api/projects/${projectId}/receipts`,
  ),
  propose: (workspaceId: string, projectId: string, commands: Array<{ command: string; arguments: Record<string, unknown> }>, expectedRevision: number) =>
    engineFetch<Record<string, unknown>>(workspaceId, `/api/projects/${projectId}/commands/propose`, {
      method: 'POST', body: JSON.stringify({ commands, expected_revision: expectedRevision }),
    }),
  batch: (workspaceId: string, projectId: string, commands: Array<{ command: string; arguments: Record<string, unknown> }>, expectedRevision: number, requestId: string, confirmationId?: string) =>
    engineFetch<Record<string, unknown>>(workspaceId, `/api/projects/${projectId}/commands/batch`, {
      method: 'POST', body: JSON.stringify({
        commands, expected_revision: expectedRevision, request_id: requestId,
        actor: 'verbalogix-web', confirmation_id: confirmationId,
      }),
    }),
  select: (workspaceId: string, projectId: string, itemIds: string[], expectedRevision: number, requestId: string) =>
    engineFetch<Record<string, unknown>>(workspaceId, `/api/projects/${projectId}/selection`, {
      method: 'POST', body: JSON.stringify({
        item_ids: itemIds, expected_revision: expectedRevision, request_id: requestId, actor: 'verbalogix-web',
      }),
    }),
  confirm: (workspaceId: string, projectId: string, command: string, arguments_: Record<string, unknown>, expectedRevision: number) =>
    engineFetch<{ id: string; expires_at: string }>(workspaceId, `/api/projects/${projectId}/confirmations`, {
      method: 'POST', body: JSON.stringify({ command, arguments: arguments_, expected_revision: expectedRevision }),
    }),
  pair: (workspaceId: string, projectId: string) => engineFetch<{ code: string; expires_at: string }>(
    workspaceId, '/api/pairing/start', {
      method: 'POST', body: JSON.stringify({ workspace_id: projectId, project_id: projectId, sequence_id: projectId }),
    },
  ),
  spatialSnapshot: (
    workspaceId: string, projectId: string,
    parameters: { focusId?: string | null; depth?: string; hopCount?: number } = {},
  ) => {
    const query = new URLSearchParams();
    if (parameters.focusId) query.set('focus_id', parameters.focusId);
    if (parameters.depth) query.set('depth', parameters.depth);
    if (parameters.hopCount !== undefined) query.set('hop_count', String(parameters.hopCount));
    return engineFetch<Record<string, unknown>>(
      workspaceId, `/api/projects/${projectId}/spatial/snapshot?${query.toString()}`,
    );
  },
  spatialNeighborhood: (workspaceId: string, projectId: string, entityId: string, hopCount = 2) =>
    engineFetch<Record<string, unknown>>(
      workspaceId,
      `/api/projects/${encodeURIComponent(projectId)}/spatial/entities/${encodeURIComponent(entityId)}/neighborhood?hop_count=${hopCount}`,
    ),
  spatialBlastRadius: (workspaceId: string, projectId: string, entityId: string) =>
    engineFetch<Record<string, unknown>>(
      workspaceId,
      `/api/projects/${encodeURIComponent(projectId)}/spatial/entities/${encodeURIComponent(entityId)}/blast-radius`,
    ),
  requestSpatialDirective: (
    workspaceId: string, projectId: string, directive: Record<string, unknown>,
  ) => engineFetch<Record<string, unknown>>(
    workspaceId, `/api/projects/${encodeURIComponent(projectId)}/spatial/directives`, {
      method: 'POST', body: JSON.stringify(directive),
    },
  ),
  semanticGraph: (workspaceId: string, projectId: string, revision?: number) =>
    engineFetch<Record<string, unknown>>(
      workspaceId,
      `/api/projects/${encodeURIComponent(projectId)}/semantic/graph${revision ? `?revision=${revision}` : ''}`,
    ),
  semanticNeighborhood: (
    workspaceId: string, projectId: string, request: Record<string, unknown>,
  ) => engineFetch<Record<string, unknown>>(
    workspaceId, `/api/projects/${encodeURIComponent(projectId)}/semantic/neighborhood`, {
      method: 'POST', body: JSON.stringify(request),
    },
  ),
  journalEntries: (workspaceId: string, projectId: string, limit = 200) =>
    engineFetch<Record<string, unknown>>(
      workspaceId, `/api/projects/${encodeURIComponent(projectId)}/journal?limit=${limit}`,
    ),
  verifyJournal: (workspaceId: string, projectId: string) =>
    engineFetch<Record<string, unknown>>(
      workspaceId, `/api/projects/${encodeURIComponent(projectId)}/journal/verify`,
    ),
  appendJournalEntry: (
    workspaceId: string, projectId: string, entry: Record<string, unknown>,
  ) => engineFetch<Record<string, unknown>>(
    workspaceId, `/api/projects/${encodeURIComponent(projectId)}/journal/entries`, {
      method: 'POST', body: JSON.stringify(entry),
    },
  ),
  acknowledgeSpatialDirective: (
    workspaceId: string, receiptId: string, acknowledgement: Record<string, unknown>,
  ) => engineFetch<Record<string, unknown>>(
    workspaceId, `/api/spatial/directives/${receiptId}/ack`, {
      method: 'POST', body: JSON.stringify(acknowledgement),
    },
  ),
  providerConnections: (workspaceId: string) => engineFetch<{ connections: Array<Record<string, unknown>> }>(
    workspaceId, `/api/workspaces/${encodeURIComponent(workspaceId)}/connections`,
  ),
  putProviderConnection: (workspaceId: string, body: Record<string, unknown>) => engineFetch<Record<string, unknown>>(
    workspaceId, `/api/workspaces/${encodeURIComponent(workspaceId)}/connections`, {
      method: 'POST', body: JSON.stringify(body),
    },
  ),
  protectedProviderConnection: (workspaceId: string, connectionId: string) => engineFetch<Record<string, unknown>>(
    workspaceId, `/api/workspaces/${encodeURIComponent(workspaceId)}/connections/${encodeURIComponent(connectionId)}/protected`,
  ),
  revokeProviderConnection: (workspaceId: string, connectionId: string) => engineFetch<Record<string, unknown>>(
    workspaceId, `/api/workspaces/${encodeURIComponent(workspaceId)}/connections/${encodeURIComponent(connectionId)}`, {
      method: 'DELETE',
    },
  ),
  generativeVideo: (workspaceId: string, projectId: string, request: Record<string, unknown>) =>
    engineFetch<Record<string, unknown>>(workspaceId, `/api/projects/${encodeURIComponent(projectId)}/generative/video`, {
      method: 'POST', body: JSON.stringify(request),
    }),
  generativeAudio: (workspaceId: string, projectId: string, request: Record<string, unknown>) =>
    engineFetch<Record<string, unknown>>(workspaceId, `/api/projects/${encodeURIComponent(projectId)}/generative/audio`, {
      method: 'POST', body: JSON.stringify(request),
    }),
  generativeReceipt: (workspaceId: string, projectId: string, receiptId: string) =>
    engineFetch<Record<string, unknown>>(workspaceId, `/api/projects/${encodeURIComponent(projectId)}/generative/receipts/${encodeURIComponent(receiptId)}`),
  repoToVideoEvidence: (workspaceId: string, projectId: string, request: DirectorInput) =>
    engineFetch<{ evidence: RepositoryEvidence; evidence_revision: string; redaction: { status: string; bounded: boolean }; factuality: { status: string } }>(workspaceId, `/api/projects/${encodeURIComponent(projectId)}/repo-to-video/evidence`, {
      method: 'POST', body: JSON.stringify(request),
    }),
  repoToVideoStoryboard: (workspaceId: string, projectId: string, request: DirectorInput) =>
    engineFetch<{ storyboard: Storyboard; receipt: EngineReceipt }>(workspaceId, `/api/projects/${encodeURIComponent(projectId)}/repo-to-video/storyboard`, {
      method: 'POST', body: JSON.stringify(request),
    }),
  repoToVideoCreativeBrief: (workspaceId: string, projectId: string, request: DirectorInput) =>
    engineFetch<{ brief: CreativeBrief; receipt: EngineReceipt }>(workspaceId, `/api/projects/${encodeURIComponent(projectId)}/repo-to-video/director/brief`, {
      method: 'POST', body: JSON.stringify(request),
    }),
  commitRepoToVideoStoryboard: (workspaceId: string, projectId: string, request: { receipt_id: string; expected_revision: number; confirmation_id: string }) =>
    engineFetch<{ receipt: EngineReceipt; idempotent?: boolean }>(workspaceId, `/api/projects/${encodeURIComponent(projectId)}/repo-to-video/storyboard/commit`, {
      method: 'POST', body: JSON.stringify(request), headers: { 'x-sag-human-confirmation': request.confirmation_id },
    }),
  generateRepoToVideo: (workspaceId: string, projectId: string, request: { storyboard: Storyboard; creative_brief: CreativeBrief; expected_revision: number; confirmation_id: string; aspect_ratio: '9:16' | '16:9' }) =>
    engineFetch<{ receipt: EngineReceipt; operations: GenerationOperation[] }>(workspaceId, `/api/projects/${encodeURIComponent(projectId)}/repo-to-video/generate`, {
      method: 'POST', body: JSON.stringify(request), headers: { 'x-sag-human-confirmation': request.confirmation_id },
    }),
  pollRepoToVideoGeneration: (workspaceId: string, projectId: string, receiptId: string) =>
    engineFetch<{ receipt: EngineReceipt; operations: GenerationOperation[] }>(workspaceId, `/api/projects/${encodeURIComponent(projectId)}/repo-to-video/generation/${encodeURIComponent(receiptId)}`),
  deliveryState: (workspaceId: string, projectId: string) => engineFetch<{
    delivery_profiles: Array<Record<string, unknown>>;
    release_approvals: Array<Record<string, unknown>>;
  }>(workspaceId, `/api/projects/${encodeURIComponent(projectId)}/delivery`),
  putDeliveryProfile: (workspaceId: string, projectId: string, profile: Record<string, unknown>) =>
    engineFetch<Record<string, unknown>>(workspaceId, `/api/projects/${encodeURIComponent(projectId)}/delivery/profiles`, {
      method: 'POST', body: JSON.stringify(profile),
    }),
  approveRelease: (
    workspaceId: string, projectId: string, body: Record<string, unknown>,
  ) => engineFetch<{
    approval: Record<string, unknown> & { id: string; bundle_hash: string; artifact_hashes: string[] };
    receipt: Record<string, unknown> & { id: string };
  }>(
    workspaceId, `/api/projects/${encodeURIComponent(projectId)}/release/approvals`, {
      method: 'POST', body: JSON.stringify(body),
    },
  ),
  dispatchRelease: (
    workspaceId: string, projectId: string, approvalId: string, requestId: string,
  ) => engineFetch<{
    approval: Record<string, unknown> & { id: string; artifact_hashes: string[] };
    attempts: Array<Record<string, unknown> & { id: string }>;
    receipt: Record<string, unknown> & { id: string };
  }>(workspaceId, `/api/projects/${encodeURIComponent(projectId)}/release/approvals/${encodeURIComponent(approvalId)}/dispatch`, {
    method: 'POST', body: JSON.stringify({ request_id: requestId }),
  }),
};
