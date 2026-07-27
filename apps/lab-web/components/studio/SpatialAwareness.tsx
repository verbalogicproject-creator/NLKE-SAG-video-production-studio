'use client';

import { Grid3X3, ScanLine, X } from 'lucide-react';
import { CSSProperties, useCallback, useEffect, useRef, useState } from 'react';

type StudioDepth = 'edit' | 'context' | 'system';

type AuthorityEntity = {
  id: string;
  eligible_action_ids?: string[];
};

type AuthoritySnapshot = {
  canonical_revision: number;
  runtime_cursor: number;
  projection_hash: string;
  entities: AuthorityEntity[];
};

export type AdaptiveGrid = {
  coordinate_space: 'normalized_0_1';
  origin: 'top_left';
  columns: number;
  rows: number;
  target_cell_css_px: number;
  cell_width_css_px: number;
  cell_height_css_px: number;
};

export type SpatialRegionBinding = {
  binding_id: string;
  entity_id: string;
  role: string;
  label: string;
  rect: { x: number; y: number; width: number; height: number };
  cells: string[];
  visible: boolean;
  occluded: boolean;
  eligible_action_ids: string[];
  source: 'dom';
  confidence: number;
  protected: boolean;
  evidence_refs: string[];
};

export type SpatialFrame = {
  frame_id: string;
  schema_version: 'sag-spatial-frame/1.0';
  canonical_revision: number;
  projection_hash: string;
  runtime_cursor: number;
  active_depth: StudioDepth;
  viewport: {
    width_css_px: number;
    height_css_px: number;
    device_pixel_ratio: number;
    scroll_x_css_px: number;
    scroll_y_css_px: number;
  };
  grid: AdaptiveGrid;
  bindings: SpatialRegionBinding[];
  truncated_bindings: number;
  redaction_state: 'metadata_only';
  generated_at?: string;
};

function identifier(prefix: string) {
  const value = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().replaceAll('-', '')
    : `${Date.now()}${Math.random().toString(16).slice(2)}`;
  return `${prefix}_${value}`;
}

function gridFor(width: number, height: number): AdaptiveGrid {
  let columns = Math.max(4, Math.min(16, Math.round(width / 80)));
  let rows = Math.max(6, Math.min(24, Math.round(height / 80)));
  while (columns > 4 && width / columns < 44) columns -= 1;
  while (rows > 6 && height / rows < 44) rows -= 1;
  return {
    coordinate_space: 'normalized_0_1', origin: 'top_left', columns, rows,
    target_cell_css_px: 80, cell_width_css_px: width / columns, cell_height_css_px: height / rows,
  };
}

function occupiedCells(
  rect: SpatialRegionBinding['rect'], grid: AdaptiveGrid,
) {
  const firstColumn = Math.max(0, Math.floor(rect.x * grid.columns));
  const lastColumn = Math.min(grid.columns - 1, Math.ceil((rect.x + rect.width) * grid.columns) - 1);
  const firstRow = Math.max(0, Math.floor(rect.y * grid.rows));
  const lastRow = Math.min(grid.rows - 1, Math.ceil((rect.y + rect.height) * grid.rows) - 1);
  const cells: string[] = [];
  for (let row = firstRow; row <= lastRow && cells.length < 24; row += 1) {
    for (let column = firstColumn; column <= lastColumn && cells.length < 24; column += 1) {
      cells.push(`${String.fromCharCode(65 + column)}${row + 1}`);
    }
  }
  return cells;
}

function collectBindings(
  root: HTMLElement, snapshot: AuthoritySnapshot, grid: AdaptiveGrid, width: number, height: number,
) {
  const authority = new Map(snapshot.entities.map((entity) => [entity.id, new Set(entity.eligible_action_ids ?? [])]));
  const candidates = Array.from(root.querySelectorAll<HTMLElement>('[data-sag-entity-id]'))
    .filter((element) => element.dataset.sagIgnore !== 'true')
    .map((element, sourceIndex) => {
      const bounds = element.getBoundingClientRect();
      const left = Math.max(0, bounds.left);
      const top = Math.max(0, bounds.top);
      const right = Math.min(width, bounds.right);
      const bottom = Math.min(height, bounds.bottom);
      const entityId = element.dataset.sagEntityId ?? '';
      const visible = right > left && bottom > top && getComputedStyle(element).visibility !== 'hidden';
      const requestedActions = (element.dataset.sagActionIds ?? '').split(',').map((value) => value.trim()).filter(Boolean);
      const allowed = authority.get(entityId);
      const eligibleActions = allowed
        ? requestedActions.filter((action) => allowed.has(action))
        : requestedActions;
      const rect = {
        x: left / width, y: top / height,
        width: Math.max(1 / width, (right - left) / width),
        height: Math.max(1 / height, (bottom - top) / height),
      };
      const label = (element.getAttribute('aria-label') || element.textContent || entityId)
        .replace(/\s+/g, ' ').trim().slice(0, 160);
      const role = element.getAttribute('role') || element.tagName.toLowerCase();
      const selected = element.getAttribute('aria-selected') === 'true' || element.getAttribute('aria-pressed') === 'true';
      const canonical = authority.has(entityId);
      return {
        priority: selected ? 0 : entityId.startsWith('viewport:') ? 1 : canonical ? 2 : 3,
        sourceIndex,
        binding: {
          binding_id: element.dataset.sagBindingId || `binding_${sourceIndex}_${entityId.replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 80)}`,
          entity_id: entityId, role, label, rect, cells: occupiedCells(rect, grid), visible,
          occluded: false, eligible_action_ids: eligibleActions, source: 'dom' as const,
          confidence: 1, protected: element.dataset.sagProtected === 'true', evidence_refs: [],
        },
      };
    })
    .filter((entry) => entry.binding.entity_id && entry.binding.visible)
    .sort((left, right) => left.priority - right.priority || left.sourceIndex - right.sourceIndex);
  const bindings = candidates.slice(0, 24).map((entry) => entry.binding);
  return { bindings, truncated: Math.max(0, candidates.length - bindings.length) };
}

