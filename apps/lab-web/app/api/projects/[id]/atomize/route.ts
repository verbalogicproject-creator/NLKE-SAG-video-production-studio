import { NextResponse } from 'next/server';

// POST /api/projects/:id/atomize — enqueue the atomizer job
export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  return NextResponse.json(
    {
      error: 'NotImplemented',
      message:
        `Enqueues job.atomize for project ${id}. Atomizer reads the RAW asset transcript + workspace brand skill, emits an EDL per requested variant, then enqueues job.render for each.`,
    },
    { status: 501 },
  );
}
