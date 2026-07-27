'use client';

import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, ArrowDown, ArrowUp, Check, ChevronDown, CircleAlert, Clapperboard, FileCode2,
  GitBranch, GitCompare, Grid3X3, Lock, Mic2, Play, Plus, RefreshCw, Save, Sparkles, Trash2,
  Unlock, Volume2, X,
} from 'lucide-react';
import type {
  CreativeBrief, DirectorInput, EngineReceipt, GenerationOperation, RepositoryEvidence, Storyboard,
  StoryboardScene, ProductionSession,
} from '@/lib/engine';
import { PromptStudio, type PromptVersion } from './PromptStudio';

type DirectorTab = 'direction' | 'brief' | 'prompts' | 'storyboard' | 'queue';
type EvidenceState = {
  evidence: RepositoryEvidence; evidence_revision: string;
  redaction: { status: string; bounded: boolean }; factuality: { status: string };
};
type BriefVersion = { id: string; savedAt: string; brief: CreativeBrief };
type QueueEntry = {
  id: string; receiptId: string; kind: string; sceneId?: string; provider: string; model: string;
  operationName: string; state: string; assetId?: string; errorCode?: string; errorDetail?: string;
  startedAt: string;
};
type DirectorSession = {
  input: DirectorInput; evidence?: EvidenceState; brief?: CreativeBrief; briefVersions: BriefVersion[];
  promptVersions: PromptVersion[];
  briefApproved: boolean; storyboard?: Storyboard; storyboardReceipt?: EngineReceipt;
  storyboardApproved: boolean; generationReceiptId?: string; queue: QueueEntry[]; activeTab: DirectorTab;
};

const DEFAULT_INPUT: DirectorInput = {
  repository_url: 'https://github.com/', ref: '',
  creative_instructions: 'Create a factual developer tutorial and promotion short. Show how the repository turns governed media operations into a verifiable edit.',
  audience: 'Developers evaluating open-source video production infrastructure',
  goal: 'Explain the repository clearly and earn qualified repository traffic', duration_seconds: 60,
  visual_style: 'Precise developer documentary with restrained cinematic inserts', target_platform: 'youtube_shorts',
  brand_kit: '', reference_assets: [],
};

function sessionFromProduction(production: ProductionSession): DirectorSession {
  const evidence = production.repository_evidence && production.evidence_revision ? {
    evidence: production.repository_evidence,
    evidence_revision: production.evidence_revision,
    redaction: { status: 'passed', bounded: true },
    factuality: { status: 'evidence_bound' },
  } : undefined;
  const storyboardReceipt = production.storyboard_proposal_receipt_id ? {
    id: production.storyboard_proposal_receipt_id,
    command: 'media.propose_storyboard', status: production.approved_storyboard_receipt_id ? 'committed' : 'awaiting_user_consent',
    actor: 'engine', project_revision: 1, created_at: production.updated_at,
  } : undefined;
  return {
    input: production.director_input ?? DEFAULT_INPUT,
    evidence,
    brief: production.active_brief ?? undefined,
    briefVersions: production.brief_versions.map((brief, index) => ({
      id: `brief-${index + 1}`, savedAt: production.updated_at, brief,
    })),
    promptVersions: production.prompt_revisions as unknown as PromptVersion[],
    briefApproved: production.brief_approved,
    storyboard: production.active_storyboard ?? undefined,
    storyboardReceipt,
    storyboardApproved: Boolean(production.approved_storyboard_receipt_id),
    generationReceiptId: production.generation_receipt_id ?? undefined,
    queue: production.generation_operations as unknown as QueueEntry[],
    activeTab: production.director_tab,
  };
}

function productionPatch(session: DirectorSession): Record<string, unknown> {
  return {
    director_tab: session.activeTab,
    director_input: session.input,
    repository_evidence: session.evidence?.evidence ?? null,
    evidence_revision: session.evidence?.evidence_revision ?? null,
    active_brief: session.brief ?? null,
    brief_versions: session.briefVersions.map((version) => version.brief),
    brief_approved: session.briefApproved,
    active_storyboard: session.storyboard ?? null,
    storyboard_proposal_receipt_id: session.storyboardReceipt?.id ?? null,
    approved_storyboard_receipt_id: session.storyboardApproved ? session.storyboardReceipt?.id ?? null : null,
    prompt_revisions: session.promptVersions,
    generation_receipt_id: session.generationReceiptId ?? null,
    operation_ids: session.queue.map((entry) => entry.operationName),
    generation_operations: session.queue,
  };
}

function operationState(operation: GenerationOperation): string {
  if (operation.asset_id) return 'inserted';
  if (operation.state === 'completed') return 'provider completed';
  if (operation.state === 'failed') return 'failed';
  if (operation.state === 'running') return 'running';
  return 'accepted';
}

