'use client';

import Link from 'next/link';
import dynamic from 'next/dynamic';
import { Component, FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, Bot, Box, Camera, Captions, ChevronDown, CirclePlay, EyeOff, Film, Image as ImageIcon,
  Download, FileJson, Layers3, Link2, LoaderCircle, Mic2, MonitorPlay, MoreHorizontal, Pause, Pencil, Play, Plus,
  Redo2, Scissors, Search, Settings2, SlidersHorizontal, Split, Square, Trash2,
  ShieldCheck, Undo2, Upload, Volume2, WandSparkles, Wifi, WifiOff, X,
} from 'lucide-react';
import { CaptureSpool, CompletedCapture, createCaptureSpool, recoverCaptureSpools } from './capture-spool';
import { DirectorPanel } from './DirectorPanel';
import { SpatialAwarenessOverlay, useSpatialAwareness } from './SpatialAwareness';
import type { IntakeStage, ProductionSession, ProductionStage, ScreenshotCaptureRecord, WorkflowMode } from '@/lib/engine';

const SpatialCanvas = dynamic(() => import('./SpatialCanvas'), { ssr: false });

const TICKS = 120_000;
const MAX_DURATION = 180 * TICKS;

type Asset = {
  id: string; name: string; kind: string; intake_status: string; duration_ticks?: number | null;
  proxy_asset_id?: string | null; thumbnail_asset_id?: string | null; managed_uri?: string | null;
  parent_asset_id?: string | null; sha256?: string | null; source_kind?: string;
  observation_summary?: Record<string, unknown>;
};
type Item = {
  id: string; kind: string; track_id: string; name: string; start_ticks: number; duration_ticks: number;
  asset_id?: string | null; text?: string | null; gain_db?: number; muted?: boolean; x?: number; y?: number;
  scale?: number; opacity?: number; fit_mode?: string; caption_style?: { preset: string; position: string } | null;
};
type Track = { id: string; kind: string; name: string; items: Item[] };
type Project = {
  id: string; name: string; revision: number; duration_ticks: number;
  canvas: { width: number; height: number }; assets: Asset[]; tracks: Track[];
};
type Receipt = {
  id: string; command: string; status: string; actor: string; project_revision: number;
  created_at: string; payload?: Record<string, any>;
};
type MobilePane = 'media' | 'monitor' | 'timeline' | 'inspector';
type StudioDepth = 'edit' | 'context' | 'system';
type RuntimeConnection = 'connecting' | 'connected' | 'reconnecting' | 'offline';
type SpatialEntity = {
  id: string; kind: string; label: string; parent_id?: string | null; semantic_layer: string;
  revision: number; state: Record<string, any>; metadata: Record<string, any>;
  eligible_action_ids: string[]; position: { x: number; y: number; z: number };
  bounds: { width: number; height: number; depth: number };
};
type SpatialSnapshot = {
  canonical_revision: number; runtime_cursor: number; projection_hash: string;
  entities: SpatialEntity[]; edges: Array<{ id: string; source: string; target: string; relationship_kind: string }>;
  focus: string[]; truncation: { truncated: boolean; omitted_entities: number; omitted_edges: number };
};

