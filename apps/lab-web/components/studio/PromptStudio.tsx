'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Braces, Check, ChevronDown, CircleAlert, FilePenLine, GitCompare, History,
  RotateCcw, Save, ShieldCheck, Workflow,
} from 'lucide-react';
import type {
  CreativeBrief, DirectorInput, PromptModulePreview, PromptStudioPreview, Storyboard,
} from '@/lib/engine';

export type PromptVersion = {
  id: string; moduleId: string; label: string; content: string; contentSha256: string; savedAt: string;
};

type EditablePromptField = 'creative_instruction' | 'omni_prompt' | 'veo_prompt' | 'music_prompt' | 'narration_guidance';

function localModules(input: DirectorInput, brief?: CreativeBrief): PromptModulePreview[] {
  const entries: Array<[string, string, EditablePromptField, string, string, string]> = [
    ['direction.instruction', 'Creative direction', 'creative_instruction', 'Director', 'gemini-omni-flash-preview', input.creative_instructions],
  ];
  if (brief) entries.push(
    ['generation.omni_continuity', 'Omni continuity', 'omni_prompt', 'Scene video', 'gemini-omni-flash-preview', brief.omni_prompt],
    ['generation.veo_continuity', 'Veo continuity', 'veo_prompt', 'Controlled scene video', 'veo-3.1-generate-preview', brief.veo_prompt],
    ['generation.music', 'Music direction', 'music_prompt', 'Music', 'lyria-3-clip-preview', brief.music_prompt],
    ['planning.narration_guidance', 'Narration guidance', 'narration_guidance', 'Narration planning', 'gemini-3.1-flash-tts-preview', brief.narration_guidance],
  );
  return entries.map(([id, label, field, component, model, content]) => ({
    id, label, stage: field === 'creative_instruction' ? 'direction' : field === 'narration_guidance' ? 'planning' : 'generation',
    component, model, content, content_sha256: '', estimated_tokens: Math.ceil(content.length / 4),
    dispatch: field === 'creative_instruction' || field === 'narration_guidance' ? 'planning_context' : 'provider_input',
    editable_field: field, consumers: [], warnings: [],
  }));
}