function queueFromOperations(receiptId: string, operations: GenerationOperation[], previous: QueueEntry[] = []): QueueEntry[] {
  const existing = new Map(previous.map((entry) => [entry.id, entry]));
  const generated = operations.map((operation) => {
    const id = `${receiptId}:${operation.operation_name}`;
    return {
      id, receiptId, kind: operation.kind, sceneId: operation.scene_id, provider: operation.provider ?? 'google',
      model: operation.model, operationName: operation.operation_name, state: operationState(operation),
      assetId: operation.asset_id, errorCode: operation.error_code, errorDetail: operation.error_detail,
      startedAt: existing.get(id)?.startedAt ?? new Date().toISOString(),
    };
  });
  return [...previous.filter((entry) => entry.receiptId !== receiptId), ...generated];
}

function proposalQueueEntry(kind: 'brief' | 'storyboard', receipt: EngineReceipt): QueueEntry {
  return {
    id: `${receipt.id}:${kind}`, receiptId: receipt.id, kind, provider: 'google', model: 'gemini-omni-flash-preview',
    operationName: receipt.command, state: 'awaiting approval', startedAt: receipt.created_at ?? new Date().toISOString(),
  };
}

function normalizeSceneStarts(scenes: StoryboardScene[]): StoryboardScene[] {
  let start = 0;
  return scenes.map((scene) => {
    const next = { ...scene, start_seconds: Number(start.toFixed(2)) };
    start += scene.duration_seconds;
    return next;
  });
}

function storyboardProblems(storyboard: Storyboard | undefined, evidenceRevision: string | undefined, duration: number): string[] {
  if (!storyboard) return ['Generate a storyboard before approval.'];
  const problems: string[] = [];
  if (!evidenceRevision || storyboard.evidence_revision !== evidenceRevision) problems.push('Evidence revision does not match the inspected repository.');
  let previousEnd = 0;
  for (const scene of storyboard.scenes) {
    if (scene.start_seconds < previousEnd - 0.01) problems.push(`${scene.id} overlaps the previous scene.`);
    if (!scene.evidence_refs.length) problems.push(`${scene.id} has narration without an evidence reference.`);
    for (const region of scene.spatial_layout?.regions ?? []) {
      if (region.x + region.width > 1.000001 || region.y + region.height > 1.000001) {
        problems.push(`${scene.id} region ${region.id} exceeds the normalized frame.`);
      }
      if (region.purpose === 'authentic_reference' && !region.source_asset_id) {
        problems.push(`${scene.id} authentic region ${region.id} needs a source asset.`);
      }
    }
    previousEnd = scene.start_seconds + scene.duration_seconds;
  }
  if (previousEnd > duration + 0.01) problems.push(`Storyboard ends at ${previousEnd.toFixed(1)}s, beyond the requested ${duration}s.`);
  return problems;
}

async function responseJson(response: Response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message ?? body.detail ?? body.error ?? 'Director operation failed');
  return body;
}

