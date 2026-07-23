// Shared DTOs — mirror the Prisma models. Kept hand-written so the SDK stays
// decoupled from Prisma's generated types (which would drag @prisma/client
// into every consumer).

export type Role = 'OWNER' | 'ADMIN' | 'EDITOR' | 'VIEWER';

export type ProjectStatus = 'DRAFT' | 'INGESTING' | 'READY' | 'ARCHIVED';

export type AssetKind =
  | 'RAW'
  | 'ANALYSIS'
  | 'SCRATCH'
  | 'DELIVERABLE';

export type PlatformVariant =
  | 'YT_SHORTS_9_16'
  | 'TIKTOK_9_16'
  | 'IG_REELS_9_16';

export type JobStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'HALTED_BRAND_VIOLATION'
  | 'CANCELLED';

export type Platform = 'YOUTUBE';
export type PublishStatus = 'PENDING' | 'UPLOADING' | 'PUBLISHED' | 'FAILED' | 'AMBIGUOUS';

export interface Project {
  id: string;
  workspaceId: string;
  name: string;
  status: ProjectStatus;
  description?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface Asset {
  id: string;
  projectId: string;
  kind: AssetKind;
  managedUri: string;
  generation?: string | null;
  mimeType?: string | null;
  sizeBytes: number;
  durationMs?: number | null;
  metadata?: unknown;
  createdAt: string;
}

export interface RenderJob {
  id: string;
  projectId: string;
  variant: PlatformVariant;
  status: JobStatus;
  progress: number;
  outputAssetId?: string | null;
  error?: string | null;
  queuedAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
}

export interface PresignedUpload {
  uploadSessionId: string;
  sessionUri: string;
  expiresAt: string;
}