function seconds(ticks: number) { return ticks / TICKS; }
function timecode(ticks: number) {
  const total = Math.max(0, Math.floor(seconds(ticks)));
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

export function Studio({
  controlProject, initialProject, initialContext, initialCatalog, initialReceipts, initialSpatial, initialDelivery,
  initialProduction,
}: {
  controlProject: {
    id: string; name: string;
    sequences?: Array<{
      id?: string; name?: string;
      deliveryProfiles?: Array<Record<string, any>>;
      releaseApprovals?: Array<Record<string, any> & { attempts?: Array<Record<string, any>> }>;
    }>;
  };
  initialProject: Project;
  initialContext: any;
  initialCatalog: any;
  initialReceipts: Receipt[];
  initialSpatial: SpatialSnapshot;
  initialDelivery: { delivery_profiles: Array<Record<string, any>>; release_approvals: Array<Record<string, any> & { attempts?: Array<Record<string, any>> }> };
  initialProduction: ProductionSession;
}) {
  const [project, setProject] = useState(initialProject);
  const [context, setContext] = useState(initialContext);
  const [catalog, setCatalog] = useState(initialCatalog);
  const [receipts, setReceipts] = useState<Receipt[]>(initialReceipts ?? []);
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [production, setProduction] = useState(initialProduction);
  const productionRef = useRef(initialProduction);
  const productionWrite = useRef<Promise<void>>(Promise.resolve());
  const sequenceId = controlProject.sequences?.[0]?.id ?? initialProject.id;
  const initialSequenceName = controlProject.sequences?.[0]?.name ?? `${controlProject.name} master`;
  const [projectName, setProjectName] = useState(controlProject.name);
  const [sequenceName, setSequenceName] = useState(initialSequenceName);
  const [renameOpen, setRenameOpen] = useState(false);
  const [draftProjectName, setDraftProjectName] = useState(controlProject.name);
  const [draftSequenceName, setDraftSequenceName] = useState(initialSequenceName);
  const [selectedId, setSelectedId] = useState<string | null>(
    initialProduction.focused_entity_id ?? initialContext?.shared_focus?.[0]?.id ?? initialProject.tracks.flatMap((track) => track.items)[0]?.id ?? null,
  );
  const [mobilePane, setMobilePane] = useState<MobilePane>('monitor');
  const [activityOpen, setActivityOpen] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [pairCode, setPairCode] = useState('');
  const [pairKind, setPairKind] = useState<'codex' | 'computer_use'>('codex');
  const [captureOpen, setCaptureOpen] = useState(false);
  const [depth, setDepth] = useState<StudioDepth>(initialProduction.active_depth);
  const [spatial, setSpatial] = useState<SpatialSnapshot>(initialSpatial);
  const [delivery, setDelivery] = useState(initialDelivery);
  const [show3d, setShow3d] = useState(false);
  const [spatialPaused, setSpatialPaused] = useState(false);
  const [runtimeConnection, setRuntimeConnection] = useState<RuntimeConnection>('connecting');
  const seenRuntimeEvents = useRef(new Set<string>());
  const [playing, setPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const awareness = useSpatialAwareness({
    projectId: controlProject.id,
    sequenceId,
    revision: project.revision,
    depth,
    triggerKey: `${production.current_stage}:${selectedId ?? ''}:${mobilePane}:${activityOpen}:${show3d}`,
  });

  const items = useMemo(() => project.tracks.flatMap((track) => track.items), [project]);
  const selected = items.find((item) => item.id === selectedId) ?? null;
  const selectedAsset = selected?.asset_id ? project.assets.find((asset) => asset.id === selected.asset_id) : null;
  const eligible = new Set((catalog?.eligibility ?? []).filter((entry: any) => entry.eligible).map((entry: any) => entry.name));
  const selectedSpatial = spatial.entities.find((entity) => entity.id === selectedId) ?? null;

  async function fetchSpatial(nextDepth: StudioDepth = depth, focusId: string | null = selectedId) {
    const query = new URLSearchParams({ depth: nextDepth, hop_count: nextDepth === 'system' ? '6' : '2' });
    if (focusId) query.set('focus_id', focusId);
    query.set('sequence_id', sequenceId);
    const response = await fetch(`/api/projects/${controlProject.id}/studio/spatial?${query}`, { cache: 'no-store' });
    const body = await response.json();
    if (!response.ok) throw new Error(body.message ?? body.error ?? 'Spatial context failed');
    setSpatial(body);
    return body as SpatialSnapshot;
  }

  const updateProduction = useCallback(async (patch: Record<string, unknown>) => {
    setProduction((current) => ({ ...current, ...patch } as ProductionSession));
    productionWrite.current = productionWrite.current.then(async () => {
      async function write(expectedRevision: number) {
        return fetch(`/api/projects/${controlProject.id}/repo-to-video/production`, {
          method: 'PUT', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ sequence_id: sequenceId, expected_revision: expectedRevision, ...patch }),
        });
      }
      let response = await write(productionRef.current.revision);
      if (response.status === 409) {
        const latest = await fetch(
          `/api/projects/${controlProject.id}/repo-to-video/production?sequence_id=${encodeURIComponent(sequenceId)}`,
          { cache: 'no-store' },
        );
        const latestBody = await latest.json();
        if (!latest.ok) throw new Error(latestBody.message ?? latestBody.detail ?? 'Production context reload failed');
        productionRef.current = latestBody.production;
        response = await write(productionRef.current.revision);
      }
      const body = await response.json();
      if (!response.ok) throw new Error(body.message ?? body.detail ?? 'Production context save failed');
      productionRef.current = body.production;
      setProduction(body.production);
    });
    return productionWrite.current;
  }, [controlProject.id, sequenceId]);

  function changeDepth(nextDepth: StudioDepth) {
    setDepth(nextDepth);
    void updateProduction({ active_depth: nextDepth });
    if (nextDepth !== 'edit') void fetchSpatial(nextDepth).catch((cause) => setError(cause instanceof Error ? cause.message : 'Spatial context failed'));
  }

  function changeStage(nextStage: ProductionStage) {
    setActivityOpen(false);
    void updateProduction({ current_stage: nextStage });
  }

  function changeWorkflowMode(workflowMode: WorkflowMode) {
    const intakeStage: IntakeStage = workflowMode === 'repo_to_video' ? 'evidence' : 'source';
    void updateProduction({ workflow_mode: workflowMode, intake_stage: intakeStage, current_stage: 'director' });
  }

  function changeIntakeStage(intakeStage: IntakeStage) {
    setActivityOpen(false);
    void updateProduction({ intake_stage: intakeStage, current_stage: 'director' });
  }

  async function refresh(silent = false) {
    if (!silent) setBusy('refresh');
    const response = await fetch(
      `/api/projects/${controlProject.id}/studio?sequence_id=${encodeURIComponent(sequenceId)}`,
      { cache: 'no-store' },
    );
    const body = await response.json();
    if (!response.ok) throw new Error(body.message ?? body.error ?? 'Studio refresh failed');
    setProject(body.project); setContext(body.context); setCatalog(body.catalog);
    setReceipts(body.receipts?.receipts ?? body.receipts ?? []);
    setSuggestions(body.suggestions?.suggestions ?? []);
    if (body.spatial && depth !== 'edit') setSpatial(body.spatial);
    if (body.delivery) setDelivery(body.delivery);
    if (body.production) {
      productionRef.current = body.production;
      setProduction(body.production);
      setDepth(body.production.active_depth);
    }
    if (body.controlProject?.name) setProjectName(String(body.controlProject.name));
    if (body.sequence?.name) setSequenceName(String(body.sequence.name));
    if (!silent) setBusy('');
  }

  useEffect(() => {
    const intervalMs = runtimeConnection === 'connected' ? 15_000 : 2_500;
    const timer = window.setInterval(() => {
      if (!document.hidden) void refresh(true).catch(() => undefined);
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [controlProject.id, runtimeConnection]);

  useEffect(() => {
    const refreshForComputerUse = () => void refresh(true).catch(() => undefined);
    window.addEventListener('sag:computer-use:refresh', refreshForComputerUse);
    return () => window.removeEventListener('sag:computer-use:refresh', refreshForComputerUse);
  }, [controlProject.id, sequenceId]);

  useEffect(() => {
    setSpatialPaused(window.localStorage.getItem(`sag-spatial-paused:${controlProject.id}`) === '1');
    setShow3d(window.matchMedia('(min-width: 768px) and (orientation: landscape)').matches);
  }, [controlProject.id]);

  useEffect(() => {
    if (depth !== 'edit') void fetchSpatial(depth).catch(() => undefined);
  }, [depth, project.revision, selectedId]);

  useEffect(() => {
    const storedCursor = window.sessionStorage.getItem(`sag-runtime-cursor:${controlProject.id}`) ?? '0';
    const runtimeQuery = new URLSearchParams({ cursor: storedCursor, sequence_id: sequenceId });
    const source = new EventSource(`/api/projects/${controlProject.id}/studio/runtime?${runtimeQuery}`);
    let offlineTimer: number | undefined;
    source.onopen = () => {
      if (offlineTimer) window.clearTimeout(offlineTimer);
      setRuntimeConnection('connected');
    };
    source.onerror = () => {
      setRuntimeConnection('reconnecting');
      if (offlineTimer) window.clearTimeout(offlineTimer);
      offlineTimer = window.setTimeout(() => setRuntimeConnection('offline'), 10_000);
    };

    function rememberRuntimeCursor(message: MessageEvent<string>) {
      try {
        const event = JSON.parse(message.data);
        if (event?.cursor) window.sessionStorage.setItem(`sag-runtime-cursor:${controlProject.id}`, String(event.cursor));
      } catch { /* Ignore malformed runtime telemetry. */ }
    }

    async function acknowledge(
      directive: any, success: boolean, findings: Array<Record<string, unknown>> = [],
      beforeFrame: any = null, afterFrame: any = null,
    ) {
      const binding = beforeFrame?.bindings?.find((entry: any) => entry.binding_id === directive.binding_id);
      await fetch(`/api/projects/${controlProject.id}/studio/spatial`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          operation: 'ack', receiptId: directive.receipt_id, sequenceId,
          acknowledgement: {
            consumer_id: `studio:${controlProject.id}`,
            projection_hash: directive.expected_projection_hash,
            observed_target_ids: success ? directive.target_ids : [],
            active_depth: depth, renderer_mode: show3d ? 'webgl' : 'dom_tree', findings, success,
            before_frame_id: directive.expected_frame_id ?? beforeFrame?.frame_id,
            after_frame_id: afterFrame?.frame_id,
            changed_entity_ids: success ? directive.target_ids : [],
            changed_cells: binding?.cells ?? [],
            action_route: {
              kind: 'semantic_handler', action: directive.action,
              target_id: directive.target_ids?.[0] ?? null,
              binding_id: directive.binding_id ?? null, confidence: binding?.confidence ?? 1,
            },
          },
        }),
      });
    }

    function onDirective(message: MessageEvent<string>) {
      let event: any;
      try { event = JSON.parse(message.data); } catch { return; }
      if (!event?.event_id || seenRuntimeEvents.current.has(event.event_id)) return;
      seenRuntimeEvents.current.add(event.event_id);
      if (seenRuntimeEvents.current.size > 500) seenRuntimeEvents.current.delete(seenRuntimeEvents.current.values().next().value!);
      window.sessionStorage.setItem(`sag-runtime-cursor:${controlProject.id}`, String(event.cursor));
      const directive = event.payload?.directive;
      if (!directive) return;
      if (spatialPaused) {
        void acknowledge(directive, false, [{ code: 'agent_spatial_paused', summary: 'Browser spatial directives are paused.' }]);
        return;
      }
      void (async () => {
        let beforeFrame = awareness.latestFrameRef.current;
        if (directive.expected_frame_id && beforeFrame?.frame_id !== directive.expected_frame_id) {
          const response = await fetch(
            `/api/projects/${controlProject.id}/studio/spatial/frames/${encodeURIComponent(directive.expected_frame_id)}?sequence_id=${encodeURIComponent(sequenceId)}`,
            { cache: 'no-store' },
          );
          if (!response.ok) throw new Error('Expected spatial frame is unavailable');
          beforeFrame = await response.json();
        }
        const targetId = directive.target_ids?.[0] ?? null;
        if (targetId) setSelectedId(targetId);
        let nextDepth = depth;
        if (directive.action === 'spatial.set_depth') {
          const requested = directive.intended_observed_effect?.active_depth;
          nextDepth = requested === 'edit' || requested === 'system' ? requested : 'context';
          changeDepth(nextDepth);
        } else if (directive.action === 'spatial.reset_view') {
          setShow3d(window.matchMedia('(min-width: 768px) and (orientation: landscape)').matches);
        } else if (directive.action !== 'spatial.focus_entity' && directive.action !== 'spatial.frame_entity') {
          nextDepth = directive.action === 'spatial.reveal_blast_radius' ? 'system' : 'context';
          changeDepth(nextDepth);
        }
        await fetchSpatial(nextDepth, targetId);
        await new Promise((resolve) => window.setTimeout(resolve, 80));
        const afterFrame = await awareness.declareFrameNow();
        await acknowledge(directive, true, [], beforeFrame, afterFrame);
      })().catch((cause) => {
        void acknowledge(directive, false, [{ code: 'projection_failed', summary: cause instanceof Error ? cause.message : 'Projection failed.' }]);
      });
    }

    source.addEventListener('spatial.directive.dispatched', onDirective as EventListener);
    source.addEventListener('spatial.frame.declared', rememberRuntimeCursor as EventListener);
    source.addEventListener('spatial.action.routed', rememberRuntimeCursor as EventListener);
    source.addEventListener('spatial.effect.observed', rememberRuntimeCursor as EventListener);
    source.addEventListener('snapshot_required', () => { void fetchSpatial(depth).catch(() => undefined); });
    source.addEventListener('receipt.transitioned', () => { void refresh(true).catch(() => undefined); });
    return () => {
      if (offlineTimer) window.clearTimeout(offlineTimer);
      source.close();
    };
  }, [controlProject.id, sequenceId, depth, show3d, spatialPaused, awareness.declareFrameNow]);

  async function operate(operation: string, payload: Record<string, unknown> = {}) {
    setBusy(operation); setError('');
    try {
      const response = await fetch(`/api/projects/${controlProject.id}/studio`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ operation, sequenceId, expectedRevision: project.revision, ...payload }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.message ?? body.error ?? body.detail ?? 'Studio operation failed');
      if (body.project) setProject(body.project);
      await refresh(true);
      return body.result;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Studio operation failed');
      throw cause;
    } finally { setBusy(''); }
  }

  async function command(name: string, arguments_: Record<string, unknown>, confirm = false) {
    return operate('command', { command: name, arguments: arguments_, confirm });
  }

  async function renameProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = draftProjectName.trim();
    const nextSequenceName = draftSequenceName.trim();
    if (!name || !nextSequenceName) {
      setError('Project and sequence names are required.');
      return;
    }
    try {
      const result = await operate('rename', { name, sequenceName: nextSequenceName });
      setProjectName(name);
      setSequenceName(nextSequenceName);
      setRenameOpen(false);
      return result;
    } catch {
      return undefined;
    }
  }

  async function select(item: Item) {
    setSelectedId(item.id);
    void updateProduction({ focused_entity_id: item.id });
    await operate('select', { itemIds: [item.id] });
  }

  async function selectSpatial(entityId: string) {
    setSelectedId(entityId);
    void updateProduction({ focused_entity_id: entityId });
    const item = items.find((entry) => entry.id === entityId);
    if (item) await operate('select', { itemIds: [item.id] });
  }

  async function pair() {
    const result = await operate('pair');
    setPairKind('codex');
    setPairCode(String(result.code));
  }

  async function pairComputerUse() {
    const result = await operate('pair_computer_use');
    setPairKind('computer_use');
    setPairCode(String(result.code));
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy('upload'); setError('');
    try {
      const response = await fetch(`/api/projects/${controlProject.id}/assets/upload?sequence_id=${encodeURIComponent(sequenceId)}`, {
        method: 'POST', body: new FormData(event.currentTarget),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.message ?? body.error ?? 'Upload failed');
      event.currentTarget.reset();
      await refresh(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Upload failed');
    } finally { setBusy(''); }
  }

  async function deleteSelected() {
    if (!selected || !window.confirm(`Delete ${selected.name} from this sequence?`)) return;
    await command('timeline.delete_item', { item_id: selected.id }, true);
    setSelectedId(null);
  }

  const mediaUrl = selectedAsset?.managed_uri
    ? `/api/projects/${controlProject.id}/studio/assets/${selectedAsset.id}/${selectedAsset.proxy_asset_id ? 'proxy' : 'content'}?sequence_id=${encodeURIComponent(sequenceId)}`
    : null;
  const renderReceipts = [...receipts]
    .filter((receipt) => receipt.command === 'render.verified')
    .sort((left, right) => String(right.created_at).localeCompare(String(left.created_at)));
  const latestRender = renderReceipts[0];
  const renderInFlight = Boolean(latestRender && ['accepted', 'dispatched', 'rendering', 'artifact_written', 'awaiting_observation'].includes(latestRender.status));
  const latestVerifiedRender = renderReceipts.find((receipt) => (
    receipt.status === 'observed_success'
    && receipt.payload?.artifact_id
    && receipt.payload?.artifact_sha256
    && receipt.payload?.qc_report?.passed === true
  ));

  useEffect(() => {
    if (!renderInFlight) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) void refresh(true).catch(() => undefined);
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [renderInFlight, latestRender?.id]);

  return <div className="studio-root" ref={awareness.rootRef} data-sag-entity-id="viewport:studio"
    data-sag-project-id={controlProject.id} data-sag-project-revision={project.revision}
    data-sag-action-ids="spatial.reset_view">
    <header className="studio-header" data-sag-entity-id="viewport:studio-header" data-sag-action-ids="spatial.set_depth">
      <div className="studio-project-identity">
        <Link href="/dashboard" className="studio-mark" aria-label="Back to projects"><Film size={19} /></Link>
        <button className="studio-project-name" type="button" onClick={() => {
          setDraftProjectName(projectName); setDraftSequenceName(sequenceName); setRenameOpen(true);
        }} aria-label="Rename project and sequence">
          <span>{projectName}</span>
          <small>{sequenceName} / REV {project.revision} / {project.canvas.width}×{project.canvas.height}</small>
          <Pencil size={12} aria-hidden="true" />
        </button>
      </div>
      <div className="studio-header-actions">
        <div className="studio-depth-switch" role="group" aria-label="Studio depth">
          {(['edit', 'context', 'system'] as const).map((value) => <button
            key={value} className={depth === value ? 'active' : ''} aria-pressed={depth === value}
            data-sag-entity-id={`viewport:studio-depth-${value}`} data-sag-action-ids="spatial.set_depth"
            onClick={() => changeDepth(value)}>{value.charAt(0).toUpperCase() + value.slice(1)}</button>)}
        </div>
        <div className="studio-command-strip">
          <button className="studio-button secondary" onClick={() => void command('project.undo', {})} disabled={busy !== '' || !eligible.has('project.undo')} aria-label="Undo"><Undo2 size={15} /><span className="hidden sm:inline">Undo</span></button>
          <button className="studio-button secondary hidden md:flex" onClick={() => void command('project.redo', {})} disabled={busy !== '' || !eligible.has('project.redo')}><Redo2 size={15} />Redo</button>
          <button className="studio-button secondary" onClick={() => void pair()} disabled={busy !== ''} aria-label="Pair Codex"><Link2 size={15} /><span className="hidden sm:inline">Pair Codex</span></button>
          <button className="studio-button secondary hidden md:flex" onClick={() => void pairComputerUse()} disabled={busy !== ''} aria-label="Pair browser computer use"><MonitorPlay size={15} />Pair browser</button>
          <button className="studio-button director-trigger" aria-pressed={production.current_stage === 'director'} aria-label="Director" onClick={() => changeStage('director')}><WandSparkles size={15} /><span className="hidden sm:inline">Director</span></button>
          <button className="studio-button primary" onClick={() => void operate('render')} disabled={busy !== '' || renderInFlight}><CirclePlay size={15} />{renderInFlight ? 'Rendering' : 'Render'}</button>
          <button className="studio-icon-button" onClick={() => setActivityOpen((value) => !value)} aria-label="Open governance"><Activity size={17} /></button>
        </div>
      </div>
    </header>

    <div className="studio-runtime-strip" aria-live="polite">
      <RuntimeState connection={runtimeConnection} />
      <span className={`studio-render-state ${latestRender?.status ?? 'idle'}`}>
        {renderInFlight
          ? `Render: ${latestRender!.status.replaceAll('_', ' ')}`
          : latestRender?.status === 'observed_failure' || latestRender?.status === 'execution_failed'
            ? 'Latest render failed verification'
            : latestVerifiedRender ? `Verified revision ${latestVerifiedRender.project_revision}` : 'No verified output'}
      </span>
      {latestVerifiedRender ? <VerifiedDownloadLinks
        projectId={controlProject.id} sequenceId={sequenceId} receipt={latestVerifiedRender} compact
      /> : null}
    </div>

    {renameOpen ? <form className="studio-name-editor" onSubmit={renameProject} aria-label="Rename project and sequence">
      <label>Project name<input autoFocus value={draftProjectName} maxLength={120} onChange={(event) => setDraftProjectName(event.target.value)} /></label>
      <label>Sequence name<input value={draftSequenceName} maxLength={120} onChange={(event) => setDraftSequenceName(event.target.value)} /></label>
      <div>
        <button className="studio-button secondary" type="button" onClick={() => setRenameOpen(false)}>Cancel</button>
        <button className="studio-button primary" type="submit" disabled={busy !== ''}>{busy === 'rename' ? 'Saving' : 'Save names'}</button>
      </div>
    </form> : null}

    {pairCode ? <div className="studio-notice" role="status">
      <Bot size={17} /><span>{pairKind === 'computer_use' ? 'Browser pairing code' : 'Pairing code'}</span><strong>{pairCode}</strong><span className="text-ink-2">{pairKind === 'computer_use' ? 'Workspace-scoped computer-use principal; code expires in ten minutes.' : 'Scoped to this sequence for ten minutes.'}</span>
      <button onClick={() => setPairCode('')} aria-label="Dismiss pairing code"><X size={15} /></button>
    </div> : null}
    {error ? <div className="studio-error" role="alert"><span>{error}</span><button onClick={() => setError('')}><X size={15} /></button></div> : null}

    <nav className="studio-stage-rail" aria-label="Production stages">
      <div className="studio-workflow-switch" role="group" aria-label="Workflow mode">
        <button className={production.workflow_mode === 'repo_to_video' ? 'active' : ''} aria-pressed={production.workflow_mode === 'repo_to_video'} onClick={() => changeWorkflowMode('repo_to_video')}>Repository</button>
        <button className={production.workflow_mode === 'source_to_shorts' ? 'active' : ''} aria-pressed={production.workflow_mode === 'source_to_shorts'} onClick={() => changeWorkflowMode('source_to_shorts')}>Source video</button>
      </div>
      {(production.workflow_mode === 'repo_to_video'
        ? ([['evidence', 'Evidence'], ['brief', 'Brief'], ['storyboard', 'Storyboard'], ['keyframes', 'Keyframes']] as const)
        : ([['source', 'Source'], ['analysis', 'Analysis'], ['ranked_clips', 'Ranked clips'], ['reframe', 'Reframe']] as const)
      ).map(([stage, label]) => <button
        key={stage} className={production.current_stage === 'director' && production.intake_stage === stage ? 'active' : ''}
        aria-current={production.current_stage === 'director' && production.intake_stage === stage ? 'step' : undefined}
        onClick={() => changeIntakeStage(stage)}
      >{label}</button>)}
      {(['director', 'scenes', 'edit', 'finish', 'review', 'deliver'] as const).map((stage) => <button
        key={stage} className={production.current_stage === stage ? 'active' : ''}
        aria-label={`${stage.charAt(0).toUpperCase() + stage.slice(1)} stage`}
        aria-current={production.current_stage === stage ? 'step' : undefined}
        onClick={() => changeStage(stage)}
      >{stage.charAt(0).toUpperCase() + stage.slice(1)}</button>)}
    </nav>

    {depth === 'edit' && production.current_stage === 'edit' ? <main className="studio-workspace">
      <section className={`studio-panel studio-media ${mobilePane === 'media' ? 'mobile-active' : ''}`} aria-label="Media" data-sag-entity-id="viewport:media" data-sag-action-ids="spatial.frame_entity">
        <PanelHeading icon={<Layers3 size={15} />} title="Media" action={<button className="studio-icon-button compact" aria-label="Search media"><Search size={14} /></button>} />
        <div className="studio-panel-body space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <button className="studio-button secondary" onClick={() => setCaptureOpen((value) => !value)}><Camera size={14} />Capture</button>
            <button className="studio-button secondary" disabled={busy !== '' || renderInFlight} onClick={() => void operate('render')}><CirclePlay size={14} />{renderInFlight ? 'Rendering' : 'Preview'}</button>
          </div>
          {project.assets.some((asset) => !asset.parent_asset_id && asset.intake_status === 'observed_valid') ? <button
            className="studio-button primary w-full" disabled={busy !== ''}
            onClick={() => {
              const source = project.assets.find((asset) => !asset.parent_asset_id && asset.intake_status === 'observed_valid');
              if (source) void operate('analyze', { assetId: source.id });
            }}><WandSparkles size={14} />Find short moments</button> : null}
          {suggestions.length ? <div className="space-y-2">
            <div className="text-[10px] font-medium text-ink-2">Suggested moments</div>
            {suggestions.slice(0, 5).map((suggestion) => <div key={suggestion.id} className="studio-suggestion">
              <strong>{suggestion.provenance?.hook ?? suggestion.generator_kind ?? 'Candidate'}</strong>
              <span>{timecode(Number(suggestion.provenance?.start_ticks ?? 0))} / {timecode(Number(suggestion.provenance?.duration_ticks ?? 0))}</span>
            </div>)}
          </div> : null}
          {captureOpen ? <CaptureControl projectId={controlProject.id} sequenceId={sequenceId} onComplete={() => refresh(true)} /> : null}
          <form onSubmit={upload} className="studio-dropzone">
            <Upload size={19} /><span>Import video or audio</span><input name="file" type="file" accept="video/*,audio/*,image/*" aria-label="Import media" />
          </form>
          <div className="grid grid-cols-2 gap-2">
            {project.assets.filter((asset) => !asset.parent_asset_id).map((asset) => <button
              key={asset.id} className="studio-media-tile"
              data-sag-entity-id={asset.id} data-sag-action-ids="spatial.focus_entity"
              onClick={() => {
                const existing = items.find((item) => item.asset_id === asset.id);
                if (existing) void select(existing);
              }}
            >
              <span className="studio-thumb">
                {asset.thumbnail_asset_id ? <img src={`/api/projects/${controlProject.id}/studio/assets/${asset.id}/thumbnail?sequence_id=${encodeURIComponent(sequenceId)}`} alt="" /> : asset.kind === 'image' ? <ImageIcon size={21} /> : <Film size={21} />}
              </span>
              <span className="truncate text-left text-[11px] text-ink-1">{asset.name}</span>
              <span className="font-mono text-[9px] text-ink-3">{asset.duration_ticks ? timecode(asset.duration_ticks) : asset.kind}</span>
              <span className={`studio-media-verification ${asset.intake_status === 'observed_valid' ? 'verified' : asset.intake_status === 'observed_invalid' ? 'invalid' : ''}`}>
                <span>{asset.intake_status.replaceAll('_', ' ')}</span>{asset.sha256 ? <code>{asset.sha256.slice(0, 10)}</code> : null}
              </span>
            </button>)}
          </div>
          {project.assets.length === 0 ? <EmptyState icon={<Upload size={20} />} title="No media yet" detail="Import a recording to start the cut." /> : null}
        </div>
      </section>

      <section className={`studio-monitor ${mobilePane === 'monitor' ? 'mobile-active' : ''}`} aria-label="Program monitor" data-sag-entity-id="viewport:monitor" data-sag-action-ids="spatial.frame_entity">
        <div className="studio-stage">
          {mediaUrl && selectedAsset?.kind === 'video' ? <video ref={videoRef} src={mediaUrl} playsInline onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} /> :
            <div className="studio-stage-empty"><MonitorPlay size={30} /><span>{selected ? selected.name : 'Select a clip to preview'}</span></div>}
          {selected?.kind === 'title' ? <div className="studio-title-preview">{selected.text}</div> : null}
        </div>
        <div className="studio-transport">
          <button className="studio-icon-button" onClick={() => {
            const video = videoRef.current; if (!video) return;
            if (video.paused) void video.play(); else video.pause();
          }} aria-label={playing ? 'Pause' : 'Play'}>{playing ? <Pause size={17} /> : <Play size={17} />}</button>
          <span className="font-mono text-[10px] text-ink-2">00:00 / {timecode(project.duration_ticks)}</span>
          <div className="flex-1" />
          <button className="studio-icon-button" aria-label="Monitor settings"><Settings2 size={16} /></button>
        </div>
      </section>

      <aside className={`studio-panel studio-inspector ${mobilePane === 'inspector' ? 'mobile-active' : ''}`} aria-label="Inspector" data-sag-entity-id="viewport:inspector" data-sag-action-ids="spatial.frame_entity">
        <PanelHeading icon={<SlidersHorizontal size={15} />} title="Inspector" />
        <div className="studio-panel-body">
          {selected ? <Inspector item={selected} disabled={busy !== ''} onCommand={command} onDelete={deleteSelected} /> :
            <EmptyState icon={<SlidersHorizontal size={20} />} title="Nothing selected" detail="Choose a timeline item to edit its properties." />}
        </div>
      </aside>

      <section className={`studio-timeline ${mobilePane === 'timeline' ? 'mobile-active' : ''}`} aria-label="Timeline" data-sag-entity-id="viewport:timeline" data-sag-action-ids="spatial.frame_entity">
        <div className="studio-timeline-toolbar">
          <div className="flex items-center gap-1">
            <button className="studio-icon-button" title="Split selected clip" disabled={!selected || busy !== ''} onClick={() => selected && void command('timeline.split_clip', { item_id: selected.id, at_ticks: selected.start_ticks + Math.floor(selected.duration_ticks / 2) })}><Split size={16} /></button>
            <button className="studio-icon-button" title="Delete selected item" disabled={!selected || busy !== ''} onClick={() => void deleteSelected()}><Trash2 size={16} /></button>
          </div>
          <div className="font-mono text-[10px] text-ink-2">MASTER / {timecode(project.duration_ticks)} / MAGNETIC PRIMARY</div>
          <div className="flex items-center gap-1"><button className="studio-icon-button"><Scissors size={16} /></button><button className="studio-icon-button"><MoreHorizontal size={16} /></button></div>
        </div>
        <div className="studio-timeline-scroll">
          <div className="studio-ruler"><span>00:00</span><span>{timecode(project.duration_ticks / 2)}</span><span>{timecode(project.duration_ticks)}</span></div>
          {project.tracks.map((track) => <div className="studio-track" key={track.id}>
            <div className="studio-track-label"><TrackIcon kind={track.kind} /><span>{track.name}</span></div>
            <div className="studio-track-lane">
              {track.items.map((item) => {
                const left = Math.min(98, item.start_ticks / Math.max(project.duration_ticks, 1) * 100);
                const width = Math.max(4, Math.min(100 - left, item.duration_ticks / Math.max(project.duration_ticks, 1) * 100));
                return <button key={item.id} className={`studio-clip ${item.id === selectedId ? 'selected' : ''} ${item.kind}`}
                  data-sag-entity-id={item.id} data-sag-action-ids="spatial.focus_entity,spatial.frame_entity"
                  style={{ left: `${left}%`, width: `${width}%` }} onClick={() => void select(item)}>
                  <span>{item.name}</span><small>{timecode(item.duration_ticks)}</small>
                </button>;
              })}
            </div>
          </div>)}
        </div>
      </section>
    </main> : depth === 'edit' ? <ProductionStageWorkspace
      stage={production.current_stage}
      production={production}
      project={project}
      receipts={receipts}
      delivery={delivery}
      suggestions={suggestions}
      projectId={controlProject.id}
      sequenceId={sequenceId}
      onProductionUpdate={updateProduction}
      onProjectRefresh={() => refresh(true)}
      onOpenEdit={() => changeStage('edit')}
      onRender={() => operate('render')}
    /> : <SpatialWorkspace
      snapshot={spatial}
      depth={depth}
      selectedId={selectedId}
      selectedEntity={selectedSpatial}
      show3d={show3d}
      paused={spatialPaused}
      connection={runtimeConnection}
      onSelect={(entityId) => void selectSpatial(entityId)}
      onToggle3d={() => setShow3d((value) => !value)}
      onTogglePause={() => {
        setSpatialPaused((value) => {
          window.localStorage.setItem(`sag-spatial-paused:${controlProject.id}`, value ? '0' : '1');
          return !value;
        });
      }}
      onOpenGovernance={() => setActivityOpen(true)}
    />}

    {depth === 'edit' && production.current_stage === 'edit' ? <nav className="studio-mobile-nav" aria-label="Studio panes">
      {([
        ['media', <Layers3 size={18} />, 'Media'], ['monitor', <MonitorPlay size={18} />, 'Preview'],
        ['timeline', <Film size={18} />, 'Timeline'], ['inspector', <SlidersHorizontal size={18} />, 'Inspector'],
      ] as const).map(([pane, icon, label]) => <button key={pane} className={mobilePane === pane ? 'active' : ''} onClick={() => setMobilePane(pane)}>{icon}<span>{label}</span></button>)}
    </nav> : null}

    {activityOpen ? <ActivityDrawer
      receipts={receipts}
      context={context}
      delivery={delivery}
      projectId={controlProject.id}
      sequenceId={sequenceId}
      onClose={() => setActivityOpen(false)}
    /> : null}
    {busy ? <div className="studio-busy" role="status"><LoaderCircle className="animate-spin" size={16} />{
      busy === 'refresh' ? 'Refreshing Studio'
        : busy === 'render' ? 'Starting verified render'
          : busy === 'rename' ? 'Saving project names'
            : busy === 'upload' ? 'Importing media'
              : 'Applying change'
    }</div> : null}
    <SpatialAwarenessOverlay frame={awareness.frame} status={awareness.status} />
  </div>;
}

