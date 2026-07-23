import type {
  Project,
  Asset,
  RenderJob,
  PlatformVariant,
  PresignedUpload,
} from './types.js';

export interface LabClientOptions {
  /** e.g. https://lab.verbalogix.com */
  baseUrl?: string;
  /** Workspace API key (Settings → API Keys). */
  apiKey: string;
  /** Custom fetch — inject for tests or server-side contexts. */
  fetch?: typeof fetch;
}

export class LabClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly _fetch: typeof fetch;

  constructor(opts: LabClientOptions) {
    this.baseUrl = (opts.baseUrl ?? 'https://lab.verbalogix.com').replace(/\/$/, '');
    this.apiKey  = opts.apiKey;
    this._fetch  = opts.fetch ?? fetch;
  }

  // ── Projects ────────────────────────────────────────────────

  async listProjects(params?: { status?: string; limit?: number }): Promise<Project[]> {
    const qs = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : '';
    return this.req<Project[]>(`/api/projects${qs}`);
  }

  async createProject(input: { name: string; description?: string }): Promise<Project> {
    return this.req<Project>('/api/projects', { method: 'POST', body: input });
  }

  async getProject(id: string): Promise<Project & { assets: Asset[]; renders: RenderJob[] }> {
    return this.req(`/api/projects/${id}`);
  }

  // ── Assets ──────────────────────────────────────────────────

  async requestUploadUrl(input: {
    projectId: string;
    filename: string;
    contentType: string;
    sizeBytes: number;
  }): Promise<PresignedUpload> {
    const { projectId, ...body } = input;
    return this.req<PresignedUpload>(`/api/projects/${projectId}/assets/upload-url`, {
      method: 'POST',
      body,
    });
  }

  async markAssetIngested(input: { assetId: string; actualSizeBytes: number }): Promise<{ ok: true }> {
    return this.req(`/api/assets/ingest`, { method: 'POST', body: input });
  }

  // ── Pipeline ────────────────────────────────────────────────

  async startChamber(projectId: string, sourceAssetId: string, variants?: PlatformVariant[]): Promise<{ run: { id: string } }> {
    return this.req(`/api/projects/${projectId}/chamber`, {
      method: 'POST',
      body: { sourceAssetId, variants },
    });
  }

  // ── Events (SSE) ────────────────────────────────────────────

  /**
   * Subscribe to live job-state deltas for a project. Returns an object
   * with a `close()` method. Callback fires for each event.
   */
  subscribeToProject(projectId: string, onEvent: (evt: { event: string; data: unknown }) => void): { close: () => void } {
    const url = `${this.baseUrl}/api/events/${projectId}`;
    // EventSource doesn't support Authorization headers; include apiKey as
    // query param. The server validates either transport.
    const es = new EventSource(`${url}?apiKey=${encodeURIComponent(this.apiKey)}`);
    es.onmessage = (e) => onEvent({ event: 'message', data: safeParse(e.data) });
    es.addEventListener('hello',     (e) => onEvent({ event: 'hello',     data: safeParse((e as MessageEvent).data) }));
    es.addEventListener('heartbeat', (e) => onEvent({ event: 'heartbeat', data: safeParse((e as MessageEvent).data) }));
    es.addEventListener('bye',       (e) => onEvent({ event: 'bye',       data: safeParse((e as MessageEvent).data) }));
    es.addEventListener('error',     ()  => onEvent({ event: 'error',     data: null }));
    return { close: () => es.close() };
  }

  // ── internals ───────────────────────────────────────────────

  private async req<T = unknown>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
    const res = await this._fetch(`${this.baseUrl}${path}`, {
      method: init?.method ?? 'GET',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new LabClientError(res.status, res.statusText, text);
    }
    return res.json() as Promise<T>;
  }
}

export class LabClientError extends Error {
  constructor(public readonly status: number, statusText: string, public readonly body: string) {
    super(`${status} ${statusText}${body ? ` — ${body}` : ''}`);
    this.name = 'LabClientError';
  }
}

function safeParse(s: string): unknown {
  try { return JSON.parse(s); } catch { return s; }
}
