ALTER TABLE control."CanonicalJob"
  ADD COLUMN "inputVersion" TEXT NOT NULL DEFAULT 'sag-job-1',
  ADD COLUMN "inputSnapshot" JSONB NOT NULL DEFAULT '{}',
  ADD COLUMN "resultSnapshot" JSONB,
  ADD COLUMN progress DOUBLE PRECISION NOT NULL DEFAULT 0,
  ADD COLUMN stage TEXT,
  ADD COLUMN "statusMessage" TEXT,
  ADD COLUMN "cancellationRequested" BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN "heartbeatAt" TIMESTAMP(3),
  ADD COLUMN "maxAttempts" INTEGER NOT NULL DEFAULT 3;
