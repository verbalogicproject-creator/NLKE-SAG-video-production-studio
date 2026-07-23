import type {
  BrandContract,
  ChamberStartRequest,
  EngineJob,
  EngineSuggestion,
} from '@verbalogix/media-contracts';
import { GoogleAuth } from 'google-auth-library';

const baseUrl = () => (process.env.SAG_ENGINE_URL ?? 'http://127.0.0.1:8080').replace(/\/$/, '');

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
  command: (workspaceId: string, projectId: string, command: string, arguments_: Record<string, unknown>, expectedRevision: number, requestId: string) =>
    engineFetch<Record<string, unknown>>(workspaceId, `/api/projects/${projectId}/commands`, {
      method: 'POST',
      body: JSON.stringify({ command, arguments: arguments_, expected_revision: expectedRevision, request_id: requestId, actor: 'verbalogix-web' }),
    }),
};
