import type { EngineJob, EngineSuggestion } from '@verbalogix/media-contracts';

const base = () => (process.env.SAG_ENGINE_URL ?? 'http://127.0.0.1:8080').replace(/\/$/, '');

export async function engineRequest<T>(workspaceId: string, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${base()}${path}`, {
    ...init,
    headers: {
      'content-type': 'application/json',
      'x-sag-service-token': process.env.SAG_VIDEO_SERVICE_TOKEN ?? 'local-chamber-service',
      'x-sag-workspace-id': workspaceId,
      ...init.headers,
    },
  });
  const body = await response.json().catch(() => ({ detail: response.statusText }));
  if (!response.ok) throw new Error(String(body.detail ?? `SAG engine returned ${response.status}`));
  return body as T;
}

export const engineJob = (workspaceId: string, jobId: string) =>
  engineRequest<EngineJob>(workspaceId, `/api/jobs/${jobId}`);

export const engineSuggestions = (workspaceId: string, projectId: string, jobId: string) =>
  engineRequest<{ suggestions: EngineSuggestion[] }>(workspaceId, `/api/projects/${projectId}/suggestions?job_id=${encodeURIComponent(jobId)}`);