export function useSpatialAwareness({
  projectId, sequenceId, revision, depth, triggerKey,
}: {
  projectId: string;
  sequenceId: string;
  revision: number;
  depth: StudioDepth;
  triggerKey: string;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const latestFrameRef = useRef<SpatialFrame | null>(null);
  const currentState = useRef({ revision, depth });
  currentState.current = { revision, depth };
  const [frame, setFrame] = useState<SpatialFrame | null>(null);
  const [status, setStatus] = useState<'idle' | 'declaring' | 'declared' | 'failed'>('idle');

  const declareFrameNow = useCallback(async () => {
    const root = rootRef.current;
    if (!root || document.visibilityState === 'hidden') return null;
    setStatus('declaring');
    const snapshotResponse = await fetch(
      `/api/projects/${projectId}/studio/spatial?depth=system&hop_count=6&sequence_id=${encodeURIComponent(sequenceId)}`, { cache: 'no-store' },
    );
    if (!snapshotResponse.ok) throw new Error('Spatial authority snapshot failed');
    const snapshot = await snapshotResponse.json() as AuthoritySnapshot;
    if (snapshot.canonical_revision !== currentState.current.revision) {
      throw new Error('Spatial authority revision is stale');
    }
    const width = Math.max(1, document.documentElement.clientWidth);
    const height = Math.max(1, document.documentElement.clientHeight);
    const grid = gridFor(width, height);
    const collected = collectBindings(root, snapshot, grid, width, height);
    const request = {
      frame_id: identifier('frame'), schema_version: 'sag-spatial-frame/1.0',
      canonical_revision: snapshot.canonical_revision, projection_hash: snapshot.projection_hash,
      runtime_cursor: snapshot.runtime_cursor, active_depth: currentState.current.depth,
      viewport: {
        width_css_px: width, height_css_px: height, device_pixel_ratio: window.devicePixelRatio || 1,
        scroll_x_css_px: Math.max(0, window.scrollX), scroll_y_css_px: Math.max(0, window.scrollY),
      },
      grid, bindings: collected.bindings, truncated_bindings: collected.truncated,
      redaction_state: 'metadata_only',
    };
    const response = await fetch(`/api/projects/${projectId}/studio/spatial/frames?sequence_id=${encodeURIComponent(sequenceId)}`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(request),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.message ?? body.error ?? body.detail ?? 'Spatial frame declaration failed');
    }
    const next = await response.json() as SpatialFrame;
    latestFrameRef.current = next;
    setFrame(next);
    setStatus('declared');
    return next;
  }, [projectId, sequenceId]);

  useEffect(() => {
    let cancelled = false;
    let timer = window.setTimeout(() => {
      if (!cancelled) void declareFrameNow().catch(() => { if (!cancelled) setStatus('failed'); });
    }, 120);
    const observer = new ResizeObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        if (!cancelled) void declareFrameNow().catch(() => { if (!cancelled) setStatus('failed'); });
      }, 180);
    });
    if (rootRef.current) observer.observe(rootRef.current);
    return () => { cancelled = true; window.clearTimeout(timer); observer.disconnect(); };
  }, [declareFrameNow, revision, depth, triggerKey]);

  return { rootRef, frame, latestFrameRef, status, declareFrameNow };
}

export function SpatialAwarenessOverlay({
  frame, status,
}: {
  frame: SpatialFrame | null;
  status: 'idle' | 'declaring' | 'declared' | 'failed';
}) {
  const [open, setOpen] = useState(false);
  const gridStyle: CSSProperties | undefined = frame ? {
    gridTemplateColumns: `repeat(${frame.grid.columns}, minmax(0, 1fr))`,
    gridTemplateRows: `repeat(${frame.grid.rows}, minmax(0, 1fr))`,
  } : undefined;
  return <div className={`studio-spatial-awareness ${open ? 'open' : ''}`} data-sag-ignore="true">
    <button
      className="studio-spatial-map-toggle"
      aria-label={open ? 'Hide spatial map' : 'Show spatial map'}
      aria-pressed={open}
      onClick={() => setOpen((value) => !value)}
    >{open ? <X size={17} /> : <Grid3X3 size={17} />}<span>Spatial map</span></button>
    {open ? <>
      {frame ? <div className="studio-coordinate-grid" style={gridStyle} aria-hidden="true">
        {Array.from({ length: frame.grid.rows * frame.grid.columns }, (_, index) => {
          const column = index % frame.grid.columns;
          const row = Math.floor(index / frame.grid.columns);
          return <span key={`${column}:${row}`}>{String.fromCharCode(65 + column)}{row + 1}</span>;
        })}
      </div> : null}
      <aside className="studio-spatial-map-panel" aria-label="Declared spatial regions">
        <header><ScanLine size={15} /><strong>Declared regions</strong><span className={status}>{status}</span></header>
        {frame ? <>
          <p>{frame.grid.columns} columns, {frame.grid.rows} rows, {frame.bindings.length} bindings</p>
          <div role="list">
            {frame.bindings.map((binding) => <div key={binding.binding_id} role="listitem">
              <span>{binding.label || binding.entity_id}</span>
              <code>{binding.cells.slice(0, 4).join(' ')}</code>
            </div>)}
          </div>
        </> : <p>{status === 'failed' ? 'Frame declaration failed.' : 'Waiting for the first declared frame.'}</p>}
      </aside>
    </> : null}
  </div>;
}
