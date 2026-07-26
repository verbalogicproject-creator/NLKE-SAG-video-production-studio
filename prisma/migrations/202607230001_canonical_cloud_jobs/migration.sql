CREATE SCHEMA IF NOT EXISTS control;
CREATE SCHEMA IF NOT EXISTS queue;

CREATE TYPE control."Role" AS ENUM ('OWNER','ADMIN','EDITOR','VIEWER');
CREATE TYPE control."ProjectStatus" AS ENUM ('DRAFT','INGESTING','READY','ARCHIVED');
CREATE TYPE control."AssetKind" AS ENUM ('RAW','ANALYSIS','SCRATCH','DELIVERABLE');
CREATE TYPE control."StorageProvider" AS ENUM ('LOCAL','GCS');
CREATE TYPE control."UploadStatus" AS ENUM ('ISSUED','UPLOADED','VERIFYING','PROMOTED','REJECTED','EXPIRED');
CREATE TYPE control."PlatformVariant" AS ENUM ('YT_SHORTS_9_16','TIKTOK_9_16','IG_REELS_9_16');
CREATE TYPE control."ChamberRunStatus" AS ENUM ('INGESTING','ANALYZING','DRAFTS_READY','IN_REVIEW','RENDERING','VERIFYING','READY_TO_PUBLISH','FAILED','CANCELLED','HALTED_BRAND_VIOLATION');
CREATE TYPE control."ChamberVariantStatus" AS ENUM ('PENDING','DRAFT_READY','HALTED_BRAND_VIOLATION','ACCEPTED','RENDERING','VERIFYING','READY_TO_PUBLISH','FAILED','CANCELLED');
CREATE TYPE control."CanonicalJobKind" AS ENUM ('INTAKE','ANALYSIS','RENDER','OBSERVE','PUBLISH_YOUTUBE');
CREATE TYPE control."CanonicalJobState" AS ENUM ('QUEUED','DISPATCH_PENDING','CLAIMED','RUNNING','AWAITING_OBSERVATION','SUCCEEDED','FAILED','CANCELLED','INTERRUPTED');
CREATE TYPE control."InvitationStatus" AS ENUM ('PENDING','ACCEPTED','REVOKED','EXPIRED');
CREATE TYPE control."ApiKeyStatus" AS ENUM ('ACTIVE','REVOKED');
CREATE TYPE control."QuotaKind" AS ENUM ('UPLOAD_BYTES','STORAGE_BYTES','ANALYSIS_CONCURRENCY','RENDER_CONCURRENCY','RENDER_DAILY');
CREATE TYPE queue."OutboxState" AS ENUM ('PENDING','DISPATCHED','FAILED');
CREATE TYPE control."ApprovalState" AS ENUM ('ACTIVE','CONSUMED','REVOKED','EXPIRED');
CREATE TYPE control."PublicationState" AS ENUM ('PENDING','UPLOADING','PUBLISHED','FAILED','AMBIGUOUS');

CREATE TABLE control."User" (
  id TEXT PRIMARY KEY,email TEXT NOT NULL,name TEXT,image TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL
);
CREATE UNIQUE INDEX "User_email_key" ON control."User"(email);
CREATE INDEX "User_email_idx" ON control."User"(email);

