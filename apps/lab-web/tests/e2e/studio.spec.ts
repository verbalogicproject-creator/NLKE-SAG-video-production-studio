import { expect, test, type Page } from '@playwright/test';

const projectId = process.env.E2E_PROJECT_ID;
const sequenceId = process.env.E2E_SEQUENCE_ID;

function studioPath(): string {
  test.skip(!projectId || !sequenceId, 'E2E_PROJECT_ID and E2E_SEQUENCE_ID identify the seeded acceptance project');
  return `/projects/${projectId}/studio/${sequenceId}`;
}

async function assertNoHorizontalDrift(page: Page) {
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport + 1);
}

test('hydrates the live timecode from a deterministic server snapshot', async ({ page }) => {
  const hydrationErrors: string[] = [];
  page.on('pageerror', (error) => {
    if (/hydration|server rendered html/i.test(error.message)) hydrationErrors.push(error.message);
  });
  await page.goto(studioPath());
  await expect(page.locator('header').first()).toContainText(/\d{2}:\d{2}:\d{2} UTC/);
  await page.waitForTimeout(1100);
  expect(hydrationErrors).toEqual([]);
});

test('records a camera preview and imports the capture through managed media intake', async ({ page }) => {
  await page.addInitScript(() => {
    class MockMediaRecorder {
      static isTypeSupported() { return true; }
      state: RecordingState = 'inactive';
      mimeType: string;
      ondataavailable: ((event: BlobEvent) => unknown) | null = null;
      onstop: ((event: Event) => unknown) | null = null;
      constructor(_stream: MediaStream, options?: MediaRecorderOptions) {
        this.mimeType = options?.mimeType ?? 'video/webm';
      }
      start() { this.state = 'recording'; }
      stop() {
        this.state = 'inactive';
        this.ondataavailable?.({ data: new Blob(['camera-capture'], { type: this.mimeType }) } as BlobEvent);
        queueMicrotask(() => this.onstop?.(new Event('stop')));
      }
    }
    Object.defineProperty(window, 'MediaRecorder', { configurable: true, value: MockMediaRecorder });
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
      getUserMedia: async () => new MediaStream(),
      getDisplayMedia: async () => new MediaStream(),
    } });
    if (navigator.storage) Object.defineProperty(navigator.storage, 'getDirectory', { configurable: true, value: undefined });
  });
  let imports = 0;
  await page.route('**/api/projects/*/assets/upload', async (route) => {
    imports += 1;
    await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ asset: { id: 'capture-e2e' } }) });
  });
  await page.goto(studioPath());
  if ((page.viewportSize()?.width ?? 1000) < 768) await page.getByRole('button', { name: 'Media', exact: true }).click();
  await page.getByRole('button', { name: 'Capture', exact: true }).click();
  await page.getByLabel('Capture source').selectOption('camera');
  await page.getByLabel('Camera').selectOption('environment');
  await page.getByRole('button', { name: 'Start capture' }).click();
  await expect(page.getByLabel('Live camera preview')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stop capture' })).toBeVisible();
  await page.getByRole('button', { name: 'Stop capture' }).click();
  await expect(page.getByRole('status')).toContainText('Capture imported.');
  expect(imports).toBe(1);
  await assertNoHorizontalDrift(page);
});

test('preserves semantic selection across Edit, Context, and System', async ({ page }) => {
  await page.goto(studioPath());
  await expect(page.getByRole('button', { name: 'Edit' })).toBeVisible();
  await page.getByRole('button', { name: 'Context' }).click();
  const treeItem = page.getByRole('treeitem').filter({ hasText: /clip|title|asset/i }).first();
  await treeItem.click();
  const selectedName = (await treeItem.textContent())?.trim();
  await expect(page.getByRole('treeitem', { selected: true }).first()).toContainText(selectedName ?? '');
  await page.getByRole('button', { name: 'System' }).click();
  await expect(page.getByRole('treeitem', { selected: true }).first()).toContainText(selectedName ?? '');
  await page.reload();
  await expect(page.getByRole('button', { name: 'System' })).toHaveAttribute('aria-pressed', 'true');
  await assertNoHorizontalDrift(page);
});

