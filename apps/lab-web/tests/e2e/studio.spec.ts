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
    acknowledgement: { observed_target_ids: [directiveTarget!], success: true },
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
