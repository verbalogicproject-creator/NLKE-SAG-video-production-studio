// Shared DTOs — mirror the Prisma models. Kept hand-written so the SDK stays
// decoupled from Prisma's generated types (which would drag @prisma/client
// into every consumer).

export type Plan = 'FREE' | 'STARTER' | 'STUDIO' | 'AGENCY';
export type Role = 'OWNER' | 'ADMIN' | 'EDITOR' | 'VIEWER';

export type ProjectStatus = 'DRAFT' | 'INGESTING' | 'READY' | 'ARCHIVED';

export type AssetKind =
  | 'RAW'
  | 'TRANSCRIPT'
  | 'SCENE_DATA'
  | 'EDIT_DECISION'
  | 'SCRATCH'
  | 'DELIVERABLE';

export type PlatformVariant =
  | 'LINKEDIN_16_9'
  | 'YT_LONG_16_9'
  | 'YT_SHORTS_9_16'
  | 'TIKTOK_9_16'
  | 'IG_REELS_9_16'
  | 'FB_FEED_16_9';

export type JobStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'HALTED_BRAND_VIOLATION'
  | 'CANCELLED';

export type Platform = 'YOUTUBE' | 'LINKEDIN' | 'TIKTOK' | 'INSTAGRAM' | 'FACEBOOK';
export type PublishStatus = 'PENDING' | 'PUBLISHED' | 'FAILED';

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
  r2Bucket: string;
  r2Key: string;
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
  assetId: string;
  url: string;
  expiresAt: string;
}