function RuntimeState({ connection }: { connection: RuntimeConnection }) {
  const labels: Record<RuntimeConnection, string> = {
    connecting: 'Runtime connecting',
    connected: 'Runtime connected',
    reconnecting: 'Runtime reconnecting',
    offline: 'Runtime offline',
  };
  return <span className={`studio-runtime-state ${connection}`} role="status">
    {connection === 'connected' ? <Wifi size={13} /> : connection === 'connecting' ? <LoaderCircle className="animate-spin" size={13} /> : <WifiOff size={13} />}
    {labels[connection]}
  </span>;
}

function VerifiedDownloadLinks({
  projectId, sequenceId, receipt, compact = false,
}: {
  projectId: string; sequenceId: string; receipt: Receipt; compact?: boolean;
}) {
  const artifactId = String(receipt.payload?.artifact_id ?? '');
  const query = `sequence_id=${encodeURIComponent(sequenceId)}`;
  return <div className={`studio-download-actions ${compact ? 'compact' : ''}`}>
    <a className="studio-button secondary" href={`/api/projects/${projectId}/studio/artifacts/${encodeURIComponent(artifactId)}/content?${query}`} download>
      <Download size={14} />Video
    </a>
    <a className="studio-button secondary" href={`/api/projects/${projectId}/studio/receipts/${encodeURIComponent(receipt.id)}/download?${query}`} download>
      <FileJson size={14} />Receipt
    </a>
  </div>;
}

