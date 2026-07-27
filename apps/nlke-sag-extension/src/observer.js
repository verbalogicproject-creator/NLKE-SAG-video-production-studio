(() => {
  if (globalThis.__sagComputerUseObserverInstalled) return;
  globalThis.__sagComputerUseObserverInstalled = true;

  const hex = (bytes) => [...new Uint8Array(bytes)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
  const hash = async (value) => hex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)));
  const rect = (element) => {
    const value = element.getBoundingClientRect();
    const width = Math.max(1, window.innerWidth); const height = Math.max(1, window.innerHeight);
    const x = Math.max(0, Math.min(1, value.left / width));
    const y = Math.max(0, Math.min(1, value.top / height));
    return {
      x, y,
      width: Math.max(0.000001, Math.min(1 - x, value.width / width)),
      height: Math.max(0.000001, Math.min(1 - y, value.height / height)),
    };
  };
  const visible = (element) => {
    const style = getComputedStyle(element); const box = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0;
  };

  async function observe(profile) {
    const profileEntities = new Map((profile?.entities ?? []).map((entry) => [entry.entity_id, entry]));
    const actions = profile?.actions ?? [];
    const bindings = [];
    const metadata = {};
    for (const [entityId, entity] of profileEntities) {
      let element = null;
      const locator = entity.locator;
      if (locator.kind === 'sag_entity') element = document.querySelector(`[data-sag-entity="${CSS.escape(locator.value)}"]`);
      if (locator.kind === 'test_id') element = document.querySelector(`[data-testid="${CSS.escape(locator.value)}"]`);
      if (locator.kind === 'aria') element = document.querySelector(`[aria-label="${CSS.escape(locator.value)}"]`);
      if (locator.kind === 'label') element = [...document.querySelectorAll('label')].find((entry) => entry.textContent?.trim() === locator.value)?.control ?? null;
      if (!element || !visible(element)) continue;
      const eligible = actions.filter((action) => action.entity_ids.includes(entityId)).map((action) => action.action_id);
      const bindingId = `binding_${entityId.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
      bindings.push({
        binding_id: bindingId, entity_id: entityId, role: entity.role, label: entityId,
        rect: rect(element), source: 'profile', confidence: 1, visible: true, protected: false,
        eligible_action_ids: eligible,
      });
      metadata[bindingId] = {
        itemId: element.dataset.sagItemId ?? null,
        projectId: document.querySelector('[data-sag-project-id]')?.dataset.sagProjectId ?? null,
        revision: Number(document.querySelector('[data-sag-project-revision]')?.dataset.sagProjectRevision ?? 0) || null,
      };
    }
    if (!profile) {
      [...document.querySelectorAll('button,a,input,select,textarea,[role]')].slice(0, 64).forEach((element, index) => {
        if (!visible(element)) return;
        bindings.push({
          binding_id: `generic_binding_${index}`, entity_id: `generic.${element.tagName.toLowerCase()}.${index}`,
          role: element.getAttribute('role') ?? element.tagName.toLowerCase(), label: element.tagName.toLowerCase(),
          rect: rect(element), source: 'dom', confidence: 0.8, visible: true,
          protected: ['INPUT', 'TEXTAREA'].includes(element.tagName), eligible_action_ids: [],
        });
      });
    }
    const route = `${location.pathname}${location.search}${location.hash}`;
    const state = JSON.stringify({
      route, revision: document.querySelector('[data-sag-project-revision]')?.dataset.sagProjectRevision ?? null,
      bindings: bindings.map((entry) => [entry.entity_id, entry.visible]),
    });
    const projectId = document.querySelector('[data-sag-project-id]')?.dataset.sagProjectId;
    const revision = Number(document.querySelector('[data-sag-project-revision]')?.dataset.sagProjectRevision ?? 0);
    return {
      observation: {
        origin: location.origin, route_hash: await hash(route), title_hash: await hash(document.title),
        viewport: { width: innerWidth, height: innerHeight, device_scale_factor: devicePixelRatio },
        application_state_hash: await hash(state), bindings,
        context_refs: projectId ? [{ kind: 'project', id: projectId, revision: revision || null }] : [],
        redaction_state: 'metadata_only', observed_at: new Date().toISOString(),
      },
      metadata,
    };
  }

  chrome.runtime.onMessage.addListener((message, _sender, reply) => {
    if (message?.type === 'SAG_OBSERVE') {
      observe(message.profile).then(reply, (error) => reply({ error: String(error?.message ?? error) }));
      return true;
    }
    if (message?.type === 'SAG_REFRESH') {
      window.dispatchEvent(new CustomEvent('sag:computer-use:refresh'));
      reply({ ok: true });
    }
    if (message?.type === 'SAG_FIXTURE_ACTION') {
      const element = document.querySelector('[data-testid="computer-use-value"]');
      if (!(element instanceof HTMLInputElement)) return reply({ error: 'fixture target unavailable' });
      element.value = String(message.arguments?.value ?? '');
      element.dispatchEvent(new Event('input', { bubbles: true }));
      element.dispatchEvent(new Event('change', { bubbles: true }));
      reply({ ok: true });
    }
  });
})();