test('semantic hierarchy is keyboard navigable without WebGL', async ({ page }) => {
  await page.addInitScript(() => {
    const prototype = HTMLCanvasElement.prototype as unknown as {
      getContext: (type: string, ...args: unknown[]) => unknown;
    };
    const original = prototype.getContext;
    prototype.getContext = function (type: string, ...args: unknown[]) {
      if (type.startsWith('webgl')) return null;
      return original.call(this, type, ...args);
    };
  });
  await page.goto(studioPath());
  await page.getByRole('button', { name: 'Context' }).click();
  const first = page.getByRole('treeitem').first();
  await first.focus();
  await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('treeitem').nth(1)).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('treeitem').nth(1)).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('tree').first()).toBeVisible();
  await expect(page.getByLabel('Semantic inspector')).toContainText('Parent');
  await expect(page.getByLabel('Semantic inspector')).toContainText('Relationships');
  await expect(page.getByLabel('Semantic inspector')).toContainText('Available actions');
  await assertNoHorizontalDrift(page);
});

test('pause control and responsive targets remain operable', async ({ page }) => {
  await page.goto(studioPath());
  const pause = page.getByRole('button', { name: /Pause Codex|Resume Codex/ });
  await expect(pause).toBeVisible();
  const box = await pause.boundingBox();
  if ((page.viewportSize()?.width ?? 1000) < 768) expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  else expect(box?.height ?? 0).toBeGreaterThanOrEqual(34);
  await pause.click();
  await expect(pause).toHaveAccessibleName(/Resume Codex/);
  await assertNoHorizontalDrift(page);
});