function ProductionStageWorkspace({
  stage, production, project, receipts, delivery, suggestions, projectId, sequenceId,
  onProductionUpdate, onProjectRefresh, onOpenEdit, onRender,
}: {
  stage: ProductionStage; production: ProductionSession; project: Project; receipts: Receipt[];
  delivery: { delivery_profiles: Array<Record<string, any>>; release_approvals: Array<Record<string, any>> };
  suggestions: any[];
  projectId: string; sequenceId: string;
  onProductionUpdate: (patch: Record<string, unknown>) => Promise<void>;
  onProjectRefresh: () => Promise<void>; onOpenEdit: () => void; onRender: () => Promise<unknown>;
}) {
  const [screenshotCaptures, setScreenshotCaptures] = useState<ScreenshotCaptureRecord[]>([]);
  const [screenshotBusy, setScreenshotBusy] = useState('');
  const [screenshotError, setScreenshotError] = useState('');

  const loadScreenshotCaptures = useCallback(async () => {
    const response = await fetch(`/api/projects/${projectId}/studio/screenshots?sequence_id=${encodeURIComponent(sequenceId)}`, { cache: 'no-store' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(String(body.message ?? body.error ?? 'Screenshot review could not be loaded'));
    setScreenshotCaptures(body.captures ?? []);
  }, [projectId, sequenceId]);

  useEffect(() => {
    if (stage !== 'review') return;
    void loadScreenshotCaptures().catch((cause) => {
      setScreenshotError(cause instanceof Error ? cause.message : 'Screenshot review could not be loaded');
    });
  }, [stage, loadScreenshotCaptures]);

  async function decideScreenshot(captureId: string, decision: 'approved' | 'rejected') {
    setScreenshotBusy(captureId); setScreenshotError('');
    try {
      const response = await fetch(`/api/projects/${projectId}/studio/screenshots/${captureId}/decisions?sequence_id=${encodeURIComponent(sequenceId)}`, {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ decision }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(body.message ?? body.error ?? 'Screenshot decision failed'));
      setScreenshotCaptures((current) => current.map((entry) => entry.id === captureId ? body.capture : entry));
    } catch (cause) {
      setScreenshotError(cause instanceof Error ? cause.message : 'Screenshot decision failed');
    } finally {
      setScreenshotBusy('');
    }
  }

  if (stage === 'director' && production.workflow_mode === 'source_to_shorts') return <SourceToShortsStage
    intakeStage={production.intake_stage} production={production} project={project} suggestions={suggestions}
    onOpenEdit={onOpenEdit} onProductionUpdate={onProductionUpdate}
  />;

  if (stage === 'director') return <main className="studio-production-stage stage-director" aria-label="Director stage">
    <DirectorPanel
      projectId={projectId} sequenceId={sequenceId} projectRevision={project.revision}
      production={production} onProductionUpdate={onProductionUpdate}
      onProjectRefresh={onProjectRefresh} onClose={onOpenEdit}
    />
  </main>;

  if (stage === 'scenes') {
    const storyboard = production.active_storyboard;
    return <main className="studio-production-stage" aria-label="Scenes stage">
      <StageHeading title="Scenes" detail="Storyboard units, evidence links, and generation readiness remain bound to one production context." />
      {storyboard ? <section className="studio-scene-board" aria-label="Storyboard scenes">
        {storyboard.scenes.map((scene) => {
          const decision = production.scene_decisions[scene.id];
          return <article key={scene.id} className="studio-stage-card">
            <header><code>{scene.id}</code><span>{scene.start_seconds.toFixed(1)}s / {scene.duration_seconds.toFixed(1)}s</span></header>
            <strong>{scene.purpose}</strong>
            <p>{scene.visual_direction}</p>
            <dl><div><dt>Evidence</dt><dd>{scene.evidence_refs.length} links</dd></div><div><dt>Model</dt><dd>{scene.generation_model}</dd></div><div><dt>Decision</dt><dd>{String(decision?.decision ?? 'Not reviewed')}</dd></div></dl>
          </article>;
        })}
      </section> : <StageEmpty title="No approved storyboard" detail="Return to Director to inspect repository evidence and prepare scene units." />}
    </main>;
  }

  if (stage === 'finish') {
    const audioItems = project.tracks.filter((track) => track.kind === 'audio').flatMap((track) => track.items);
    const captionItems = project.tracks.filter((track) => track.kind === 'caption').flatMap((track) => track.items);
    const variants = Object.entries(production.variants);
    return <main className="studio-production-stage" aria-label="Finish stage">
      <StageHeading title="Finish" detail="Inspect the canonical timeline, audio, captions, and linked platform overlays before review." />
      <section className="studio-stage-metrics" aria-label="Finishing state">
        <div><span>Master revision</span><strong>{project.revision}</strong></div>
        <div><span>Audio items</span><strong>{audioItems.length}</strong></div>
        <div><span>Caption items</span><strong>{captionItems.length}</strong></div>
        <div><span>Linked variants</span><strong>{variants.length}</strong></div>
      </section>
      {variants.length ? <section className="studio-variant-list">{variants.map(([id, variant]) => <article key={id} className="studio-stage-card"><code>{id}</code><strong>{String(variant.aspect_ratio ?? 'Aspect ratio not set')}</strong><p>{String(variant.status ?? 'Revisioned overlay')}</p></article>)}</section> : <StageEmpty title="No variant overlays" detail="The canonical master remains authoritative. Linked 9:16, 16:9, and 1:1 overlays are configured here." />}
      <button className="studio-button primary studio-stage-action" onClick={onOpenEdit}><Scissors size={14} />Open canonical edit</button>
    </main>;
  }

  if (stage === 'review') {
    const storyboard = production.active_storyboard;
    const sceneCount = storyboard?.scenes.length ?? 0;
    const evidenceBound = storyboard?.scenes.filter((scene) => scene.evidence_refs.length > 0).length ?? 0;
    const accepted = Object.values(production.scene_decisions).filter((entry) => entry.decision === 'accepted').length;
    const observedReceipts = receipts.filter((receipt) => receipt.status === 'observed_success').length;
    const approvedScreenshots = screenshotCaptures.filter((capture) => capture.approval_state === 'approved' && !capture.stale).length;
    return <main className="studio-production-stage" aria-label="Review stage">
      <StageHeading title="Review" detail="Final approval stays blocked until evidence, observation, audio, captions, brand, CTA, and safe areas are checked." />
      <section className="studio-review-checklist" aria-label="Review checklist">
        <ReviewRow label="Claim to evidence" value={`${evidenceBound}/${sceneCount} scenes`} ready={sceneCount > 0 && evidenceBound === sceneCount} />
        <ReviewRow label="Scene decisions" value={`${accepted}/${sceneCount} accepted`} ready={sceneCount > 0 && accepted === sceneCount} />
        <ReviewRow label="Observed operations" value={`${observedReceipts} successful receipts`} ready={observedReceipts > 0} />
        <ReviewRow label="Authentic screenshots" value={`${approvedScreenshots}/${screenshotCaptures.length} approved`} ready={approvedScreenshots > 0} />
        <ReviewRow label="Final human approval" value="Not recorded" ready={false} />
      </section>
      <section className="studio-screenshot-review" aria-label="Authentic screenshot contact sheet">
        <header><div><span>Visual proof</span><h2>Screenshot contact sheet</h2></div><button type="button" className="studio-button secondary" onClick={() => void loadScreenshotCaptures()}>Refresh</button></header>
        {screenshotError ? <div className="studio-error" role="alert"><span>{screenshotError}</span></div> : null}
        {screenshotCaptures.length ? <div className="studio-screenshot-grid">{screenshotCaptures.map((capture) => <article key={capture.id} className={`studio-screenshot-card ${capture.approval_state}`}>
          <img src={`/api/projects/${projectId}/studio/assets/${capture.asset_id}/thumbnail?sequence_id=${encodeURIComponent(sequenceId)}`} alt={`SAG checkpoint ${capture.checkpoint_id}`} />
          <div className="studio-screenshot-card-body">
            <header><strong>{capture.checkpoint_id}</strong><span>{capture.approval_state}</span></header>
            <p>{capture.observed_labels.join(' · ')}</p>
            <dl><div><dt>Source</dt><dd>{capture.adapter}</dd></div><div><dt>Hash</dt><dd>{capture.asset_sha256.slice(0, 12)}</dd></div><div><dt>Revision</dt><dd>{capture.application_revision}</dd></div></dl>
            {capture.stale ? <span className="studio-screenshot-stale">Stale: revalidate before use</span> : null}
            <div className="studio-screenshot-actions">
              <button type="button" className="studio-button secondary" disabled={screenshotBusy === capture.id || capture.approval_state === 'rejected'} onClick={() => void decideScreenshot(capture.id, 'rejected')}>Reject</button>
              <button type="button" className="studio-button primary" disabled={screenshotBusy === capture.id || capture.stale || capture.approval_state === 'approved'} onClick={() => void decideScreenshot(capture.id, 'approved')}>{screenshotBusy === capture.id ? 'Saving' : 'Approve'}</button>
            </div>
          </div>
        </article>)}</div> : <StageEmpty title="No managed screenshots" detail="Capture authentic SAG checkpoints and bind them to an immutable screenshot recipe." />}
      </section>
    </main>;
  }

  if (stage === 'deliver') {
    const verifiedRenders = [...receipts]
      .filter((receipt) => (
        receipt.command === 'render.verified'
        && receipt.status === 'observed_success'
        && receipt.payload?.artifact_id
        && receipt.payload?.artifact_sha256
        && receipt.payload?.qc_report?.passed === true
      ))
      .sort((left, right) => String(right.created_at).localeCompare(String(left.created_at)));
    const activeRender = receipts.some((receipt) => (
      receipt.command === 'render.verified'
      && ['accepted', 'dispatched', 'rendering', 'artifact_written', 'awaiting_observation'].includes(receipt.status)
    ));
    return <main className="studio-production-stage" aria-label="Deliver stage">
    <StageHeading title="Deliver" detail="Create verified downloadable artifacts. Public publication is outside the current milestone." />
    <section className="studio-stage-metrics" aria-label="Delivery state">
      <div><span>Profiles</span><strong>{delivery.delivery_profiles.length}</strong></div>
      <div><span>Approvals</span><strong>{delivery.release_approvals.length}</strong></div>
      <div><span>Project revision</span><strong>{project.revision}</strong></div>
      <div><span>Publication</span><strong>Disabled</strong></div>
    </section>
    <button className="studio-button primary studio-stage-action" disabled={activeRender} onClick={() => void onRender()}><CirclePlay size={14} />{activeRender ? 'Render in progress' : 'Render verified preview'}</button>
    <section className="studio-deliverables" aria-label="Verified downloads">
      <header><div><span>Observed output</span><h2>Verified downloads</h2></div><strong>{verifiedRenders.length}</strong></header>
      {verifiedRenders.map((receipt) => <article key={receipt.id}>
        <div><strong>Revision {receipt.project_revision}</strong><span>{new Date(receipt.created_at).toLocaleString()}</span></div>
        <code>{String(receipt.payload?.artifact_sha256).slice(0, 24)}</code>
        <VerifiedDownloadLinks projectId={projectId} sequenceId={sequenceId} receipt={receipt} />
      </article>)}
      {verifiedRenders.length === 0 ? <StageEmpty title="No verified render" detail="Start a render. Downloads unlock only after independent observation and QC pass." /> : null}
    </section>
  </main>;
  }

  return null;
}

function SourceToShortsStage({
  intakeStage, production, project, suggestions, onOpenEdit, onProductionUpdate,
}: {
  intakeStage: IntakeStage; production: ProductionSession; project: Project; suggestions: any[];
  onOpenEdit: () => void; onProductionUpdate: (patch: Record<string, unknown>) => Promise<void>;
}) {
  const sourceAssets = project.assets.filter((asset) => asset.kind === 'video');
  const ranked = [...suggestions].sort((a, b) => Number(b.evidence?.clip_quality_score?.total ?? b.confidence ?? 0) - Number(a.evidence?.clip_quality_score?.total ?? a.confidence ?? 0));
  if (intakeStage === 'source') return <main className="studio-production-stage" aria-label="Source stage">
    <StageHeading title="Source" detail="Choose observed workspace media. The engine pins source and proxy hashes before analysis." />
    {sourceAssets.length ? <section className="studio-variant-list">{sourceAssets.map((asset) => <article className="studio-stage-card" key={asset.id}><code>{asset.id}</code><strong>{asset.name}</strong><p>{asset.intake_status === 'observed_valid' ? 'Observed and ready for analysis' : 'Media validation required'}</p></article>)}</section> : <StageEmpty title="No source video" detail="Import an observed-valid video asset before running shorts analysis." />}
  </main>;
  if (intakeStage === 'analysis') return <main className="studio-production-stage" aria-label="Analysis stage">
    <StageHeading title="Analysis" detail="Transcription, boundaries, subjects, and crop trajectories are immutable for each source and settings hash." />
    <section className="studio-stage-metrics"><div><span>Revision</span><strong>{production.active_analysis_revision_id ?? 'Not selected'}</strong></div><div><span>Providers</span><strong>Local first</strong></div><div><span>Coordinates</span><strong>Normalized</strong></div><div><span>Fallback</span><strong>Centered / manual</strong></div></section>
  </main>;
  if (intakeStage === 'ranked_clips') return <main className="studio-production-stage" aria-label="Ranked clips stage">
    <StageHeading title="Ranked clips" detail="Clip Quality Score explains hook, flow, value, delivery, visual evidence, and boundary quality." />
    {ranked.length ? <section className="studio-scene-board">{ranked.map((candidate) => <button type="button" className="studio-stage-card text-left" key={candidate.id} aria-pressed={production.focused_candidate_id === candidate.id} onClick={() => void onProductionUpdate({ focused_candidate_id: candidate.id, active_analysis_revision_id: candidate.evidence?.analysis_revision_id ?? null })}><header><code>{candidate.id}</code><span>{Number(candidate.evidence?.clip_quality_score?.total ?? candidate.confidence * 100).toFixed(1)}</span></header><strong>{candidate.reason}</strong><p>{candidate.evidence?.text ?? 'Transcript excerpt unavailable'}</p></button>)}</section> : <StageEmpty title="No ranked clips" detail="Run source analysis to create evidence-backed clip candidates." />}
  </main>;
  return <main className="studio-production-stage" aria-label="Reframe stage">
    <StageHeading title="Reframe" detail="Review normalized subject tracks, stable split layouts, and visible low-confidence fallbacks before editing." />
    <section className="studio-stage-metrics"><div><span>Candidate</span><strong>{production.focused_candidate_id ?? 'Not selected'}</strong></div><div><span>Target</span><strong>9:16</strong></div><div><span>Strategy</span><strong>Provider neutral</strong></div><div><span>Manual override</span><strong>Available</strong></div></section>
    <button className="studio-button primary studio-stage-action" onClick={onOpenEdit}><Scissors size={14} />Open canonical edit</button>
  </main>;
}

function StageHeading({ title, detail }: { title: string; detail: string }) {
  return <header className="studio-stage-heading"><div><span>Production stage</span><h1>{title}</h1></div><p>{detail}</p></header>;
}

function StageEmpty({ title, detail }: { title: string; detail: string }) {
  return <section className="studio-stage-empty"><Film size={22} /><strong>{title}</strong><p>{detail}</p></section>;
}

function ReviewRow({ label, value, ready }: { label: string; value: string; ready: boolean }) {
  return <div className={ready ? 'ready' : ''}><span>{ready ? <ShieldCheck size={15} /> : <Square size={15} />}{label}</span><strong>{value}</strong></div>;
}

class SpatialErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed
      ? <div className="studio-spatial-fallback" role="alert"><Box size={24} /><strong>3D view unavailable</strong><span>Use the semantic hierarchy to continue.</span></div>
      : this.props.children;
  }
}

