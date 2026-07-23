'use client';

import { useEffect, useMemo, useState } from 'react';

type Asset = { id: string; engineAssetId: string | null; sha256: string | null; sizeBytes: string; mimeType: string | null };
type Variant = { variant: string; status: string; suggestionId: string | null; engineProjectId: string | null; engineRevision: number | null; warningDetails: Record<string, unknown> | null };
type Run = { id: string; status: string; variants: Variant[]; errorDetail?: string | null };
type Props = { project: { id: string; name: string; assets: Asset[]; chamberRuns: Run[] } };

const TERMINAL = new Set(['READY_TO_PUBLISH', 'FAILED', 'CANCELLED', 'HALTED_BRAND_VIOLATION']);

export function ChamberProject({ project }: Props) {
  const [runs, setRuns] = useState(project.chamberRuns);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const current = runs[0];
  const source = project.assets.find((asset) => asset.engineAssetId && asset.sha256);

  async function invoke(path: string, init: RequestInit = {}) {
    setBusy(path); setMessage('');
    const response = await fetch(path, init);
    const body = await response.json();
    setBusy('');
    if (!response.ok) { setMessage(body.message ?? body.error); throw new Error(body.message ?? body.error); }
    return body;
  }

  async function upload(form: FormData) {
    await invoke(`/api/projects/${project.id}/assets/upload`, { method: 'POST', body: form });
    window.location.reload();
  }

  async function start() {
    if (!source) return;
    const body = await invoke(`/api/projects/${project.id}/chamber`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ sourceAssetId: source.id, variants: ['YT_SHORTS_9_16', 'TIKTOK_9_16', 'IG_REELS_9_16'], language: 'auto' }),
    });
    setRuns([body.run, ...runs]);
  }

  useEffect(() => {
    if (!current || TERMINAL.has(current.status)) return;
    const timer = setInterval(async () => {
      const response = await fetch(`/api/chamber/${current.id}`, { cache: 'no-store' });
      if (response.ok) {
        const body = await response.json();
        setRuns((value) => [body.run, ...value.slice(1)]);
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [current?.id, current?.status]);

  return <div className="p-4 space-y-4">
    <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border-base pb-3">
      <div><div className="data text-[10px] text-amber">PROJECT</div><h1 className="font-display text-2xl text-ink-0">{project.name}</h1></div>
      {!source ? <form action={upload} className="flex gap-2"><input name="file" type="file" accept="video/*" required className="data text-xs text-ink-2" /><button className="bg-amber text-bg-0 px-3 py-2 data text-[11px]">UPLOAD SOURCE</button></form> :
        <button disabled={Boolean(busy)} onClick={start} className="bg-amber text-bg-0 px-3 py-2 data text-[11px] disabled:opacity-50">PUT IN CHAMBER</button>}
    </div>
    {message ? <div className="border border-red-500/50 bg-red-950/30 p-3 text-red-300 data text-xs">{message}</div> : null}
    {source ? <div className="border border-border-base p-3 data text-xs text-ink-2">SOURCE / {source.mimeType} / {source.sizeBytes} BYTES / SHA {source.sha256?.slice(0, 12)}</div> : null}
    {current ? <RunView run={current} invoke={invoke} busy={busy} /> : <div className="border border-dashed border-border-base p-10 text-center text-ink-2">Upload a source video to begin.</div>}
  </div>;
}

function RunView({ run, invoke, busy }: { run: Run; invoke: (path: string, init?: RequestInit) => Promise<any>; busy: string }) {
  const ready = useMemo(() => run.variants.filter((variant) => variant.status === 'READY_TO_PUBLISH').length, [run]);
  return <section className="space-y-3">
    <div className="flex justify-between data text-xs"><span>RUN {run.id}</span><span className="text-amber">{run.status} / {ready}/3 READY</span></div>
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-2">
      {run.variants.map((variant) => <VariantCard key={variant.variant} run={run} variant={variant} invoke={invoke} busy={busy} />)}
    </div>
    {!TERMINAL.has(run.status) ? <button onClick={() => invoke(`/api/chamber/${run.id}/cancel`, { method: 'POST' })} className="border border-border-base px-3 py-2 data text-[10px] text-ink-2">CANCEL RUN</button> : null}
  </section>;
}

function VariantCard({ run, variant, invoke, busy }: { run: Run; variant: Variant; invoke: (path: string, init?: RequestInit) => Promise<any>; busy: string }) {
  const base = `/api/chamber/${run.id}/variants/${variant.variant}`;
  const details = variant.warningDetails ?? {};
  return <article className="border border-border-base bg-bg-1 p-3 space-y-3">
    <div className="flex justify-between data text-[10px]"><span>{variant.variant}</span><span className="text-amber">{variant.status}</span></div>
    <p className="text-sm text-ink-1 min-h-12">{String(details.reason ?? 'Waiting for a source-backed draft…')}</p>
    {details.confidence ? <div className="data text-[10px] text-ink-3">SCORE {Math.round(Number(details.confidence) * 100)}</div> : null}
    {variant.status === 'DRAFT_READY' ? <button disabled={Boolean(busy)} onClick={() => invoke(`${base}/accept`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' }).then(() => window.location.reload())} className="w-full bg-amber text-bg-0 py-2 data text-[10px]">ACCEPT DRAFT</button> : null}
    {variant.engineProjectId ? <VariantEditor base={base} variant={variant} invoke={invoke} busy={busy} /> : null}
    {variant.status === 'READY_TO_PUBLISH' ? <div className="border border-green-600/50 p-2 text-green-300 data text-[10px]">OBSERVED SUCCESS / READY TO PUBLISH</div> : null}
  </article>;
}

function VariantEditor({ base, variant, invoke, busy }: { base: string; variant: Variant; invoke: (path: string, init?: RequestInit) => Promise<any>; busy: string }) {
  const [project, setProject] = useState<any>(null);
  async function load() { const body = await invoke(`${base}/engine-project`); setProject(body.project); }
  async function edit(command: string, arguments_: Record<string, unknown>) {
    if (!project) return;
    const body = await invoke(`${base}/engine-project`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ command, arguments: arguments_, expectedRevision: project.revision }) });
    setProject(body.project);
  }
  const items = project?.tracks?.flatMap((track: any) => track.items) ?? [];
  const titles = project?.tracks?.flatMap((track: any) => track.items).filter((item: any) => item.kind === 'title') ?? [];
  const video = items.find((item: any) => item.kind === 'video');
  const caption = items.find((item: any) => item.kind === 'caption');
  return <div className="space-y-2">
    <button onClick={load} className="w-full border border-border-base py-2 data text-[10px]">{project ? `REFRESH EDITOR / REV ${project.revision}` : 'OPEN EDITOR'}</button>
    {project ? <div className="space-y-3 border border-border-base p-3">
      {titles.map((title: any) => <form key={title.id} className="space-y-1" onSubmit={(event) => {
        event.preventDefault(); const data = new FormData(event.currentTarget); void edit('timeline.set_title', { item_id: title.id, text: data.get('text') });
      }}><label className="block data text-[10px] text-ink-2">HOOK TITLE</label><div className="flex gap-2"><input name="text" defaultValue={title.text} maxLength={500} className="min-w-0 flex-1 border border-border-base bg-bg-0 px-2 py-1.5 text-xs text-ink-0" /><button className="border border-border-base px-2 data text-[10px]">SAVE</button></div></form>)}
      {video ? <>
        <form className="grid grid-cols-2 gap-2" onSubmit={(event) => {
          event.preventDefault(); const data = new FormData(event.currentTarget); const start = Math.round(Number(data.get('start')) * 120000); const duration = Math.round(Number(data.get('duration')) * 120000);
          void edit('timeline.trim_clip', { item_id: video.id, start_ticks: start, duration_ticks: duration, source_in_ticks: video.source_in_ticks, source_out_ticks: video.source_in_ticks + duration });
        }}><EditField label="START (SECONDS)" name="start" value={video.start_ticks / 120000} /><EditField label="DURATION (SECONDS)" name="duration" value={video.duration_ticks / 120000} /><button className="col-span-2 border border-border-base py-1.5 data text-[10px]">APPLY TRIM</button></form>
        <form className="grid grid-cols-3 gap-2" onSubmit={(event) => {
          event.preventDefault(); const data = new FormData(event.currentTarget); void edit('timeline.set_crop_keyframes', { item_id: video.id, keyframes: [{ time_ticks: 0, center_x: Number(data.get('x')), center_y: Number(data.get('y')), zoom: Number(data.get('zoom')), locked: true }] });
        }}><EditField label="CROP X" name="x" value={video.crop_keyframes?.[0]?.center_x ?? .5} step="0.01" /><EditField label="CROP Y" name="y" value={video.crop_keyframes?.[0]?.center_y ?? .5} step="0.01" /><EditField label="ZOOM" name="zoom" value={video.crop_keyframes?.[0]?.zoom ?? 1} step="0.05" /><button className="col-span-3 border border-border-base py-1.5 data text-[10px]">SET FRAMING</button></form>
        <form className="grid grid-cols-2 gap-2" onSubmit={(event) => {
          event.preventDefault(); const data = new FormData(event.currentTarget); void edit('timeline.set_audio_gain', { item_id: video.id, gain_db: Number(data.get('gain')), muted: data.get('muted') === 'on' });
        }}><EditField label="GAIN (DB)" name="gain" value={video.gain_db ?? 0} step="0.5" /><label className="flex items-end gap-2 pb-1.5 data text-[10px] text-ink-2"><input name="muted" type="checkbox" defaultChecked={video.muted} /> MUTE</label><button className="col-span-2 border border-border-base py-1.5 data text-[10px]">APPLY AUDIO</button></form>
      </> : null}
      {caption ? <form className="grid grid-cols-2 gap-2" onSubmit={(event) => {
        event.preventDefault(); const data = new FormData(event.currentTarget); void edit('timeline.set_caption_style', { item_id: caption.id, preset: data.get('preset'), position: data.get('position') });
      }}><SelectField label="CAPTION STYLE" name="preset" value={caption.caption_style?.preset ?? 'bold_pop'} options={['bold_pop', 'clean', 'minimal']} /><SelectField label="POSITION" name="position" value={caption.caption_style?.position ?? 'bottom'} options={['top', 'middle', 'bottom']} /><button className="col-span-2 border border-border-base py-1.5 data text-[10px]">APPLY CAPTIONS</button></form> : null}
    </div> : null}
    <button disabled={Boolean(busy)} onClick={() => invoke(`${base}/render`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ projectRevision: project?.revision ?? variant.engineRevision }) }).then(() => window.location.reload())} className="w-full bg-ink-0 text-bg-0 py-2 data text-[10px]">RENDER & VERIFY</button>
  </div>;
}

function EditField({ label, name, value, step = '0.1' }: { label: string; name: string; value: number; step?: string }) {
  return <label className="space-y-1 data text-[10px] text-ink-2"><span className="block">{label}</span><input name={name} type="number" step={step} defaultValue={value} className="w-full border border-border-base bg-bg-0 px-2 py-1.5 text-ink-0" /></label>;
}

function SelectField({ label, name, value, options }: { label: string; name: string; value: string; options: string[] }) {
  return <label className="space-y-1 data text-[10px] text-ink-2"><span className="block">{label}</span><select name={name} defaultValue={value} className="w-full border border-border-base bg-bg-0 px-2 py-1.5 text-ink-0">{options.map((option) => <option key={option}>{option}</option>)}</select></label>;
}
