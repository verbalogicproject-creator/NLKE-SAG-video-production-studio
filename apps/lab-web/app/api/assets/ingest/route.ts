import { NextResponse } from 'next/server';

// Client calls this after a successful R2 presigned PUT.
// Body: { assetId, actualSizeBytes, checksum? }
// Side-effect: creates Asset row, enqueues job.transcribe.
export async function POST() {
  return NextResponse.json(
    {
      error: 'NotImplemented',
      message:
        'Upload-complete webhook. Verifies the R2 object exists, writes Asset row, enqueues job.transcribe.',
    },
    { status: 501 },
  );
}