function SpatialWorkspace({
  snapshot, depth, selectedId, selectedEntity, show3d, paused, connection,
  onSelect, onToggle3d, onTogglePause, onOpenGovernance,
}: {
  snapshot: SpatialSnapshot;
  depth: Exclude<StudioDepth, 'edit'>;
  selectedId: string | null;
  selectedEntity: SpatialEntity | null;
  show3d: boolean;
  paused: boolean;
  connection: RuntimeConnection;
  onSelect: (id: string) => void;
  onToggle3d: () => void;
  onTogglePause: () => void;
  onOpenGovernance: () => void;
}) {
  const byId = useMemo(() => new Map(snapshot.entities.map((entity) => [entity.id, entity])), [snapshot.entities]);
  const breadcrumbs = useMemo(() => {
    const result: SpatialEntity[] = [];
    let current = selectedEntity;
    while (current) {
      result.unshift(current);
      current = current.parent_id ? byId.get(current.parent_id) ?? null : null;
    }
    return result;
  }, [selectedEntity, byId]);
  const selectedRelationships = useMemo(
    () => selectedEntity ? snapshot.edges.filter((edge) => edge.source === selectedEntity.id || edge.target === selectedEntity.id) : [],
    [selectedEntity, snapshot.edges],
  );
  const webglAvailable = typeof window !== 'undefined' && 'WebGLRenderingContext' in window;

  return <main className="studio-spatial-workspace" aria-label={`${depth} spatial workspace`} data-sag-entity-id="viewport:spatial-workspace" data-sag-action-ids="spatial.reset_view">
    <div className="studio-spatial-toolbar">
      <nav className="studio-breadcrumbs" aria-label="Semantic hierarchy">
        {(breadcrumbs.length ? breadcrumbs : snapshot.entities.slice(0, 3)).map((entity, index) => <span key={entity.id}>
          {index ? <span aria-hidden="true">/</span> : null}
          <button onClick={() => onSelect(entity.id)}>{entity.label}</button>
        </span>)}
      </nav>
      <div className="studio-spatial-controls">
        <RuntimeState connection={connection} />
        <button className="studio-button secondary" onClick={onTogglePause} aria-pressed={paused}>
          <EyeOff size={14} />{paused ? 'Resume Codex view' : 'Pause Codex view'}
        </button>
        <button className="studio-button secondary" onClick={onToggle3d} disabled={!webglAvailable} aria-pressed={show3d}>
          <Box size={14} />{show3d ? 'Show tree' : 'Open 3D'}
        </button>
      </div>
    </div>

    <section className="studio-semantic-explorer" aria-label="Semantic explorer">
      <PanelHeading icon={<Layers3 size={15} />} title="Hierarchy" />
      <HierarchyTree entities={snapshot.entities} selectedId={selectedId} onSelect={onSelect} />
    </section>

    <section className="studio-spatial-view" aria-label={`${depth} projection`}>
      {show3d && webglAvailable ? <SpatialErrorBoundary>
        <SpatialCanvas
          entities={snapshot.entities}
          edges={snapshot.edges}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      </SpatialErrorBoundary> : <div className="studio-spatial-summary">
        <div>
          <strong>{depth === 'context' ? 'Focused causal neighborhood' : 'Production lifecycle'}</strong>
          <span>{snapshot.entities.length} entities and {snapshot.edges.length} relationships</span>
        </div>
        <HierarchyTree entities={snapshot.entities} selectedId={selectedId} onSelect={onSelect} compact />
      </div>}
      {snapshot.truncation.truncated ? <div className="studio-spatial-truncation" role="status">
        Bounded view: {snapshot.truncation.omitted_entities} entities and {snapshot.truncation.omitted_edges} relationships collapsed.
      </div> : null}
    </section>

    <aside className="studio-spatial-inspector" aria-label="Semantic inspector">
      <PanelHeading icon={<SlidersHorizontal size={15} />} title="Inspector" action={<button className="studio-icon-button compact" onClick={onOpenGovernance} aria-label="Open governance"><Activity size={14} /></button>} />
      {selectedEntity ? <div className="studio-entity-inspector">
        <div><span>Identity</span><strong>{selectedEntity.label}</strong><code>{selectedEntity.id}</code></div>
        <dl>
          <div><dt>Kind</dt><dd>{selectedEntity.kind}</dd></div>
          <div><dt>Layer</dt><dd>{selectedEntity.semantic_layer}</dd></div>
          <div><dt>Revision</dt><dd>{selectedEntity.revision}</dd></div>
          <div><dt>Parent</dt><dd>{selectedEntity.parent_id ? byId.get(selectedEntity.parent_id)?.label ?? selectedEntity.parent_id : 'Root'}</dd></div>
        </dl>
        <section><h3>State</h3><pre>{JSON.stringify(selectedEntity.state, null, 2)}</pre></section>
        <section><h3>Metadata</h3><pre>{JSON.stringify(selectedEntity.metadata, null, 2)}</pre></section>
        <section><h3>Relationships</h3>{selectedRelationships.length
          ? <ul>{selectedRelationships.map((edge) => <li key={edge.id}>
            {edge.relationship_kind}: {byId.get(edge.source)?.label ?? edge.source} to {byId.get(edge.target)?.label ?? edge.target}
          </li>)}</ul>
          : <p>No projected relationships.</p>}</section>
        <section><h3>Available actions</h3>{selectedEntity.eligible_action_ids.length
          ? <ul>{selectedEntity.eligible_action_ids.map((action) => <li key={action}>{action}</li>)}</ul>
          : <p>No actions are eligible for this entity.</p>}</section>
      </div> : <EmptyState icon={<Box size={20} />} title="Nothing selected" detail="Choose an entity from the semantic hierarchy." />}
    </aside>
  </main>;
}

