/**
 * Server-Sent Events helpers.
 *
 * Why SSE over WebSockets: one-way (server → client) is enough for render
 * status. SSE passes cleanly through HTTP proxies and Cloud Run. Auto-reconnect
 * is built into the browser's EventSource.
 */

export type SseEvent = {
  /** Event id for auto-reconnect Last-Event-ID support */
  id?: string;
  /** Default 'message' if omitted */
  event?: string;
  data: unknown;
};

/** Encode one event as a raw SSE frame. */
export function encodeSse(evt: SseEvent): string {
  const lines: string[] = [];
  if (evt.id)    lines.push(`id: ${evt.id}`);
  if (evt.event) lines.push(`event: ${evt.event}`);
  const payload =
    typeof evt.data === 'string' ? evt.data : JSON.stringify(evt.data);
  for (const line of payload.split('\n')) lines.push(`data: ${line}`);
  lines.push('', '');
  return lines.join('\n');
}

/** Build a Response stream that clients subscribe to via EventSource. */
export function sseStream(
  setup: (send: (evt: SseEvent) => void, close: () => void) => void | Promise<void>,
): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      const send = (evt: SseEvent) =>
        controller.enqueue(encoder.encode(encodeSse(evt)));
      const close = () => controller.close();
      Promise.resolve(setup(send, close)).catch((err) => {
        send({ event: 'error', data: { message: String(err) } });
        close();
      });
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type':      'text/event-stream; charset=utf-8',
      'Cache-Control':     'no-cache, no-transform',
      'Connection':        'keep-alive',
      'X-Accel-Buffering': 'no', // nginx/GCP Cloud Run friendly
    },
  });
}
