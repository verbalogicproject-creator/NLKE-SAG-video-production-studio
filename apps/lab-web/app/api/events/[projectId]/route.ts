import { sseStream } from '@/lib/sse';

// GET /api/events/:projectId — SSE stream of job-state deltas for this project.
// Client consumes with `new EventSource(url)` and listens for `message` events.
//
// Sprint 1: emits a `hello` event immediately, then stub heartbeat every 15s
// until the pg-boss listener is wired.
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ projectId: string }> },
) {
  const { projectId } = await params;

  return sseStream((send, close) => {
    send({ event: 'hello', data: { projectId, serverTime: Date.now() } });

    // Heartbeat so the browser keeps the connection alive through proxies.
    const heartbeat = setInterval(() => {
      send({ event: 'heartbeat', data: { t: Date.now() } });
    }, 15_000);

    // Close in 10 min to avoid lingering streams during dev; prod will hold
    // longer because Cloud Run respects Connection: keep-alive.
    setTimeout(() => {
      clearInterval(heartbeat);
      send({ event: 'bye', data: { reason: 'timeout' } });
      close();
    }, 10 * 60_000);
  });
}