function HierarchyTree({
  entities, selectedId, onSelect, compact = false,
}: {
  entities: SpatialEntity[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  compact?: boolean;
}) {
  const [collapsed, setCollapsed] = useState(new Set<string>());
  const children = useMemo(() => {
    const map = new Map<string | null, SpatialEntity[]>();
    for (const entity of entities) {
      const parent = entity.parent_id && entities.some((candidate) => candidate.id === entity.parent_id) ? entity.parent_id : null;
      map.set(parent, [...(map.get(parent) ?? []), entity]);
    }
    for (const entries of map.values()) entries.sort((left, right) => left.position.z - right.position.z || left.position.y - right.position.y || left.label.localeCompare(right.label));
    return map;
  }, [entities]);

  const visible = useMemo(() => {
    const result: Array<{ entity: SpatialEntity; level: number; hasChildren: boolean }> = [];
    function visit(parent: string | null, level: number) {
      for (const entity of children.get(parent) ?? []) {
        const hasChildren = Boolean(children.get(entity.id)?.length);
        result.push({ entity, level, hasChildren });
        if (!collapsed.has(entity.id)) visit(entity.id, level + 1);
      }
    }
    visit(null, 1);
    return compact ? result.filter((entry) => entry.level > 3).slice(0, 80) : result;
  }, [children, collapsed, compact]);

  function moveFocus(event: React.KeyboardEvent<HTMLButtonElement>, direction: number) {
    const buttons = Array.from(event.currentTarget.closest('[role="tree"]')?.querySelectorAll<HTMLButtonElement>('[role="treeitem"]') ?? []);
    const index = buttons.indexOf(event.currentTarget);
    buttons[Math.max(0, Math.min(buttons.length - 1, index + direction))]?.focus();
  }

  return <div className={`studio-hierarchy-tree ${compact ? 'compact' : ''}`} role="tree" aria-label={compact ? 'Projected entities' : 'Production hierarchy'}>
    {visible.map(({ entity, level, hasChildren }) => <button
      key={entity.id}
      role="treeitem"
      data-entity-id={entity.id}
      data-sag-entity-id={entity.id}
      data-sag-action-ids={entity.eligible_action_ids.join(',')}
      aria-level={level}
      aria-selected={entity.id === selectedId}
      aria-expanded={hasChildren ? !collapsed.has(entity.id) : undefined}
      aria-label={`${entity.label}. ${entity.kind}. ${entity.semantic_layer} layer. ${entity.parent_id ? `Parent ${entities.find((candidate) => candidate.id === entity.parent_id)?.label ?? entity.parent_id}.` : 'Root entity.'}`}
      className={entity.id === selectedId ? 'selected' : ''}
      style={{ paddingInlineStart: `${8 + (level - 1) * 14}px` }}
      onClick={() => onSelect(entity.id)}
      onDoubleClick={() => hasChildren && setCollapsed((current) => {
        const next = new Set(current); if (next.has(entity.id)) next.delete(entity.id); else next.add(entity.id); return next;
      })}
      onKeyDown={(event) => {
        if (event.key === 'ArrowDown') { event.preventDefault(); moveFocus(event, 1); }
        if (event.key === 'ArrowUp') { event.preventDefault(); moveFocus(event, -1); }
        if (event.key === 'ArrowLeft' && hasChildren) setCollapsed((current) => new Set(current).add(entity.id));
        if (event.key === 'ArrowRight' && hasChildren) setCollapsed((current) => { const next = new Set(current); next.delete(entity.id); return next; });
      }}
    >
      <span className="studio-tree-kind">{entity.kind}</span>
      <span>{entity.label}</span>
      <small>{entity.semantic_layer}</small>
    </button>)}
  </div>;
}

function CaptureControl({ projectId, sequenceId, onComplete }: { projectId: string; sequenceId: string; onComplete: () => Promise<void> }) {
  const [mode, setMode] = useState<'screen' | 'camera' | 'microphone' | 'screen_camera'>('screen');
  const [cameraFacing, setCameraFacing] = useState<'user' | 'environment'>('environment');
  const [phase, setPhase] = useState<'idle' | 'requesting' | 'recording' | 'stopping' | 'importing' | 'error'>('idle');
  const [message, setMessage] = useState('Capture starts only after your browser permission.');
  const [recoverable, setRecoverable] = useState<CompletedCapture[]>([]);
  const [previewStream, setPreviewStream] = useState<MediaStream | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const recorders = useRef<Array<{
    recorder: MediaRecorder; name: string; stream: MediaStream;
    spool: CaptureSpool; writeQueue: Promise<void>;
  }>>([]);
  const previewRef = useRef<HTMLVideoElement>(null);
  const startedAt = useRef(0);
  const limitTimer = useRef<number | null>(null);
  const stopping = useRef(false);
  const recording = phase === 'recording';
  const captureBusy = phase === 'requesting' || phase === 'stopping' || phase === 'importing';

  async function recorderFor(stream: MediaStream, name: string, includesVideo: boolean) {
    const mimeType = preferredCaptureMimeType(includesVideo);
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const spool = await createCaptureSpool(name, recorder.mimeType || (includesVideo ? 'video/webm' : 'audio/webm'));
    const entry = { recorder, name, stream, spool, writeQueue: Promise.resolve() };
    recorder.ondataavailable = (event) => {
      if (!event.data.size) return;
      entry.writeQueue = entry.writeQueue.then(() => entry.spool.append(event.data)).catch((cause) => {
        setMessage(cause instanceof Error ? cause.message : 'Capture spool failed.');
        void stop();
      });
    };
    recorder.start(1000);
    recorders.current.push(entry);
    stream.getTracks().forEach((track) => track.addEventListener('ended', () => {
      if (!stopping.current && recorders.current.includes(entry)) void stop();
    }, { once: true }));
  }

  async function start() {
    if (!window.isSecureContext) {
      setPhase('error');
      setMessage('Camera capture requires HTTPS or 127.0.0.1. Open this Studio from a secure origin.');
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setPhase('error');
      setMessage('Browser capture is unavailable. Use the system recorder, then import the saved file.');
      return;
    }
    try {
      setPhase('requesting');
      setMessage('Waiting for browser permission.');
      recorders.current = [];
      if (mode === 'screen' || mode === 'screen_camera') {
        if (!navigator.mediaDevices.getDisplayMedia) {
          setPhase('error');
          setMessage('Screen capture is unavailable here. Use the Android system recorder, then import the file.');
          return;
        }
        const screen = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
        await recorderFor(screen, 'screen', true);
        if (mode === 'screen') setPreviewStream(screen);
      }
      if (mode === 'camera' || mode === 'screen_camera') {
        const camera = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: cameraFacing },
            width: { ideal: 1920 }, height: { ideal: 1080 },
            frameRate: { ideal: 30, max: 30 },
          },
          audio: mode === 'camera' ? { echoCancellation: true, noiseSuppression: true } : false,
        });
        await recorderFor(camera, 'camera', true);
        setPreviewStream(camera);
      }
      if (mode === 'microphone') await recorderFor(await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      }), 'microphone', false);
      startedAt.current = Date.now();
      setElapsedSeconds(0);
      setPhase('recording');
      setMessage(recorders.current.every((entry) => entry.spool.persistent)
        ? 'Recording to recoverable device storage. Stop to import managed tracks.'
        : 'Recording with a bounded memory fallback. Stop to import managed tracks.');
      limitTimer.current = window.setTimeout(() => { void stop(); }, 10 * 60 * 1000);
    } catch (cause) {
      recorders.current.forEach((entry) => entry.stream.getTracks().forEach((track) => track.stop()));
      recorders.current = [];
      setPreviewStream(null);
      setPhase('error');
      setMessage(cause instanceof Error ? cause.message : 'Capture permission was not granted.');
    }
  }

  async function stop() {
    if (stopping.current || !recorders.current.length) return;
    stopping.current = true;
    setPhase('stopping');
    if (limitTimer.current) window.clearTimeout(limitTimer.current);
    try {
      const activeRecorders = recorders.current;
      recorders.current = [];
      const completed = await Promise.all(activeRecorders.map((entry) => new Promise<CompletedCapture>((resolve, reject) => {
        const finish = () => { void entry.writeQueue.then(() => entry.spool.finish()).then(resolve, reject); };
        entry.recorder.onstop = finish;
        if (entry.recorder.state === 'inactive') finish();
        else entry.recorder.stop();
        entry.stream.getTracks().forEach((track) => track.stop());
      })));
      setPreviewStream(null);
      setPhase('importing');
      setMessage('Importing captured tracks.');
      for (const entry of completed) {
        if (!entry.blob.size) continue;
        const form = new FormData();
        form.set('file', new File([entry.blob], entry.fileName, { type: entry.blob.type || 'video/webm' }));
        const response = await fetch(`/api/projects/${projectId}/assets/upload?sequence_id=${encodeURIComponent(sequenceId)}`, { method: 'POST', body: form });
        if (!response.ok) throw new Error((await response.json()).message ?? 'Captured track import failed');
        await entry.cleanup();
      }
      await onComplete();
      setPhase('idle');
      setMessage(`Capture imported. ${Math.max(1, Math.round((Date.now() - startedAt.current) / 1000))} seconds recorded.`);
    } catch (cause) {
      setPhase('error');
      setMessage(cause instanceof Error ? cause.message : 'Capture import failed.');
    } finally {
      recorders.current = [];
      setPreviewStream(null);
      stopping.current = false;
    }
  }

  useEffect(() => {
    void recoverCaptureSpools().then(setRecoverable).catch(() => undefined);
    return () => {
      if (limitTimer.current) window.clearTimeout(limitTimer.current);
      recorders.current.forEach((entry) => entry.stream.getTracks().forEach((track) => track.stop()));
    };
  }, []);

  useEffect(() => {
    if (!previewRef.current) return;
    previewRef.current.srcObject = previewStream;
    if (previewStream) void previewRef.current.play().catch(() => undefined);
  }, [previewStream]);

  useEffect(() => {
    if (!recording) return;
    const timer = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - startedAt.current) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [recording]);

  async function recover(entry: CompletedCapture) {
    setPhase('importing');
    setMessage('Importing recovered capture.');
    const form = new FormData();
    form.set('file', new File([entry.blob], entry.fileName, { type: entry.blob.type || 'video/webm' }));
    const response = await fetch(`/api/projects/${projectId}/assets/upload?sequence_id=${encodeURIComponent(sequenceId)}`, { method: 'POST', body: form });
    if (!response.ok) {
      setPhase('error');
      setMessage('Recovered capture import failed. The device copy was kept.');
      return;
    }
    await entry.cleanup();
    setRecoverable((current) => current.filter((candidate) => candidate.fileName !== entry.fileName));
    await onComplete();
    setPhase('idle');
    setMessage('Recovered capture imported.');
  }

  return <div className="studio-capture">
    <label htmlFor="capture-mode">Capture source</label>
    <select id="capture-mode" value={mode} disabled={recording || captureBusy} onChange={(event) => setMode(event.target.value as typeof mode)}>
      <option value="screen">Screen and system audio</option><option value="camera">Camera and microphone</option>
      <option value="microphone">Microphone</option><option value="screen_camera">Screen plus camera</option>
    </select>
    {(mode === 'camera' || mode === 'screen_camera') ? <>
      <label htmlFor="capture-facing">Camera</label>
      <select id="capture-facing" value={cameraFacing} disabled={recording || captureBusy} onChange={(event) => setCameraFacing(event.target.value as typeof cameraFacing)}>
        <option value="environment">Back camera</option><option value="user">Front camera</option>
      </select>
    </> : null}
    {previewStream ? <div className="studio-capture-preview">
      <video ref={previewRef} muted autoPlay playsInline aria-label={mode === 'screen' ? 'Live screen preview' : 'Live camera preview'} />
      <div><span>{phase === 'recording' ? 'Recording' : 'Preview'}</span><time>{formatCaptureDuration(elapsedSeconds)}</time></div>
    </div> : null}
    <button className={`studio-button ${recording ? 'danger' : 'primary'}`} disabled={captureBusy} onClick={() => void (recording ? stop() : start())}>
      {phase === 'requesting' ? <><LoaderCircle className="animate-spin" size={13} />Permission</> :
        phase === 'stopping' ? <><LoaderCircle className="animate-spin" size={13} />Finalizing</> :
          phase === 'importing' ? <><LoaderCircle className="animate-spin" size={13} />Importing</> :
            recording ? <><Square size={13} />Stop capture</> : <><Camera size={13} />Start capture</>}
    </button>
    {recoverable.map((entry) => <button key={entry.fileName} className="studio-button secondary" onClick={() => void recover(entry)}>
      <Upload size={13} />Recover interrupted capture
    </button>)}
    <p role="status">{message}</p>
  </div>;
}

