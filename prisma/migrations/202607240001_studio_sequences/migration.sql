CREATE TABLE control."StudioSequence" (
  id TEXT PRIMARY KEY,
  "projectId" TEXT NOT NULL,
  "engineProjectId" TEXT NOT NULL,
  name TEXT NOT NULL,
  "currentRevision" INTEGER NOT NULL DEFAULT 1,
  "durationLimitTicks" INTEGER NOT NULL DEFAULT 21600000,
  "legacyVariant" BOOLEAN NOT NULL DEFAULT false,
  "archivedAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "StudioSequence_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES control."Project"(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX "StudioSequence_engineProjectId_key" ON control."StudioSequence"("engineProjectId");
CREATE INDEX "StudioSequence_projectId_createdAt_idx" ON control."StudioSequence"("projectId","createdAt");

CREATE TABLE control."DeliveryProfile" (
  id TEXT PRIMARY KEY,
  "sequenceId" TEXT NOT NULL,
  destination TEXT NOT NULL,
  "aspectRatio" TEXT NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  "captionPlacement" TEXT NOT NULL DEFAULT 'safe_bottom',
  "safeZoneX" INTEGER NOT NULL DEFAULT 48,
  "safeZoneY" INTEGER NOT NULL DEFAULT 96,
  metadata JSONB NOT NULL DEFAULT '{}',
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "DeliveryProfile_sequenceId_fkey" FOREIGN KEY ("sequenceId") REFERENCES control."StudioSequence"(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX "DeliveryProfile_sequenceId_destination_key" ON control."DeliveryProfile"("sequenceId",destination);

CREATE TABLE control."ReleaseBundleApproval" (
  id TEXT PRIMARY KEY,
  "workspaceId" TEXT NOT NULL,
  "sequenceId" TEXT NOT NULL,
  "sequenceRevision" INTEGER NOT NULL,
  "bundleHash" TEXT NOT NULL,
  "artifactHashes" TEXT[] NOT NULL,
  destinations JSONB NOT NULL,
  state control."ApprovalState" NOT NULL DEFAULT 'ACTIVE',
  "approvedById" TEXT NOT NULL,
  "expiresAt" TIMESTAMP(3) NOT NULL,
  "consumedAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "ReleaseBundleApproval_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE,
  CONSTRAINT "ReleaseBundleApproval_sequenceId_fkey" FOREIGN KEY ("sequenceId") REFERENCES control."StudioSequence"(id) ON DELETE RESTRICT,
  CONSTRAINT "ReleaseBundleApproval_approvedById_fkey" FOREIGN KEY ("approvedById") REFERENCES control."User"(id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX "ReleaseBundleApproval_workspaceId_bundleHash_key" ON control."ReleaseBundleApproval"("workspaceId","bundleHash");
CREATE INDEX "ReleaseBundleApproval_workspaceId_state_expiresAt_idx" ON control."ReleaseBundleApproval"("workspaceId",state,"expiresAt");

CREATE TABLE control."ReleasePublicationAttempt" (
  id TEXT PRIMARY KEY,
  "workspaceId" TEXT NOT NULL,
  "approvalId" TEXT NOT NULL,
  destination TEXT NOT NULL,
  "idempotencyKey" TEXT NOT NULL,
  state control."PublicationState" NOT NULL DEFAULT 'PENDING',
  "externalId" TEXT,
  "boundedError" TEXT,
  attempt INTEGER NOT NULL DEFAULT 0,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "ReleasePublicationAttempt_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE,
  CONSTRAINT "ReleasePublicationAttempt_approvalId_fkey" FOREIGN KEY ("approvalId") REFERENCES control."ReleaseBundleApproval"(id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX "ReleasePublicationAttempt_idempotencyKey_key" ON control."ReleasePublicationAttempt"("idempotencyKey");
CREATE UNIQUE INDEX "ReleasePublicationAttempt_approvalId_destination_key" ON control."ReleasePublicationAttempt"("approvalId",destination);
CREATE INDEX "ReleasePublicationAttempt_workspaceId_state_updatedAt_idx" ON control."ReleasePublicationAttempt"("workspaceId",state,"updatedAt");

INSERT INTO control."StudioSequence" (
  id,"projectId","engineProjectId",name,"currentRevision","legacyVariant","createdAt","updatedAt"
)
SELECT 'sequence_' || md5(id),id,"engineProjectId",name,COALESCE("engineRevision",1),false,"createdAt","updatedAt"
FROM control."Project" WHERE "engineProjectId" IS NOT NULL
ON CONFLICT ("engineProjectId") DO NOTHING;

INSERT INTO control."DeliveryProfile" (
  id,"sequenceId",destination,"aspectRatio",width,height,"captionPlacement","safeZoneX","safeZoneY",metadata,"createdAt","updatedAt"
)
SELECT 'delivery_' || md5(s.id || d.destination),s.id,d.destination,'9:16',1080,1920,'safe_bottom',48,96,'{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP
FROM control."StudioSequence" s
CROSS JOIN (VALUES ('youtube_shorts'),('tiktok'),('instagram_reels')) AS d(destination)
ON CONFLICT ("sequenceId",destination) DO NOTHING;