export function PromptStudio({
  projectId, sequenceId, input, brief, storyboard, versions, onInput, onBrief, onSaveVersion,
}: {
  projectId: string; sequenceId: string; input: DirectorInput; brief?: CreativeBrief; storyboard?: Storyboard;
  versions: PromptVersion[];
  onInput: <K extends keyof DirectorInput>(key: K, value: DirectorInput[K]) => void;
  onBrief: <K extends keyof CreativeBrief>(key: K, value: CreativeBrief[K]) => void;
  onSaveVersion: (version: PromptVersion) => void;
}) {
  const [preview, setPreview] = useState<PromptStudioPreview>();
  const [selectedId, setSelectedId] = useState('direction.instruction');
  const [sceneId, setSceneId] = useState(storyboard?.scenes[0]?.id ?? '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (storyboard?.scenes.length && !storyboard.scenes.some((scene) => scene.id === sceneId)) {
      setSceneId(storyboard.scenes[0]!.id);
    }
  }, [storyboard, sceneId]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const response = await fetch(`/api/projects/${projectId}/repo-to-video/prompts/preview`, {
          method: 'POST', headers: { 'content-type': 'application/json' }, signal: controller.signal,
          body: JSON.stringify({
            sequence_id: sequenceId, creative_instruction: input.creative_instructions,
            creative_brief: brief, storyboard,
            aspect_ratio: input.target_platform === 'youtube_16_9' ? '16:9' : '9:16',
            active_scene_id: sceneId || undefined,
          }),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.message ?? body.detail ?? 'Prompt preview failed');
        setPreview(body as PromptStudioPreview);
        setError('');
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Prompt preview failed');
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 240);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [brief, input.creative_instructions, input.target_platform, projectId, sceneId, sequenceId, storyboard]);

  const modules = preview?.modules.length ? preview.modules : localModules(input, brief);
  const selected = modules.find((module) => module.id === selectedId) ?? modules[0];
  const model = preview?.models.find((entry) => entry.id === selected?.model);
  const previous = useMemo(
    () => versions.filter((version) => version.moduleId === selected?.id).at(-1),
    [selected?.id, versions],
  );

  function edit(field: string | null | undefined, value: string) {
    if (field === 'creative_instruction') onInput('creative_instructions', value);
    if (field === 'omni_prompt' || field === 'veo_prompt' || field === 'music_prompt' || field === 'narration_guidance') {
      onBrief(field, value);
    }
  }

  function restore() {
    if (selected?.editable_field && previous) edit(selected.editable_field, previous.content);
  }

  if (!selected) return <div className="prompt-studio-empty">Generate a creative brief to initialize prompt modules.</div>;

  const editable = Boolean(selected.editable_field);
  const hasChanged = Boolean(previous && previous.content !== selected.content);
  return <div className="prompt-studio" data-sag-entity-id="viewport:prompt-studio">
    <section className="prompt-studio-status" aria-label="Resolved prompt state">
      <div><Workflow size={15} /><div><strong>Prompting Studio</strong><span>Versioned instruction layer</span></div></div>
      <div className="prompt-studio-revision">
        <span className={`director-state ${preview?.dispatch_allowed ? 'success' : ''}`}>{preview?.dispatch_allowed ? 'generation ready' : 'proposal'}</span>
        <code title={preview?.resolved_prompt_revision}>{preview?.resolved_prompt_revision.slice(0, 12) || 'resolving'}</code>
      </div>
    </section>

    <section className="prompt-route-map" aria-label="Prompt routing topology">
      <div className="prompt-route-source">
        <span className="available">Direction</span><span className={brief ? 'available' : ''}>Brief</span><span className={storyboard ? 'available' : ''}>Storyboard</span>
      </div>
      <div className="prompt-route-branches">
        <div className={storyboard ? 'available' : ''}><span>Scene prompts</span><strong>Omni / Veo</strong></div>
        <div className={brief ? 'available' : ''}><span>Music direction</span><strong>Lyria</strong></div>
        <div className={storyboard ? 'available' : ''}><span>Narration script</span><strong>Gemini TTS</strong></div>
      </div>
      <div className="prompt-route-output"><span className={storyboard ? 'available' : ''}>Observed assets</span><span>Timeline</span></div>
    </section>

    {error ? <div className="director-warning" role="alert"><CircleAlert size={14} /><div><strong>Engine preview unavailable</strong><p>{error}</p><p>Editable local drafts remain available. Generation is still engine validated.</p></div></div> : null}
    {preview?.warnings.length ? <div className="prompt-studio-warnings" role="status">{preview.warnings.map((warning) => <span key={warning}><CircleAlert size={12} />{warning}</span>)}</div> : null}

    <div className="prompt-workbench">
      <nav aria-label="Prompt modules" className="prompt-module-list">
        {modules.map((module) => <button key={module.id} className={module.id === selected.id ? 'active' : ''} onClick={() => setSelectedId(module.id)}>
          <span>{module.label}</span><small>{module.stage} / {module.dispatch.replaceAll('_', ' ')}</small>
        </button>)}
      </nav>

      <section className="prompt-editor" aria-label={`${selected.label} editor`}>
        <header><div><FilePenLine size={14} /><div><strong>{selected.label}</strong><span>{selected.component}</span></div></div>{loading ? <span>resolving</span> : <span>{selected.estimated_tokens} est. tokens</span>}</header>
        {selected.id === 'generation.resolved_scene' || selected.id === 'generation.veo_negative' ? <label className="prompt-scene-selector"><span>Preview scene</span><select value={sceneId} onChange={(event) => setSceneId(event.target.value)}>{storyboard?.scenes.map((scene) => <option key={scene.id} value={scene.id}>{scene.id}</option>)}</select></label> : null}
        <label className="prompt-textarea"><span>{editable ? 'Editable source' : 'Engine-resolved provider input'}</span><textarea readOnly={!editable} value={selected.content} onChange={(event) => edit(selected.editable_field, event.target.value)} /></label>
        <div className="prompt-editor-actions">
          <button className="studio-button secondary" disabled={!editable} onClick={() => onSaveVersion({
            id: crypto.randomUUID(), moduleId: selected.id, label: selected.label, content: selected.content,
            contentSha256: selected.content_sha256, savedAt: new Date().toISOString(),
          })}><Save size={14} />Save draft</button>
          <button className="studio-button secondary" disabled={!editable || !previous} onClick={restore}><RotateCcw size={14} />Restore</button>
          <span className={hasChanged ? 'changed' : ''}><GitCompare size={12} />{previous ? hasChanged ? 'Changed from saved draft' : 'Matches saved draft' : 'No saved draft'}</span>
        </div>
      </section>
    </div>

    <section className="prompt-impact" aria-label="Prompt impact and model capability">
      <header><Braces size={14} /><strong>Binding and impact</strong></header>
      <dl>
        <div><dt>Dispatch</dt><dd>{selected.dispatch.replaceAll('_', ' ')}</dd></div>
        <div><dt>Model</dt><dd>{selected.model ?? 'No direct model'}</dd></div>
        <div><dt>Prompt hash</dt><dd><code>{selected.content_sha256.slice(0, 12) || 'pending'}</code></dd></div>
        <div><dt>Consumers</dt><dd>{selected.consumers.join(', ') || 'Resolved after planning'}</dd></div>
      </dl>
      {model ? <details><summary>Model capabilities <ChevronDown size={13} /></summary><p>{model.notes}</p><div className="prompt-capabilities">{model.capabilities.map((capability) => <span key={capability}>{capability.replaceAll('_', ' ')}</span>)}</div></details> : null}
      {selected.warnings.map((warning) => <p className="prompt-module-warning" key={warning}><CircleAlert size={12} />{warning}</p>)}
      <p className="prompt-authority"><ShieldCheck size={13} /><span>Draft edits affect proposals. The engine binds the resolved prompt revision to generation; canonical edits and release still require their existing gates.</span></p>
      {previous ? <p className="prompt-version-note"><History size={12} />Last saved {new Date(previous.savedAt).toLocaleString()}</p> : <p className="prompt-version-note"><Check size={12} />Prompt text is excluded from runtime telemetry.</p>}
    </section>
  </div>;
}