test('declares an adaptive semantic frame and exposes an accessible spatial map', async ({ page }) => {
  const declaration = page.waitForRequest((request) => (
    request.method() === 'POST' && request.url().endsWith('/studio/spatial/frames')
  ));
  await page.goto(studioPath());
  const request = await declaration;
  const frame = request.postDataJSON();
  expect(frame.schema_version).toBe('sag-spatial-frame/1.0');
  expect(frame.redaction_state).toBe('metadata_only');
  expect(frame.raw_screenshot).toBeUndefined();
  expect(frame.grid.columns).toBeGreaterThanOrEqual(4);
  expect(frame.grid.rows).toBeGreaterThanOrEqual(6);
  expect(frame.grid.cell_width_css_px).toBeGreaterThanOrEqual(44);
  expect(frame.grid.cell_height_css_px).toBeGreaterThanOrEqual(44);
  expect(frame.bindings).toEqual(expect.arrayContaining([
    expect.objectContaining({ entity_id: 'viewport:studio', source: 'dom', confidence: 1 }),
    expect.objectContaining({ entity_id: 'viewport:studio-header', source: 'dom', confidence: 1 }),
  ]));

  const toggle = page.getByRole('button', { name: 'Show spatial map' });
  await expect(toggle).toBeVisible();
  const toggleBox = await toggle.boundingBox();
  if ((page.viewportSize()?.width ?? 1000) < 768) expect(toggleBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await toggle.click();
  await expect(page.getByLabel('Declared spatial regions')).toBeVisible();
  await expect(page.getByLabel('Declared spatial regions')).toContainText('bindings');
  await expect(page.locator('.studio-coordinate-grid')).toBeVisible();
  await assertNoHorizontalDrift(page);
});

test('mobile Studio controls, semantic rows, and Director fields stay contained', async ({ page }) => {
  test.skip((page.viewportSize()?.width ?? 1000) >= 768, 'Mobile containment applies below 768px');
  await page.goto(studioPath());

  const header = page.locator('.studio-header');
  await expect(header).toBeVisible();
  expect(await header.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  for (const name of ['Undo', 'Pair Codex', 'Director', 'Render', 'Open governance']) {
    const button = page.getByRole('button', { name, exact: true });
    const box = await button.boundingBox();
    expect(box, `${name} should be visible`).not.toBeNull();
    expect((box?.x ?? -1) + (box?.width ?? 0)).toBeLessThanOrEqual((page.viewportSize()?.width ?? 0) + 1);
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  }

  await page.getByRole('button', { name: 'Context' }).click();
  const controls = page.locator('.studio-spatial-controls');
  expect(await controls.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  const row = page.locator('.studio-hierarchy-tree.compact [role="treeitem"]').first();
  await expect(row).toBeVisible();
  expect(await row.evaluate((element) => {
    const label = element.children.item(1)?.getBoundingClientRect();
    const layer = element.children.item(2)?.getBoundingClientRect();
    return Boolean(label && layer && (label.right <= layer.left || label.bottom <= layer.top));
  })).toBe(true);

  await page.getByRole('button', { name: 'Director', exact: true }).click();
  const director = page.getByLabel('Director workspace');
  const directorBox = await director.boundingBox();
  expect(directorBox?.x ?? -1).toBeGreaterThanOrEqual(0);
  expect(directorBox?.width ?? 0).toBeLessThanOrEqual(page.viewportSize()?.width ?? 0);
  const refBox = await director.getByLabel('Git ref').boundingBox();
  const durationBox = await director.getByLabel('Duration').boundingBox();
  expect(Math.abs((refBox?.y ?? 0) - (durationBox?.y ?? 1))).toBeLessThanOrEqual(1);
  await assertNoHorizontalDrift(page);
});

test('falls back to the semantic hierarchy after WebGL context loss', async ({ page }) => {
  await page.goto(studioPath());
  await page.getByRole('button', { name: 'Context' }).click();
  const open3d = page.getByRole('button', { name: /Open 3D|Show tree/ });
  test.skip(await open3d.isDisabled(), 'WebGL is unavailable in this browser project');
  if (await open3d.getAttribute('aria-pressed') !== 'true') await open3d.click();
  const canvas = page.locator('canvas.studio-spatial-canvas');
  await expect(canvas).toBeVisible();
  await canvas.evaluate((element) => element.dispatchEvent(new Event('webglcontextlost', { cancelable: true })));
  await expect(page.getByRole('alert')).toContainText('3D context lost');
  await expect(page.getByRole('tree').first()).toBeVisible();
});

test('deduplicates directives and acknowledges the exact observed target', async ({ page }) => {
  await page.addInitScript(() => {
    class FakeEventSource extends EventTarget {
      static instance: FakeEventSource | null = null;
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(public url: string) {
        super(); FakeEventSource.instance = this; queueMicrotask(() => this.onopen?.());
      }
      close() {}
    }
    Object.assign(window, { EventSource: FakeEventSource, __sagEventSource: FakeEventSource });
  });
  const acknowledgements: Array<Record<string, unknown>> = [];
  await page.route('**/studio/spatial', async (route) => {
    if (route.request().method() === 'POST') {
      acknowledgements.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    } else await route.continue();
  });
  await page.goto(studioPath());
  await page.getByRole('button', { name: 'Context' }).click();
  const targetItem = page.getByRole('treeitem').filter({ hasText: /clip|title|asset/i }).first();
  const target = await targetItem.getAttribute('aria-label');
  const directiveTarget = await targetItem.getAttribute('data-entity-id');
  expect(directiveTarget).toBeTruthy();
  await page.evaluate(({ directiveTarget }) => {
    const type = (window as unknown as { __sagEventSource: { instance: EventTarget } }).__sagEventSource;
    const event = new MessageEvent('spatial.directive.dispatched', { data: JSON.stringify({
      event_id: 'event-e2e-directive-1', cursor: 41,
      payload: { directive: {
        action: 'spatial.focus_entity', target_ids: [directiveTarget], receipt_id: 'receipt-e2e-1',
        expected_projection_hash: '0123456789abcdef0123456789abcdef', intended_observed_effect: {},
      } },
    }) });
    type.instance.dispatchEvent(event);
    type.instance.dispatchEvent(event);
  }, { directiveTarget: directiveTarget! });
  await expect.poll(() => acknowledgements.length).toBe(1);
  expect(acknowledgements[0]).toMatchObject({
    operation: 'ack', receiptId: 'receipt-e2e-1',
    acknowledgement: {
      observed_target_ids: [directiveTarget!], success: true,
      action_route: { kind: 'semantic_handler', action: 'spatial.focus_entity', target_id: directiveTarget! },
    },
  });
  expect(target).toBeTruthy();
});

test('Director remains available and preserves direction across Studio depths', async ({ page }) => {
  await page.goto(studioPath());
  await page.getByRole('button', { name: 'Director' }).click();
  const director = page.getByLabel('Director workspace');
  await expect(director).toBeVisible();
  const repository = director.getByLabel('Repository URL');
  await repository.fill('https://github.com/openai/sag-video');
  await page.getByRole('button', { name: 'Context' }).click();
  await expect(director).toBeVisible();
  await expect(repository).toHaveValue('https://github.com/openai/sag-video');
  await page.getByRole('button', { name: 'System' }).click();
  await expect(director).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Director workspace').getByLabel('Repository URL')).toHaveValue('https://github.com/openai/sag-video');
  await assertNoHorizontalDrift(page);
});

test('Director tabs and controls are keyboard accessible', async ({ page }) => {
  await page.goto(studioPath());
  await page.getByRole('button', { name: 'Director' }).click();
  const director = page.getByLabel('Director workspace');
  const briefTab = director.getByRole('tab', { name: 'Brief' });
  await briefTab.focus();
  await page.keyboard.press('Enter');
  await expect(briefTab).toHaveAttribute('aria-selected', 'true');
  await director.getByRole('tab', { name: 'Direction' }).click();
  const inspect = director.getByRole('button', { name: 'Inspect repository' });
  const box = await inspect.boundingBox();
  if ((page.viewportSize()?.width ?? 1000) < 768) expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  else expect(box?.height ?? 0).toBeGreaterThanOrEqual(34);
  await assertNoHorizontalDrift(page);
});

test('Prompting Studio edits a bound module and exposes routing on mobile', async ({ page }) => {
  await page.route('**/repo-to-video/prompts/preview', async (route) => {
    const body = route.request().postDataJSON() as { creative_instruction?: string };
    const content = body.creative_instruction ?? '';
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
      schema_version: 'sag-prompt-studio/0.1', resolved_prompt_revision: 'a'.repeat(64),
      dispatch_allowed: false, warnings: ['Generate a creative brief to unlock provider prompt modules.'],
      model_registry_version: 'test', model_registry_hash: 'b'.repeat(64),
      models: [{
        id: 'gemini-omni-flash-preview', provider: 'google', family: 'video', lifecycle: 'preview',
        capabilities: ['multimodal_reasoning'], input_modalities: ['text'], output_modalities: ['video'],
        default_for: [], notes: 'Planning and video generation.',
      }],
      modules: [{
        id: 'direction.instruction', label: 'Creative direction', stage: 'direction', component: 'Director',
        model: 'gemini-omni-flash-preview', content, content_sha256: 'c'.repeat(64),
        estimated_tokens: Math.ceil(content.length / 4), dispatch: 'planning_context',
        editable_field: 'creative_instruction', consumers: ['creative brief planner', 'storyboard planner'], warnings: [],
      }],
    }) });
  });
  await page.goto(studioPath());
  await page.getByRole('button', { name: 'Director' }).click();
  const director = page.getByLabel('Director workspace');
  await director.getByRole('tab', { name: 'Prompts' }).click();
  await expect(director.getByText('Prompting Studio', { exact: true })).toBeVisible();
  await expect(director.getByLabel('Prompt routing topology')).toContainText('Omni / Veo');
  const editor = director.getByLabel('Editable source');
  await editor.fill('Create an evidence-bound product tutorial with authentic Studio captures.');
  await expect(editor).toHaveValue(/evidence-bound product tutorial/);
  const save = director.getByRole('button', { name: 'Save draft' });
  await save.click();
  await expect(director.getByText(/Matches saved draft|Changed from saved draft/)).toBeVisible();
  if ((page.viewportSize()?.width ?? 1000) < 768) {
    expect((await save.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
    expect(await director.locator('.prompt-workbench').evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  }
  await assertNoHorizontalDrift(page);
});