export function DirectorPanel({
  projectId, sequenceId, projectRevision, production, onProductionUpdate, onClose, onProjectRefresh,
}: {
  projectId: string; sequenceId: string; projectRevision: number; production: ProductionSession;
  onProductionUpdate: (patch: Record<string, unknown>) => Promise<void>;
  onClose: () => void; onProjectRefresh: () => Promise<void>;
}) {
  const [session, setSession] = useState<DirectorSession>(() => sessionFromProduction(production));
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [compareOpen, setCompareOpen] = useState(false);
  const [now, setNow] = useState(Date.now());
  const persistedFingerprint = useRef(JSON.stringify(productionPatch(session)));
  const pendingPatch = useRef<Record<string, unknown> | null>(null);

  useEffect(() => {
    const patch = productionPatch(session);
    const fingerprint = JSON.stringify(patch);
    if (fingerprint === persistedFingerprint.current) return;
    pendingPatch.current = patch;
    const timer = window.setTimeout(() => {
      persistedFingerprint.current = fingerprint;
      void onProductionUpdate(patch).catch((cause) => {
        persistedFingerprint.current = '';
        setError(cause instanceof Error ? cause.message : 'Production context could not be saved');
      }).finally(() => { if (pendingPatch.current === patch) pendingPatch.current = null; });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [session, onProductionUpdate]);

  useEffect(() => () => {
    const patch = pendingPatch.current;
    if (patch) void onProductionUpdate(patch);
  }, [onProductionUpdate]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const requestBody = useMemo(() => ({ ...session.input, sequence_id: sequenceId }), [session.input, sequenceId]);
  const problems = useMemo(
    () => storyboardProblems(session.storyboard, session.evidence?.evidence_revision, session.input.duration_seconds),
    [session.storyboard, session.evidence?.evidence_revision, session.input.duration_seconds],
  );
  const queueActive = Boolean(session.generationReceiptId) && session.queue.some(
    (entry) => entry.receiptId === session.generationReceiptId && !['inserted', 'failed'].includes(entry.state),
  );

  async function post(path: string, payload: Record<string, unknown>, human = false) {
    const confirmation = human ? String(payload.confirmation_id ?? '') : '';
    return responseJson(await fetch(`/api/projects/${projectId}/repo-to-video/${path}`, {
      method: 'POST', headers: { 'content-type': 'application/json', ...(human ? { 'x-sag-human-confirmation': confirmation } : {}) },
      body: JSON.stringify(payload),
    }));
  }

  async function inspect() {
    setBusy('evidence'); setError('');
    try {
      const body = await post('evidence', requestBody);
      setSession((current) => ({ ...current, evidence: body, brief: undefined, briefApproved: false, storyboard: undefined, storyboardApproved: false }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Repository inspection failed'); }
    finally { setBusy(''); }
  }

  async function generateBrief() {
    setBusy('brief'); setError('');
    try {
      const body = await post('director/brief', requestBody);
      setSession((current) => ({
        ...current, brief: body.brief, briefApproved: false, storyboard: undefined, storyboardApproved: false, activeTab: 'brief',
        briefVersions: current.brief ? [...current.briefVersions, { id: crypto.randomUUID(), savedAt: new Date().toISOString(), brief: current.brief }] : current.briefVersions,
        queue: [...current.queue.filter((entry) => !['brief', 'storyboard'].includes(entry.kind)), proposalQueueEntry('brief', body.receipt)],
      }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Creative brief generation failed'); }
    finally { setBusy(''); }
  }

  async function generateStoryboard() {
    setBusy('storyboard'); setError('');
    try {
      const body = await post('storyboard', requestBody);
      setSession((current) => {
        const locked = new Map(current.storyboard?.scenes.filter((scene) => scene.locked).map((scene) => [scene.id, scene]) ?? []);
        const scenes = normalizeSceneStarts((body.storyboard as Storyboard).scenes.map((scene) => locked.get(scene.id) ?? scene));
        return {
          ...current, storyboard: { ...body.storyboard, scenes }, storyboardReceipt: body.receipt,
          storyboardApproved: false, activeTab: 'storyboard',
          queue: [...current.queue.filter((entry) => entry.kind !== 'storyboard'), proposalQueueEntry('storyboard', body.receipt)],
        };
      });
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Storyboard generation failed'); }
    finally { setBusy(''); }
  }

  async function approveStoryboard() {
    if (!session.storyboardReceipt || problems.length) return;
    setBusy('approve'); setError('');
    try {
      const confirmation_id = crypto.randomUUID();
      await post('storyboard/commit', {
        sequence_id: sequenceId, receipt_id: session.storyboardReceipt.id,
        expected_revision: projectRevision, confirmation_id, storyboard: session.storyboard,
      }, true);
      setSession((current) => ({
        ...current, storyboardApproved: true,
        queue: current.queue.map((entry) => entry.receiptId === current.storyboardReceipt?.id ? { ...entry, state: 'accepted' } : entry),
      }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Storyboard approval failed'); }
    finally { setBusy(''); }
  }

  async function startGeneration() {
    if (!session.storyboardApproved || !session.storyboard || !session.brief) return;
    setBusy('generation'); setError('');
    try {
      const confirmation_id = crypto.randomUUID();
      const body = await post('generate', {
        sequence_id: sequenceId, storyboard: session.storyboard, creative_brief: session.brief,
        storyboard_receipt_id: session.storyboardReceipt?.id,
        expected_revision: projectRevision, confirmation_id,
        aspect_ratio: session.input.target_platform === 'youtube_16_9' ? '16:9' : '9:16',
      }, true);
      setSession((current) => ({
        ...current, generationReceiptId: body.receipt.id,
        queue: queueFromOperations(body.receipt.id, body.operations, current.queue), activeTab: 'queue',
      }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Generation could not start'); }
    finally { setBusy(''); }
  }

  async function pollGeneration() {
    const receiptId = session.generationReceiptId;
    if (!receiptId) return;
    try {
      const body = await responseJson(await fetch(
        `/api/projects/${projectId}/repo-to-video/generation/${encodeURIComponent(receiptId)}?sequence_id=${encodeURIComponent(sequenceId)}`,
        { cache: 'no-store' },
      ));
      setSession((current) => ({ ...current, queue: queueFromOperations(receiptId, body.operations, current.queue) }));
      if (body.receipt?.status === 'observed_success') await onProjectRefresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Generation polling failed'); }
  }

  useEffect(() => {
    if (!queueActive || !session.generationReceiptId) return;
    const timer = window.setInterval(() => { void pollGeneration(); }, 3000);
    return () => window.clearInterval(timer);
  }, [queueActive, session.generationReceiptId, projectId, sequenceId]);

  function updateInput<K extends keyof DirectorInput>(key: K, value: DirectorInput[K]) {
    setSession((current) => ({ ...current, input: { ...current.input, [key]: value } }));
  }

  function updateBrief<K extends keyof CreativeBrief>(key: K, value: CreativeBrief[K]) {
    setSession((current) => current.brief ? { ...current, brief: { ...current.brief, [key]: value }, briefApproved: false } : current);
  }

  function updateScene(sceneId: string, patch: Partial<StoryboardScene>) {
    setSession((current) => current.storyboard ? {
      ...current, storyboardApproved: false,
      storyboard: { ...current.storyboard, scenes: current.storyboard.scenes.map((scene) => scene.id === sceneId && (!scene.locked || Object.keys(patch).every((key) => key === 'locked')) ? { ...scene, ...patch } : scene) },
    } : current);
  }

  function moveScene(index: number, direction: -1 | 1) {
    setSession((current) => {
      if (!current.storyboard) return current;
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= current.storyboard.scenes.length) return current;
      const scenes = [...current.storyboard.scenes];
      const currentScene = scenes[index]!;
      scenes[index] = scenes[nextIndex]!;
      scenes[nextIndex] = currentScene;
      return { ...current, storyboardApproved: false, storyboard: { ...current.storyboard, scenes: normalizeSceneStarts(scenes) } };
    });
  }

  return <aside className="director-panel" aria-label="Director workspace" data-sag-entity-id="viewport:director" data-sag-action-ids="spatial.frame_entity">
    <header className="director-header">
      <div><Sparkles size={17} /><div><h2>Director</h2><span>Repository to verified timeline</span></div></div>
      <button className="studio-icon-button" onClick={onClose} aria-label="Close Director"><X size={16} /></button>
    </header>

    <div className="director-tabs" role="tablist" aria-label="Director workflow">
      {(['direction', 'brief', 'prompts', 'storyboard', 'queue'] as const).map((tab) => <button
        key={tab} role="tab" aria-selected={session.activeTab === tab} className={session.activeTab === tab ? 'active' : ''}
        onClick={() => setSession((current) => ({ ...current, activeTab: tab }))}
      >{tab === 'direction' ? 'Direction' : tab.charAt(0).toUpperCase() + tab.slice(1)}</button>)}
    </div>

    {error ? <div className="director-error" role="alert"><CircleAlert size={14} /><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error"><X size={14} /></button></div> : null}

    <div className="director-body">
      {session.activeTab === 'direction' ? <DirectionTab
        input={session.input} evidence={session.evidence} busy={busy} onInput={updateInput} onInspect={inspect} onBrief={generateBrief}
      /> : null}
      {session.activeTab === 'brief' ? <BriefTab
        brief={session.brief} versions={session.briefVersions} approved={session.briefApproved} evidenceRevision={session.evidence?.evidence_revision}
        compareOpen={compareOpen} busy={busy} onChange={updateBrief} onCompare={() => setCompareOpen((value) => !value)}
        onSave={() => session.brief && setSession((current) => ({ ...current, briefVersions: [...current.briefVersions, { id: crypto.randomUUID(), savedAt: new Date().toISOString(), brief: session.brief! }] }))}
        onApprove={() => setSession((current) => ({
          ...current, briefApproved: true,
          queue: current.queue.map((entry) => entry.kind === 'brief' && entry.state === 'awaiting approval' ? { ...entry, state: 'accepted' } : entry),
        }))} onRegenerate={generateBrief}
        onStoryboard={() => void generateStoryboard()}
      /> : null}
      {session.activeTab === 'prompts' ? <PromptStudio
        projectId={projectId} sequenceId={sequenceId} input={session.input} brief={session.brief}
        storyboard={session.storyboard} versions={session.promptVersions} onInput={updateInput} onBrief={updateBrief}
        onSaveVersion={(version) => setSession((current) => ({
          ...current, promptVersions: [...current.promptVersions, version].slice(-40),
        }))}
      /> : null}
      {session.activeTab === 'storyboard' ? <StoryboardTab
        storyboard={session.storyboard} problems={problems} approved={session.storyboardApproved} briefApproved={session.briefApproved}
        busy={busy} onChange={updateScene} onMove={moveScene} onRegenerate={generateStoryboard}
        onApprove={approveStoryboard} onGenerate={startGeneration}
      /> : null}
      {session.activeTab === 'queue' ? <QueueTab entries={session.queue} now={now} busy={busy} onPoll={pollGeneration} /> : null}
    </div>
  </aside>;
}

function DirectionTab({ input, evidence, busy, onInput, onInspect, onBrief }: {
  input: DirectorInput; evidence?: EvidenceState; busy: string;
  onInput: <K extends keyof DirectorInput>(key: K, value: DirectorInput[K]) => void;
  onInspect: () => Promise<void>; onBrief: () => Promise<void>;
}) {
  function submit(event: FormEvent) { event.preventDefault(); void onInspect(); }
  return <div className="director-stack">
    <form onSubmit={submit} className="director-form">
      <DirectorField label="Repository URL"><input required type="url" value={input.repository_url} onChange={(event) => onInput('repository_url', event.target.value)} /></DirectorField>
      <div className="director-field-row">
        <DirectorField label="Git ref"><input value={input.ref ?? ''} placeholder="Default branch" onChange={(event) => onInput('ref', event.target.value)} /></DirectorField>
        <DirectorField label="Duration"><select value={input.duration_seconds} onChange={(event) => onInput('duration_seconds', Number(event.target.value))}><option value="30">30 seconds</option><option value="60">60 seconds</option><option value="90">90 seconds</option><option value="120">120 seconds</option></select></DirectorField>
      </div>
      <DirectorField label="Creative direction"><textarea value={input.creative_instructions} onChange={(event) => onInput('creative_instructions', event.target.value)} /></DirectorField>
      <DirectorField label="Audience"><input value={input.audience} onChange={(event) => onInput('audience', event.target.value)} /></DirectorField>
      <DirectorField label="Promotion or tutorial goal"><input value={input.goal} onChange={(event) => onInput('goal', event.target.value)} /></DirectorField>
      <DirectorField label="Visual style"><input value={input.visual_style} onChange={(event) => onInput('visual_style', event.target.value)} /></DirectorField>
      <div className="director-field-row">
        <DirectorField label="Target platform"><select value={input.target_platform} onChange={(event) => onInput('target_platform', event.target.value)}><option value="youtube_shorts">YouTube Shorts 9:16</option><option value="youtube_16_9">YouTube 16:9</option><option value="instagram_reels">Instagram Reels</option><option value="square_1_1">Square 1:1</option></select></DirectorField>
        <DirectorField label="Reference assets"><input value={input.reference_assets.join(', ')} placeholder="HTTPS URLs" onChange={(event) => onInput('reference_assets', event.target.value.split(',').map((value) => value.trim()).filter(Boolean))} /></DirectorField>
      </div>
      <DirectorField label="Brand kit"><textarea className="compact" value={input.brand_kit} placeholder="Voice, colors, logo constraints, CTA" onChange={(event) => onInput('brand_kit', event.target.value)} /></DirectorField>
      <button className="studio-button primary" disabled={Boolean(busy)}><GitBranch size={14} />{busy === 'evidence' ? 'Inspecting repository' : 'Inspect repository'}</button>
    </form>

    <section className="director-routing" aria-label="Model routing">
      <h3>Model routing</h3>
      <dl><div><dt>Omni</dt><dd>Default video generation, planning, and conversational edits</dd></div><div><dt>Veo</dt><dd>Frame control, extensions, and specialized cinematic shots</dd></div><div><dt>Veo Lite</dt><dd>Intentional lower-cost scene previews</dd></div><div><dt>Lyria</dt><dd>Music generation</dd></div><div><dt>Gemini TTS</dt><dd>Narration</dd></div></dl>
    </section>

    {evidence ? <section className="director-evidence" aria-label="Repository evidence">
      <div className="director-section-heading"><div><GitBranch size={15} /><h3>{evidence.evidence.name}</h3></div><code>{evidence.evidence.ref}</code></div>
      <div className="director-status-row"><span className="director-state success"><Check size={12} />Evidence collected</span><span>Revision {evidence.evidence_revision.slice(0, 10)}</span></div>
      <p>{evidence.evidence.description || evidence.evidence.readme.slice(0, 420) || 'No repository summary was available.'}</p>
      <details><summary>README summary <ChevronDown size={13} /></summary><pre>{evidence.evidence.readme.slice(0, 2400)}</pre></details>
      <details><summary>{evidence.evidence.files.length} bounded files <ChevronDown size={13} /></summary><ul>{evidence.evidence.files.slice(0, 80).map((file) => <li key={file}><FileCode2 size={11} />{file}</li>)}</ul></details>
      <div className="director-safety"><span><Check size={12} />Secret redaction: {evidence.redaction.status}</span><span><Check size={12} />Factuality: evidence bound</span><span><Check size={12} />Bounded evidence: {evidence.redaction.bounded ? 'yes' : 'no'}</span></div>
      <button className="studio-button primary" disabled={Boolean(busy)} onClick={() => void onBrief()}><Sparkles size={14} />{busy === 'brief' ? 'Generating brief' : 'Generate creative brief'}</button>
    </section> : null}
  </div>;
}

function BriefTab({ brief, versions, approved, evidenceRevision, compareOpen, busy, onChange, onCompare, onSave, onApprove, onRegenerate, onStoryboard }: {
  brief?: CreativeBrief; versions: BriefVersion[]; approved: boolean; evidenceRevision?: string; compareOpen: boolean; busy: string;
  onChange: <K extends keyof CreativeBrief>(key: K, value: CreativeBrief[K]) => void; onCompare: () => void; onSave: () => void;
  onApprove: () => void; onRegenerate: () => Promise<void>; onStoryboard: () => void;
}) {
  if (!brief) return <DirectorEmpty icon={<Sparkles size={22} />} title="No creative brief" detail="Inspect repository evidence, then generate a factual brief." />;
  const stale = brief.evidence_revision !== evidenceRevision;
  const previous = versions.at(-1)?.brief;
  return <div className="director-stack">
    <div className="director-review-bar"><span className={`director-state ${stale ? 'failure' : 'success'}`}>{stale ? 'Stale evidence revision' : 'Evidence revision matches'}</span><code>{brief.evidence_revision.slice(0, 10)}</code></div>
    {brief.unsupported_claim_warnings.length ? <div className="director-warning"><CircleAlert size={14} /><div><strong>Unsupported claim warnings</strong>{brief.unsupported_claim_warnings.map((warning) => <p key={warning}>{warning}</p>)}</div></div> : null}
    <div className="director-form">
      <DirectorField label="Title"><input value={brief.title} onChange={(event) => onChange('title', event.target.value)} /></DirectorField>
      <DirectorField label="Logline"><textarea className="compact" value={brief.logline} onChange={(event) => onChange('logline', event.target.value)} /></DirectorField>
      <DirectorField label="Audience promise"><textarea className="compact" value={brief.audience_promise} onChange={(event) => onChange('audience_promise', event.target.value)} /></DirectorField>
      <DirectorField label="Tone"><input value={brief.tone} onChange={(event) => onChange('tone', event.target.value)} /></DirectorField>
      <DirectorField label="Visual language"><textarea value={brief.visual_language} onChange={(event) => onChange('visual_language', event.target.value)} /></DirectorField>
      <DirectorField label="Narrative arc"><textarea className="compact" value={brief.narrative_arc.join('\n')} onChange={(event) => onChange('narrative_arc', event.target.value.split('\n').map((value) => value.trim()).filter(Boolean))} /></DirectorField>
      <DirectorField label="Omni prompt"><textarea value={brief.omni_prompt} onChange={(event) => onChange('omni_prompt', event.target.value)} /></DirectorField>
      <DirectorField label="Veo prompt"><textarea value={brief.veo_prompt} onChange={(event) => onChange('veo_prompt', event.target.value)} /></DirectorField>
      <DirectorField label="Music prompt"><textarea className="compact" value={brief.music_prompt} onChange={(event) => onChange('music_prompt', event.target.value)} /></DirectorField>
      <DirectorField label="Narration guidance"><textarea className="compact" value={brief.narration_guidance} onChange={(event) => onChange('narration_guidance', event.target.value)} /></DirectorField>
    </div>
    <div className="director-actions"><button className="studio-button secondary" onClick={onSave}><Save size={14} />Save version</button><button className="studio-button secondary" disabled={!previous} onClick={onCompare}><GitCompare size={14} />Compare</button><button className="studio-button secondary" disabled={Boolean(busy)} onClick={() => void onRegenerate()}><RefreshCw size={14} />Regenerate</button></div>
    {compareOpen && previous ? <section className="director-compare"><h3>Current compared with saved version</h3>{(['title', 'logline', 'audience_promise', 'tone', 'visual_language'] as const).map((key) => <div key={key}><strong>{key.replaceAll('_', ' ')}</strong><span className={brief[key] === previous[key] ? '' : 'changed'}>{brief[key] === previous[key] ? 'Unchanged' : 'Changed'}</span></div>)}</section> : null}
    <div className="director-approval"><div><strong>{approved ? 'Brief approved' : 'Brief is still a proposal'}</strong><span>Approval applies only to this local brief revision.</span></div>{!approved ? <button className="studio-button primary" disabled={stale} onClick={onApprove}><Check size={14} />Approve brief</button> : <button className="studio-button primary" onClick={onStoryboard}><Clapperboard size={14} />Open storyboard review</button>}</div>
  </div>;
}

function StoryboardTab({ storyboard, problems, approved, briefApproved, busy, onChange, onMove, onRegenerate, onApprove, onGenerate }: {
  storyboard?: Storyboard; problems: string[]; approved: boolean; briefApproved: boolean; busy: string;
  onChange: (id: string, patch: Partial<StoryboardScene>) => void; onMove: (index: number, direction: -1 | 1) => void;
  onRegenerate: () => Promise<void>; onApprove: () => Promise<void>; onGenerate: () => Promise<void>;
}) {
  if (!storyboard) return <DirectorEmpty icon={<Clapperboard size={22} />} title="No storyboard" detail="Approve the creative brief, then open storyboard review." />;
  return <div className="director-stack">
    <div className="director-storyboard-title"><div><h3>{storyboard.title}</h3><p>{storyboard.hook}</p></div><button className="studio-button secondary" disabled={Boolean(busy)} onClick={() => void onRegenerate()}><RefreshCw size={14} />Regenerate unlocked</button></div>
    {problems.length ? <div className="director-warning" role="status"><CircleAlert size={14} /><div><strong>Approval blocked</strong>{problems.map((problem) => <p key={problem}>{problem}</p>)}</div></div> : null}
    <div className="director-scenes">
      {storyboard.scenes.map((scene, index) => <article key={scene.id} className={`director-scene ${scene.locked ? 'locked' : ''}`}>
        <header><div><code>{scene.id}</code><span>{scene.start_seconds.toFixed(1)}s to {(scene.start_seconds + scene.duration_seconds).toFixed(1)}s</span></div><div><button onClick={() => onMove(index, -1)} disabled={index === 0 || scene.locked} aria-label={`Move ${scene.id} earlier`}><ArrowUp size={14} /></button><button onClick={() => onMove(index, 1)} disabled={index === storyboard.scenes.length - 1 || scene.locked} aria-label={`Move ${scene.id} later`}><ArrowDown size={14} /></button><button onClick={() => onChange(scene.id, { locked: !scene.locked })} aria-label={scene.locked ? `Unlock ${scene.id}` : `Lock ${scene.id}`}>{scene.locked ? <Unlock size={14} /> : <Lock size={14} />}</button></div></header>
        <div className="director-field-row"><DirectorField label="Duration"><input disabled={scene.locked} type="number" min="0.1" max="60" step="0.1" value={scene.duration_seconds} onChange={(event) => onChange(scene.id, { duration_seconds: Number(event.target.value) })} /></DirectorField><DirectorField label="Generation model"><select disabled={scene.locked} value={scene.generation_model} onChange={(event) => onChange(scene.id, { generation_model: event.target.value })}><option value="gemini-omni-flash-preview">Omni (default)</option><option value="veo-3.1-lite-generate-preview">Veo Lite preview</option><option value="veo-3.1-generate-preview">Veo controlled shot</option><option value="Wan-AI/Wan2.2-TI2V-5B">Wan 2.2 via HF/fal (5s)</option></select></DirectorField></div>
        <DirectorField label="Purpose"><input disabled={scene.locked} value={scene.purpose} onChange={(event) => onChange(scene.id, { purpose: event.target.value })} /></DirectorField>
        <DirectorField label="Narration"><textarea disabled={scene.locked} className="compact" value={scene.narration} onChange={(event) => onChange(scene.id, { narration: event.target.value })} /></DirectorField>
        <DirectorField label="Visual direction"><textarea disabled={scene.locked} value={scene.visual_direction} onChange={(event) => onChange(scene.id, { visual_direction: event.target.value })} /></DirectorField>
        <DirectorField label="Evidence references"><textarea disabled={scene.locked} className="compact" value={scene.evidence_refs.join('\n')} onChange={(event) => onChange(scene.id, { evidence_refs: event.target.value.split('\n').map((value) => value.trim()).filter(Boolean) })} /></DirectorField>
        <SpatialLayoutEditor scene={scene} disabled={Boolean(scene.locked)} onChange={(spatial_layout) => onChange(scene.id, { spatial_layout })} />
      </article>)}
    </div>
    <div className="director-approval"><div><strong>{approved ? 'Storyboard approved' : 'Human consent required'}</strong><span>{approved ? 'Bound to the current project and evidence revisions.' : 'The proposal receipt is awaiting explicit human consent.'}</span></div>{approved ? <button className="studio-button primary" onClick={() => void onGenerate()} disabled={Boolean(busy)}><Play size={14} />Generate assets</button> : <button className="studio-button primary" onClick={() => void onApprove()} disabled={Boolean(busy) || problems.length > 0 || !briefApproved}><Check size={14} />Approve storyboard</button>}</div>
  </div>;
}

function SpatialLayoutEditor({
  scene, disabled, onChange,
}: {
  scene: StoryboardScene;
  disabled: boolean;
  onChange: (layout: NonNullable<StoryboardScene['spatial_layout']>) => void;
}) {
  const layout = scene.spatial_layout;
  if (!layout) return <button className="studio-button secondary director-spatial-add" disabled={disabled} onClick={() => onChange({
    coordinate_space: 'normalized_0_1', columns: 5, rows: 10, regions: [],
  })}><Grid3X3 size={14} />Add spatial contract</button>;
  const activeLayout: NonNullable<StoryboardScene['spatial_layout']> = layout;
  function patchRegion(index: number, patch: Partial<(typeof activeLayout.regions)[number]>) {
    onChange({ ...activeLayout, regions: activeLayout.regions.map((region, regionIndex) => regionIndex === index ? { ...region, ...patch } : region) });
  }
  return <section className="director-spatial-layout" aria-label={`${scene.id} spatial contract`}>
    <header><div><Grid3X3 size={14} /><strong>Spatial contract</strong></div><span>{activeLayout.columns} by {activeLayout.rows} address grid</span></header>
    {activeLayout.regions.map((region, index) => <div className="director-region" key={region.id}>
      <div className="director-region-heading"><input aria-label="Region ID" disabled={disabled} value={region.id} onChange={(event) => patchRegion(index, { id: event.target.value })} /><button disabled={disabled} aria-label={`Remove ${region.id}`} onClick={() => onChange({ ...activeLayout, regions: activeLayout.regions.filter((_, regionIndex) => regionIndex !== index) })}><Trash2 size={13} /></button></div>
      <div className="director-region-routing"><select aria-label="Region purpose" disabled={disabled} value={region.purpose} onChange={(event) => patchRegion(index, { purpose: event.target.value as typeof region.purpose })}><option value="authentic_reference">Authentic reference</option><option value="readable_text">Readable text</option><option value="safe_motion">Safe motion</option><option value="caption_safe">Caption safe</option><option value="cta">CTA</option><option value="protected">Protected</option></select><select aria-label="Region behavior" disabled={disabled} value={region.behavior} onChange={(event) => patchRegion(index, { behavior: event.target.value as typeof region.behavior })}><option value="preserve">Preserve</option><option value="animate">Animate</option><option value="avoid">Avoid</option><option value="replace">Replace</option></select></div>
      <div className="director-region-bounds">{(['x', 'y', 'width', 'height'] as const).map((key) => <label key={key}><span>{key}</span><input aria-label={`Region ${key}`} disabled={disabled} type="number" min="0" max="1" step="0.01" value={region[key]} onChange={(event) => patchRegion(index, { [key]: Number(event.target.value) })} /></label>)}</div>
      {region.purpose === 'authentic_reference' ? <label className="director-region-source"><span>Source asset ID</span><input disabled={disabled} value={region.source_asset_id ?? ''} onChange={(event) => patchRegion(index, { source_asset_id: event.target.value })} /></label> : null}
    </div>)}
    <button className="studio-button secondary director-spatial-add" disabled={disabled || activeLayout.regions.length >= 24} onClick={() => onChange({
      ...activeLayout,
      regions: [...activeLayout.regions, {
        id: `region_${scene.id.replace(/^scene_/, '')}_${activeLayout.regions.length + 1}`,
        purpose: 'safe_motion', x: 0.1, y: 0.1, width: 0.8, height: 0.8,
        behavior: 'animate', evidence_refs: [],
      }],
    })}><Plus size={14} />Add region</button>
  </section>;
}

function QueueTab({ entries, now, busy, onPoll }: { entries: QueueEntry[]; now: number; busy: string; onPoll: () => Promise<void> }) {
  if (!entries.length) return <DirectorEmpty icon={<Activity size={22} />} title="Queue is empty" detail="Approved storyboard generation operations appear here." />;
  const generated = entries.filter((entry) => ['video', 'music', 'narration'].includes(entry.kind));
  const routeSummary = (kind: string) => {
    const matching = generated.filter((entry) => entry.kind === kind);
    const inserted = matching.filter((entry) => entry.state === 'inserted').length;
    const failed = matching.filter((entry) => entry.state === 'failed').length;
    return { count: matching.length, inserted, failed, state: failed ? 'failure' : matching.length && inserted === matching.length ? 'success' : '' };
  };
  const video = routeSummary('video');
  const music = routeSummary('music');
  const narration = routeSummary('narration');
  const inserted = generated.filter((entry) => entry.state === 'inserted').length;
  return <div className="director-stack"><div className="director-queue-heading"><div><h3>Generation operations</h3><p>Provider results are downloaded, observed, verified, then inserted by the engine.</p></div><button className="studio-button secondary" disabled={Boolean(busy)} onClick={() => void onPoll()}><RefreshCw size={14} />Refresh</button></div>
    {generated.length ? <section className="director-production-flow" aria-label="Production routing status">
      <div className={video.state}><Clapperboard size={14} /><span>Scenes</span><strong>{video.inserted}/{video.count}</strong></div>
      <div className={music.state}><Volume2 size={14} /><span>Music</span><strong>{music.inserted}/{music.count}</strong></div>
      <div className={narration.state}><Mic2 size={14} /><span>Narration</span><strong>{narration.inserted}/{narration.count}</strong></div>
      <div className={inserted === generated.length ? 'success' : ''}><Check size={14} /><span>Timeline</span><strong>{inserted}/{generated.length}</strong></div>
    </section> : null}
    <div className="director-queue">{entries.map((entry) => <article key={entry.id}>
    <header><div><strong>{entry.sceneId ?? entry.kind}</strong><span>{entry.kind}</span></div><span className={`director-state ${entry.state === 'failed' ? 'failure' : entry.state === 'inserted' ? 'success' : ''}`}>{entry.state}</span></header>
    <dl><div><dt>Provider</dt><dd>{entry.provider}</dd></div><div><dt>Model</dt><dd>{entry.model}</dd></div><div><dt>Elapsed</dt><dd>{Math.max(0, Math.floor((now - new Date(entry.startedAt).getTime()) / 1000))}s</dd></div><div><dt>Cost / quota</dt><dd>Not reported</dd></div></dl>
    <details><summary>Operation and receipt <ChevronDown size={13} /></summary><code>{entry.operationName}</code><code>{entry.receiptId}</code>{entry.assetId ? <code>Asset {entry.assetId}</code> : null}</details>
    {entry.errorCode || entry.errorDetail ? <div className="director-operation-error"><strong>{entry.errorCode ?? 'provider_failure'}</strong><span>{entry.errorDetail}</span><button className="studio-button secondary" onClick={() => void onPoll()}>Retry observation</button></div> : null}
    {!['brief', 'storyboard'].includes(entry.kind) && !['inserted', 'failed'].includes(entry.state) ? <div className="director-queue-actions"><button className="studio-button secondary" onClick={() => void onPoll()}>Retry status</button><button className="studio-button secondary" disabled title="This provider operation does not expose cancellation.">Cancel unavailable</button></div> : null}
  </article>)}</div></div>;
}

function DirectorField({ label, children }: { label: string; children: ReactNode }) {
  return <label className="director-field"><span>{label}</span>{children}</label>;
}

function DirectorEmpty({ icon, title, detail }: { icon: ReactNode; title: string; detail: string }) {
  return <div className="director-empty">{icon}<strong>{title}</strong><span>{detail}</span></div>;
}