CREATE TABLE control."Account" (
  id TEXT PRIMARY KEY,"userId" TEXT NOT NULL,type TEXT NOT NULL,provider TEXT NOT NULL,
  "providerAccountId" TEXT NOT NULL,refresh_token TEXT,access_token TEXT,expires_at INTEGER,
  token_type TEXT,scope TEXT,id_token TEXT,session_state TEXT,
  CONSTRAINT "Account_userId_fkey" FOREIGN KEY ("userId") REFERENCES control."User"(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX "Account_provider_providerAccountId_key" ON control."Account"(provider,"providerAccountId");

CREATE TABLE control."Session" (
  id TEXT PRIMARY KEY,"sessionToken" TEXT NOT NULL,"userId" TEXT NOT NULL,expires TIMESTAMP(3) NOT NULL,
  CONSTRAINT "Session_userId_fkey" FOREIGN KEY ("userId") REFERENCES control."User"(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX "Session_sessionToken_key" ON control."Session"("sessionToken");

CREATE TABLE control."VerificationToken" (identifier TEXT NOT NULL,token TEXT NOT NULL,expires TIMESTAMP(3) NOT NULL);
CREATE UNIQUE INDEX "VerificationToken_token_key" ON control."VerificationToken"(token);
CREATE UNIQUE INDEX "VerificationToken_identifier_token_key" ON control."VerificationToken"(identifier,token);

CREATE TABLE control."Workspace" (
  id TEXT PRIMARY KEY,name TEXT NOT NULL,slug TEXT NOT NULL,
  "uploadLimitBytes" BIGINT NOT NULL DEFAULT 536870912,
  "storageLimitBytes" BIGINT NOT NULL DEFAULT 5368709120,
  "analysisConcurrencyLimit" INTEGER NOT NULL DEFAULT 1,
  "renderConcurrencyLimit" INTEGER NOT NULL DEFAULT 1,
  "dailyRenderLimit" INTEGER NOT NULL DEFAULT 20,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,"updatedAt" TIMESTAMP(3) NOT NULL
);
CREATE UNIQUE INDEX "Workspace_slug_key" ON control."Workspace"(slug);
CREATE INDEX "Workspace_slug_idx" ON control."Workspace"(slug);

CREATE TABLE control."WorkspaceMember" (
  "userId" TEXT NOT NULL,"workspaceId" TEXT NOT NULL,role control."Role" NOT NULL DEFAULT 'EDITOR',
  "joinedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY("userId","workspaceId"),
  CONSTRAINT "WorkspaceMember_userId_fkey" FOREIGN KEY ("userId") REFERENCES control."User"(id) ON DELETE CASCADE,
  CONSTRAINT "WorkspaceMember_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE
);
CREATE INDEX "WorkspaceMember_workspaceId_idx" ON control."WorkspaceMember"("workspaceId");

CREATE TABLE control."Invitation" (
  id TEXT PRIMARY KEY,"workspaceId" TEXT NOT NULL,email TEXT NOT NULL,role control."Role" NOT NULL DEFAULT 'EDITOR',
  status control."InvitationStatus" NOT NULL DEFAULT 'PENDING',"expiresAt" TIMESTAMP(3) NOT NULL,
  "acceptedAt" TIMESTAMP(3),"createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Invitation_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX "Invitation_workspaceId_email_key" ON control."Invitation"("workspaceId",email);
CREATE INDEX "Invitation_email_status_expiresAt_idx" ON control."Invitation"(email,status,"expiresAt");

CREATE TABLE control."ApiKey" (
  id TEXT PRIMARY KEY,"workspaceId" TEXT NOT NULL,"createdById" TEXT NOT NULL,name TEXT NOT NULL,prefix TEXT NOT NULL,
  "keyHash" TEXT NOT NULL,scopes TEXT[] NOT NULL,status control."ApiKeyStatus" NOT NULL DEFAULT 'ACTIVE',
  "expiresAt" TIMESTAMP(3),"lastUsedAt" TIMESTAMP(3),"createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "ApiKey_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE,
  CONSTRAINT "ApiKey_createdById_fkey" FOREIGN KEY ("createdById") REFERENCES control."User"(id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX "ApiKey_keyHash_key" ON control."ApiKey"("keyHash");
CREATE INDEX "ApiKey_workspaceId_status_idx" ON control."ApiKey"("workspaceId",status);

CREATE TABLE control."Project" (
  id TEXT PRIMARY KEY,"workspaceId" TEXT NOT NULL,name TEXT NOT NULL,status control."ProjectStatus" NOT NULL DEFAULT 'DRAFT',
  description TEXT,"engineProjectId" TEXT,"engineRevision" INTEGER,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,"updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "Project_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX "Project_engineProjectId_key" ON control."Project"("engineProjectId");
CREATE INDEX "Project_workspaceId_createdAt_idx" ON control."Project"("workspaceId","createdAt");

CREATE TABLE control."StorageObject" (
  id TEXT PRIMARY KEY,provider control."StorageProvider" NOT NULL,bucket TEXT,"objectKey" TEXT NOT NULL,
  generation TEXT,sha256 TEXT,"byteSize" BIGINT,"createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX "StorageObject_provider_bucket_objectKey_generation_key" ON control."StorageObject"(provider,bucket,"objectKey",generation);

CREATE TABLE control."Asset" (
  id TEXT PRIMARY KEY,"projectId" TEXT NOT NULL,"storageObjectId" TEXT,kind control."AssetKind" NOT NULL,
  "managedUri" TEXT NOT NULL,"mimeType" TEXT,"sizeBytes" BIGINT NOT NULL,"durationMs" INTEGER,
  metadata JSONB,"engineAssetId" TEXT,sha256 TEXT,"verifiedAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Asset_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES control."Project"(id) ON DELETE CASCADE,
  CONSTRAINT "Asset_storageObjectId_fkey" FOREIGN KEY ("storageObjectId") REFERENCES control."StorageObject"(id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX "Asset_storageObjectId_key" ON control."Asset"("storageObjectId");
CREATE UNIQUE INDEX "Asset_managedUri_key" ON control."Asset"("managedUri");
CREATE UNIQUE INDEX "Asset_engineAssetId_key" ON control."Asset"("engineAssetId");
CREATE INDEX "Asset_projectId_kind_idx" ON control."Asset"("projectId",kind);

CREATE TABLE control."UploadSession" (
  id TEXT PRIMARY KEY,"workspaceId" TEXT NOT NULL,"projectId" TEXT NOT NULL,"assetId" TEXT NOT NULL,
  status control."UploadStatus" NOT NULL DEFAULT 'ISSUED',"objectKey" TEXT NOT NULL,"originalFilename" TEXT NOT NULL,
  "expectedSizeBytes" BIGINT NOT NULL,"expectedMimeType" TEXT NOT NULL,"objectGeneration" TEXT,
  "checksumSha256" TEXT,"expiresAt" TIMESTAMP(3) NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,"updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "UploadSession_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE,
  CONSTRAINT "UploadSession_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES control."Project"(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX "UploadSession_assetId_key" ON control."UploadSession"("assetId");
CREATE INDEX "UploadSession_workspaceId_status_expiresAt_idx" ON control."UploadSession"("workspaceId",status,"expiresAt");

CREATE TABLE control."BrandSkill" (
  "workspaceId" TEXT PRIMARY KEY,markdown TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,
  "updatedAt" TIMESTAMP(3) NOT NULL,"updatedById" TEXT,
  CONSTRAINT "BrandSkill_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE
);

CREATE TABLE control."ChamberRun" (
  id TEXT PRIMARY KEY,"projectId" TEXT NOT NULL,"engineProjectId" TEXT NOT NULL,"sourceEngineAssetId" TEXT NOT NULL,
  "sourceRevision" INTEGER NOT NULL,"sourceSha256" TEXT NOT NULL,"requestedVariants" control."PlatformVariant"[] NOT NULL,
  language TEXT NOT NULL DEFAULT 'auto',prompt TEXT,"brandSkillVersion" INTEGER NOT NULL,"brandContractHash" TEXT NOT NULL,
  "brandContractSnapshot" JSONB NOT NULL,"analysisJobId" TEXT,status control."ChamberRunStatus" NOT NULL DEFAULT 'INGESTING',
  "errorCode" TEXT,"errorDetail" TEXT,"createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,"updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "ChamberRun_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES control."Project"(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX "ChamberRun_analysisJobId_key" ON control."ChamberRun"("analysisJobId");
CREATE INDEX "ChamberRun_projectId_createdAt_idx" ON control."ChamberRun"("projectId","createdAt");
CREATE INDEX "ChamberRun_status_updatedAt_idx" ON control."ChamberRun"(status,"updatedAt");

CREATE TABLE control."ChamberVariant" (
  id TEXT PRIMARY KEY,"chamberRunId" TEXT NOT NULL,variant control."PlatformVariant" NOT NULL,
  "suggestionId" TEXT,"engineProjectId" TEXT,"engineRevision" INTEGER,"renderJobId" TEXT,"receiptId" TEXT,
  "deliverableAssetId" TEXT,status control."ChamberVariantStatus" NOT NULL DEFAULT 'PENDING',"warningDetails" JSONB,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,"updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "ChamberVariant_chamberRunId_fkey" FOREIGN KEY ("chamberRunId") REFERENCES control."ChamberRun"(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX "ChamberVariant_suggestionId_key" ON control."ChamberVariant"("suggestionId");
CREATE UNIQUE INDEX "ChamberVariant_renderJobId_key" ON control."ChamberVariant"("renderJobId");
CREATE UNIQUE INDEX "ChamberVariant_receiptId_key" ON control."ChamberVariant"("receiptId");
CREATE UNIQUE INDEX "ChamberVariant_chamberRunId_variant_key" ON control."ChamberVariant"("chamberRunId",variant);
CREATE INDEX "ChamberVariant_chamberRunId_status_idx" ON control."ChamberVariant"("chamberRunId",status);

CREATE TABLE control."CanonicalJob" (
  id TEXT PRIMARY KEY,"workspaceId" TEXT NOT NULL,"projectId" TEXT,kind control."CanonicalJobKind" NOT NULL,
  state control."CanonicalJobState" NOT NULL DEFAULT 'QUEUED',"requestId" TEXT NOT NULL,"canonicalEntityId" TEXT NOT NULL,
  attempt INTEGER NOT NULL DEFAULT 0,"claimedBy" TEXT,"claimedAt" TIMESTAMP(3),"leaseExpiresAt" TIMESTAMP(3),
  "errorCode" TEXT,"errorDetail" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,"updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "CanonicalJob_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE,
  CONSTRAINT "CanonicalJob_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES control."Project"(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX "CanonicalJob_workspaceId_requestId_key" ON control."CanonicalJob"("workspaceId","requestId");
CREATE INDEX "CanonicalJob_state_createdAt_idx" ON control."CanonicalJob"(state,"createdAt");
CREATE INDEX "CanonicalJob_workspaceId_kind_state_idx" ON control."CanonicalJob"("workspaceId",kind,state);

CREATE TABLE queue."OutboxEvent" (
  id TEXT PRIMARY KEY,"jobId" TEXT NOT NULL,state queue."OutboxState" NOT NULL DEFAULT 'PENDING',attempt INTEGER NOT NULL DEFAULT 0,
  "availableAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,"dispatchedAt" TIMESTAMP(3),"lastError" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "OutboxEvent_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES control."CanonicalJob"(id) ON DELETE CASCADE
);
CREATE INDEX "OutboxEvent_state_availableAt_idx" ON queue."OutboxEvent"(state,"availableAt");

CREATE TABLE control."QuotaLedger" (
  id TEXT PRIMARY KEY,"workspaceId" TEXT NOT NULL,kind control."QuotaKind" NOT NULL,amount BIGINT NOT NULL,
  "requestId" TEXT NOT NULL,"occurredAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,metadata JSONB,
  CONSTRAINT "QuotaLedger_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX "QuotaLedger_workspaceId_kind_requestId_key" ON control."QuotaLedger"("workspaceId",kind,"requestId");
CREATE INDEX "QuotaLedger_workspaceId_kind_occurredAt_idx" ON control."QuotaLedger"("workspaceId",kind,"occurredAt");

CREATE TABLE control."ArtifactObservation" (
  id TEXT PRIMARY KEY,"jobId" TEXT NOT NULL,"artifactSha256" TEXT NOT NULL,passed BOOLEAN NOT NULL,evidence JSONB NOT NULL,
  "observedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "ArtifactObservation_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES control."CanonicalJob"(id) ON DELETE CASCADE
);
CREATE INDEX "ArtifactObservation_jobId_observedAt_idx" ON control."ArtifactObservation"("jobId","observedAt");

CREATE TABLE control."YouTubeConnection" (
  id TEXT PRIMARY KEY,"workspaceId" TEXT NOT NULL,"channelId" TEXT NOT NULL,"channelTitle" TEXT,
  "encryptedAccessToken" TEXT NOT NULL,"encryptedRefreshToken" TEXT,"expiresAt" TIMESTAMP(3),scopes TEXT[] NOT NULL,
  "kmsKeyVersion" TEXT NOT NULL,"createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,"updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "YouTubeConnection_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX "YouTubeConnection_workspaceId_key" ON control."YouTubeConnection"("workspaceId");

CREATE TABLE control."PublicationApproval" (
  id TEXT PRIMARY KEY,"workspaceId" TEXT NOT NULL,"artifactAssetId" TEXT NOT NULL,"artifactSha256" TEXT NOT NULL,
  "channelId" TEXT NOT NULL,visibility TEXT NOT NULL DEFAULT 'private',state control."ApprovalState" NOT NULL DEFAULT 'ACTIVE',
  "approvedById" TEXT NOT NULL,"expiresAt" TIMESTAMP(3) NOT NULL,"consumedAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "PublicationApproval_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE,
  CONSTRAINT "PublicationApproval_artifactAssetId_fkey" FOREIGN KEY ("artifactAssetId") REFERENCES control."Asset"(id) ON DELETE RESTRICT,
  CONSTRAINT "PublicationApproval_approvedById_fkey" FOREIGN KEY ("approvedById") REFERENCES control."User"(id) ON DELETE RESTRICT
);
CREATE INDEX "PublicationApproval_workspaceId_state_expiresAt_idx" ON control."PublicationApproval"("workspaceId",state,"expiresAt");

CREATE TABLE control."PublicationAttempt" (
  id TEXT PRIMARY KEY,"workspaceId" TEXT NOT NULL,"approvalId" TEXT NOT NULL,"idempotencyKey" TEXT NOT NULL,
  state control."PublicationState" NOT NULL DEFAULT 'PENDING',"resumableSession" TEXT,"youtubeVideoId" TEXT,
  "boundedError" TEXT,attempt INTEGER NOT NULL DEFAULT 0,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,"updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "PublicationAttempt_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE,
  CONSTRAINT "PublicationAttempt_approvalId_fkey" FOREIGN KEY ("approvalId") REFERENCES control."PublicationApproval"(id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX "PublicationAttempt_idempotencyKey_key" ON control."PublicationAttempt"("idempotencyKey");
CREATE UNIQUE INDEX "PublicationAttempt_approvalId_idempotencyKey_key" ON control."PublicationAttempt"("approvalId","idempotencyKey");
CREATE INDEX "PublicationAttempt_workspaceId_state_updatedAt_idx" ON control."PublicationAttempt"("workspaceId",state,"updatedAt");

CREATE TABLE control."AuditEvent" (
  id TEXT PRIMARY KEY,"workspaceId" TEXT NOT NULL,"actorId" TEXT,action TEXT NOT NULL,"targetType" TEXT NOT NULL,
  "targetId" TEXT NOT NULL,"requestId" TEXT NOT NULL,evidence JSONB,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "AuditEvent_workspaceId_fkey" FOREIGN KEY ("workspaceId") REFERENCES control."Workspace"(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX "AuditEvent_workspaceId_requestId_action_key" ON control."AuditEvent"("workspaceId","requestId",action);
CREATE INDEX "AuditEvent_workspaceId_createdAt_idx" ON control."AuditEvent"("workspaceId","createdAt");