function preferredCaptureMimeType(includesVideo: boolean): string {
  if (typeof MediaRecorder.isTypeSupported !== 'function') return '';
  const candidates = includesVideo
    ? ['video/webm;codecs=vp8,opus', 'video/webm', 'video/mp4;codecs=avc1,mp4a.40.2', 'video/mp4']
    : ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];
  return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate)) ?? '';
}

function formatCaptureDuration(value: number): string {
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
}

function PanelHeading({ icon, title, action }: { icon: React.ReactNode; title: string; action?: React.ReactNode }) {
  return <div className="studio-panel-heading"><div className="flex items-center gap-2">{icon}<h2>{title}</h2></div>{action}</div>;
}

function EmptyState({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return <div className="studio-empty">{icon}<strong>{title}</strong><span>{detail}</span></div>;
}

function TrackIcon({ kind }: { kind: string }) {
  if (kind === 'audio') return <Volume2 size={13} />;
  if (kind === 'caption') return <Captions size={13} />;
  if (kind === 'overlay') return <Layers3 size={13} />;
  return <Film size={13} />;
}

function Inspector({ item, disabled, onCommand, onDelete }: {
  item: Item; disabled: boolean;
  onCommand: (name: string, arguments_: Record<string, unknown>) => Promise<any>;
  onDelete: () => Promise<void>;
}) {
  const [gain, setGain] = useState(item.gain_db ?? 0);
  useEffect(() => setGain(item.gain_db ?? 0), [item.id, item.gain_db]);
  function submitTitle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const data = new FormData(event.currentTarget);
    void onCommand('timeline.set_title', { item_id: item.id, text: String(data.get('text') ?? '') });
  }
  return <div className="space-y-5" data-sag-entity={['video', 'image'].includes(item.kind) ? 'timeline.item:selected' : undefined}
    data-sag-item-id={item.id}>
    <div><div className="font-mono text-[9px] text-ink-3">{item.kind.toUpperCase()}</div><h3 className="mt-1 text-sm font-medium text-ink-0">{item.name}</h3><div className="mt-1 font-mono text-[10px] text-ink-2">{timecode(item.start_ticks)} / {timecode(item.duration_ticks)}</div></div>
    {item.kind === 'title' ? <form onSubmit={submitTitle} className="studio-field"><label htmlFor="title-text">Text</label><textarea id="title-text" name="text" defaultValue={item.text ?? ''} maxLength={500} /><button className="studio-button secondary" disabled={disabled}>Apply title</button></form> : null}
    {['video', 'image'].includes(item.kind) ? <>
      <div className="grid grid-cols-2 gap-2">
        <NumberField label="Position X" value={item.x ?? 0} onCommit={(value) => onCommand('timeline.set_clip_transform', { item_id: item.id, x: value })} />
        <NumberField label="Position Y" value={item.y ?? 0} onCommit={(value) => onCommand('timeline.set_clip_transform', { item_id: item.id, y: value })} />
        <NumberField label="Scale" value={item.scale ?? 1} step="0.05" onCommit={(value) => onCommand('timeline.set_clip_transform', { item_id: item.id, scale: value })} />
        <NumberField label="Opacity" value={item.opacity ?? 1} step="0.05" onCommit={(value) => onCommand('timeline.set_clip_transform', { item_id: item.id, opacity: value })} />
      </div>
      <div className="studio-field"><label htmlFor="fit-mode">Fit</label><select id="fit-mode" value={item.fit_mode ?? 'fit'} onChange={(event) => void onCommand('timeline.set_clip_transform', { item_id: item.id, fit_mode: event.target.value })}><option value="fit">Fit</option><option value="fill">Fill</option><option value="stretch">Stretch</option></select></div>
    </> : null}
    {['video', 'audio'].includes(item.kind) ? <div className="studio-field"><label htmlFor="gain">Audio gain <span>{gain.toFixed(1)} dB</span></label><input id="gain" type="range" min="-60" max="24" step="0.5" value={gain} onChange={(event) => setGain(Number(event.target.value))} onPointerUp={() => void onCommand('timeline.set_audio_gain', { item_id: item.id, gain_db: gain, muted: item.muted ?? false })} /></div> : null}
    {item.kind === 'caption' ? <div className="grid grid-cols-2 gap-2"><button className="studio-button secondary" onClick={() => void onCommand('timeline.set_caption_style', { item_id: item.id, preset: 'bold_pop' })}>Bold pop</button><button className="studio-button secondary" onClick={() => void onCommand('timeline.set_caption_style', { item_id: item.id, preset: 'clean' })}>Clean</button></div> : null}
    <button className="studio-button danger w-full" onClick={() => void onDelete()} disabled={disabled}><Trash2 size={14} />Delete item</button>
  </div>;
}

function NumberField({ label, value, step = '1', onCommit }: { label: string; value: number; step?: string; onCommit: (value: number) => Promise<any> }) {
  return <div className="studio-field"><label>{label}</label><input type="number" step={step} defaultValue={value} onBlur={(event) => {
    const next = Number(event.target.value); if (Number.isFinite(next) && next !== value) void onCommit(next);
  }} /></div>;
}

function ActivityDrawer({
  receipts, context, delivery, projectId, sequenceId, onClose,
}: {
  receipts: Receipt[];
  context: any;
  delivery: { delivery_profiles?: Array<Record<string, any>>; release_approvals?: Array<Record<string, any> & { attempts?: Array<Record<string, any>> }> };
  projectId: string;
  sequenceId: string;
  onClose: () => void;
}) {
  const observed = receipts.filter((receipt) => ['observed_success', 'committed'].includes(receipt.status));
  const failed = receipts.filter((receipt) => ['observed_failure', 'execution_failed', 'denied'].includes(receipt.status));
  const latestObserved = [...observed].sort((left, right) => String(right.created_at).localeCompare(String(left.created_at)))[0];
  const verification = latestObserved?.payload?.verification ?? latestObserved?.payload?.observation ?? {};
  const verifiedHash = String(
    latestObserved?.payload?.artifact_sha256 ?? verification?.sha256 ?? verification?.artifact_sha256 ?? '',
  );
  const latestVerifiedRender = [...receipts]
    .filter((receipt) => (
      receipt.command === 'render.verified'
      && receipt.status === 'observed_success'
      && receipt.payload?.artifact_id
      && receipt.payload?.artifact_sha256
      && receipt.payload?.qc_report?.passed === true
    ))
    .sort((left, right) => String(right.created_at).localeCompare(String(left.created_at)))[0];
  return <aside className="studio-activity" aria-label="Governance and receipts" data-sag-entity-id="viewport:governance" data-sag-action-ids="spatial.frame_entity">
    <div className="studio-panel-heading"><div className="flex items-center gap-2"><Activity size={16} /><h2>Governance</h2></div><button className="studio-icon-button" onClick={onClose} aria-label="Close governance"><X size={16} /></button></div>
    <div className="border-b border-border-base p-4 text-[11px] text-ink-1">
      <div className="flex items-center justify-between"><span>Codex authority</span><strong className="text-ink-0">Sequence scoped</strong></div>
      <div className="mt-2 font-mono text-[9px] leading-5 text-ink-3">{(context?.authority?.scopes ?? []).join(' / ') || 'Browser authority'}</div>
    </div>
    <div className="studio-governance-delivery">
      <h3>Delivery profiles</h3>
      {(delivery?.delivery_profiles ?? []).map((profile) => <div key={String(profile.id)}>
        <strong>{String(profile.destination)}</strong>
        <span>{String(profile.width)}×{String(profile.height)} / {String(profile.aspect_ratio)}</span>
      </div>)}
      {(delivery?.delivery_profiles ?? []).length === 0 ? <p>No delivery profile is configured.</p> : null}
      <h3>Release approvals</h3>
      {(delivery?.release_approvals ?? []).map((approval) => <div key={String(approval.id)}>
        <strong>{String(approval.state).toLowerCase()}</strong>
        <span>Revision {String(approval.project_revision)} / {(approval.attempts ?? []).length} attempts</span>
      </div>)}
      {(delivery?.release_approvals ?? []).length === 0 ? <p>No release approval has been issued.</p> : null}
    </div>
    <section className="studio-verification-console" aria-label="Verification console">
      <header><ShieldCheck size={14} /><strong>Verification console</strong><span>{failed.length ? `${failed.length} failed` : 'no failures'}</span></header>
      <dl>
        <div><dt>Observed receipts</dt><dd>{observed.length}/{receipts.length}</dd></div>
        <div><dt>Current revision</dt><dd>{latestObserved?.project_revision ?? 'none'}</dd></div>
        <div><dt>Latest receipt</dt><dd><code>{latestObserved?.id ?? 'none'}</code></dd></div>
        <div><dt>Artifact hash</dt><dd><code>{verifiedHash ? verifiedHash.slice(0, 18) : 'not present'}</code></dd></div>
      </dl>
      <p>{latestObserved ? `${latestObserved.command} is ${latestObserved.status.replaceAll('_', ' ')}.` : 'No observed receipt is available yet.'}</p>
      {latestVerifiedRender ? <VerifiedDownloadLinks projectId={projectId} sequenceId={sequenceId} receipt={latestVerifiedRender} /> : null}
    </section>
    <div className="studio-activity-list">
      {receipts.map((receipt) => <details key={receipt.id} className="studio-receipt">
        <summary><span className={`receipt-status ${receipt.status}`}>{receipt.status.replaceAll('_', ' ')}</span><span className="truncate">{receipt.command}</span><ChevronDown size={14} /></summary>
        <div className="space-y-2"><div>Revision {receipt.project_revision} by {receipt.actor}</div><div className="font-mono text-[9px] text-ink-3">{receipt.id}</div><pre>{JSON.stringify(receipt.payload?.verification ?? receipt.payload?.observation ?? {}, null, 2)}</pre></div>
      </details>)}
      {receipts.length === 0 ? <EmptyState icon={<Activity size={20} />} title="No activity yet" detail="Committed edits and observed effects appear here." /> : null}
    </div>
  </aside>;
}
