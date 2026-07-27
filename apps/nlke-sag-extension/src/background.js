const SESSION_KEY = 'sagComputerUseSessionV1';

const getSession = async () => (await chrome.storage.session.get(SESSION_KEY))[SESSION_KEY] ?? {
  config: null, activities: {},
};
const putSession = (value) => chrome.storage.session.set({ [SESSION_KEY]: value });
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function api(path, init = {}) {
  const session = await getSession();
  if (!session.config?.engineUrl) throw new Error('Pair the extension with SAG first.');
  const headers = { ...(init.headers ?? {}) };
  if (session.config.token) headers.authorization = `Bearer ${session.config.token}`;
  if (!(init.body instanceof FormData)) headers['content-type'] = 'application/json';
  const response = await fetch(`${session.config.engineUrl}${path}`, { ...init, headers });
  const body = await response.json().catch(() => ({ detail: response.statusText }));
  if (!response.ok) throw new Error(body.detail ?? body.message ?? `SAG request failed (${response.status})`);
  return body;
}

async function inject(tabId) {
  await chrome.scripting.executeScript({ target: { tabId }, files: ['observer.js'] });
  await chrome.scripting.executeScript({ target: { tabId }, files: ['overlay.js'] });
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !/^https?:/.test(tab.url ?? '')) throw new Error('Activate an HTTP(S) tab first.');
  return tab;
}

async function observe(tabId, profile) {
  const result = await chrome.tabs.sendMessage(tabId, { type: 'SAG_OBSERVE', profile });
  if (result?.error) throw new Error(result.error);
  return result;
}

async function recordObservation(tabId, state) {
  const observed = await observe(tabId, state.profile);
  const record = await api(`/api/computer-use/activities/${encodeURIComponent(state.activity.id)}/observations`, {
    method: 'POST', body: JSON.stringify(observed.observation),
  });
  return { record, metadata: observed.metadata };
}

async function activate() {
  const tab = await activeTab();
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['observer.js'] });
  const session = await getSession();
  if (!session.config?.token) throw new Error('Pair the extension with SAG first.');
  const origin = new URL(tab.url).origin;
  const listed = await api(`/api/computer-use/profiles?origin=${encodeURIComponent(origin)}`);
  const installed = listed.profiles?.[0] ?? null;
  const profile = installed?.profile ?? null;
  const activity = await api('/api/computer-use/activities', {
    method: 'POST', body: JSON.stringify({
      origin, tab_session_id: `${tab.id}-${crypto.randomUUID()}`,
      profile_id: profile?.profile_id ?? null, profile_version: profile?.version ?? null,
    }),
  });
  const state = { activity, profile, activatedUrl: tab.url, activatedAt: new Date().toISOString() };
  const first = await recordObservation(tab.id, state);
  state.lastObservation = first.record;
  session.activities[String(tab.id)] = state;
  await putSession(session);
  return { activity, profile: profile ? { id: profile.profile_id, version: profile.version } : null, observation: first.record };
}

async function pause(tabId, reason = 'user_paused') {
  const session = await getSession(); const state = session.activities[String(tabId)];
  if (!state) return { paused: true };
  try {
    return await api(`/api/computer-use/activities/${encodeURIComponent(state.activity.id)}/state`, {
      method: 'POST', body: JSON.stringify({ state: 'paused', reason }),
    });
  } finally {
    // Browser-side authority is released even when SAG is temporarily
    // unreachable; the server activity still expires and rejects navigation.
    delete session.activities[String(tabId)];
    await putSession(session);
  }
}

async function captureCheckpoint(tab, state, observationId) {
  const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
  const blob = await fetch(dataUrl).then((response) => response.blob());
  const form = new FormData();
  form.set('observation_id', observationId);
  // The user sees and explicitly authorizes the exact current tab capture. No
  // automatic redaction claim is made by the adapter.
  form.set('redaction_state', 'not_applicable');
  form.set('file', blob, `sag-checkpoint-${Date.now()}.png`);
  return api(`/api/computer-use/activities/${encodeURIComponent(state.activity.id)}/checkpoints`, {
    method: 'POST', body: form,
  });
}

async function refreshAndObserve(tabId, state, priorRevision) {
  await chrome.tabs.sendMessage(tabId, { type: 'SAG_REFRESH' });
  for (let attempt = 0; attempt < 8; attempt += 1) {
    await sleep(400);
    const value = await observe(tabId, state.profile);
    const revision = Math.max(0, ...Object.values(value.metadata ?? {}).map((entry) => Number(entry.revision ?? 0)));
    if (!priorRevision || revision > priorRevision) return value;
  }
  return observe(tabId, state.profile);
}

async function runAction({ actionId, arguments: suppliedArguments }) {
  const tab = await activeTab(); const session = await getSession();
  const state = session.activities[String(tab.id)];
  if (!state) throw new Error('Activate this tab first.');
  if (tab.url !== state.activatedUrl) {
    await pause(tab.id, 'navigation_detected');
    throw new Error('The tab navigated. Activate it again before acting.');
  }
  const declaration = state.profile?.actions?.find((entry) => entry.action_id === actionId);
  if (!declaration || !['read', 'safe_reversible'].includes(declaration.safety_class)) {
    throw new Error('This action is not eligible under the installed signed profile.');
  }
  const before = await recordObservation(tab.id, state);
  await captureCheckpoint(tab, state, before.record.id);
  const binding = before.record.bindings.find((entry) => entry.eligible_action_ids.includes(actionId));
  if (!binding) throw new Error('No eligible semantic target is visible.');
  const metadata = before.metadata[binding.binding_id] ?? {};
  const actionArguments = { ...suppliedArguments };
  if (actionId === 'timeline.set_clip_transform') actionArguments.item_id = metadata.itemId;
  const intent = await api(`/api/computer-use/activities/${encodeURIComponent(state.activity.id)}/intents`, {
    method: 'POST', body: JSON.stringify({
      request_id: crypto.randomUUID(), before_observation_id: before.record.id,
      action_id: actionId, target_binding_id: binding.binding_id, arguments: actionArguments,
      context_ref: metadata.projectId ? { kind: 'project', id: metadata.projectId, revision: metadata.revision } : null,
      expected_project_revision: metadata.revision,
    }),
  });
  const execution = await api(`/api/computer-use/intents/${encodeURIComponent(intent.id)}/execute`, {
    method: 'POST', body: JSON.stringify({ ticket: intent.ticket }),
  });
  if (declaration.route === 'extension_handler') {
    const result = await chrome.tabs.sendMessage(tab.id, {
      type: 'SAG_FIXTURE_ACTION', actionId, arguments: actionArguments,
    });
    if (result?.error) throw new Error(result.error);
  }
  const observed = declaration.route === 'canonical_command'
    ? await refreshAndObserve(tab.id, state, Number(metadata.revision ?? 0))
    : await observe(tab.id, state.profile);
  const after = await api(`/api/computer-use/activities/${encodeURIComponent(state.activity.id)}/observations`, {
    method: 'POST', body: JSON.stringify(observed.observation),
  });
  await captureCheckpoint(tab, state, after.id);
  const receipt = await api(`/api/computer-use/executions/${encodeURIComponent(execution.id)}/complete`, {
    method: 'POST', body: JSON.stringify({ after_observation_id: after.id, success: true, observed_effect: {} }),
  });
  state.lastObservation = after; state.lastReceipt = receipt;
  session.activities[String(tab.id)] = state; await putSession(session);
  return receipt;
}

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id || !/^https?:/.test(tab.url ?? '')) return;
  await inject(tab.id).catch(() => undefined);
});

chrome.tabs.onUpdated.addListener(async (tabId, change) => {
  if (!change.url && change.status !== 'loading') return;
  const session = await getSession();
  if (session.activities[String(tabId)]) await pause(tabId, 'navigation_detected').catch(() => undefined);
});
chrome.tabs.onRemoved.addListener((tabId) => pause(tabId, 'tab_closed').catch(() => undefined));

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  (async () => {
    if (message?.type === 'SAG_CONFIGURE') {
      const engineUrl = new URL(message.engineUrl).origin;
      const granted = await chrome.permissions.request({ origins: [`${engineUrl}/*`] });
      if (!granted) throw new Error('Permission to contact this SAG origin was not granted.');
      const response = await fetch(`${engineUrl}/api/pairing/attach`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ code: message.code, actor_name: 'nlke-sag-extension' }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? 'Pairing failed.');
      if (body.audience !== 'computer_use' || body.principal_kind !== 'browser_extension') {
        throw new Error('Pairing code did not issue a browser computer-use principal.');
      }
      await putSession({ config: { engineUrl, token: body.access_token, workspaceId: body.workspace_id }, activities: {} });
      return { connected: true, workspaceId: body.workspace_id, expiresAt: body.expires_at };
    }
    if (message?.type === 'SAG_STATUS') {
      const session = await getSession(); const tabId = String(sender.tab?.id ?? message.tabId ?? '');
      return { configured: Boolean(session.config), activity: session.activities[tabId] ?? null };
    }
    if (message?.type === 'SAG_ACTIVATE') return activate();
    if (message?.type === 'SAG_PAUSE') return pause(sender.tab?.id ?? message.tabId, 'user_paused');
    if (message?.type === 'SAG_OBSERVE_NOW') {
      const tab = await activeTab(); const session = await getSession(); const state = session.activities[String(tab.id)];
      if (!state) throw new Error('Activate this tab first.');
      const result = await recordObservation(tab.id, state); state.lastObservation = result.record;
      session.activities[String(tab.id)] = state; await putSession(session); return result.record;
    }
    if (message?.type === 'SAG_CHECKPOINT') {
      const tab = await activeTab(); const session = await getSession(); const state = session.activities[String(tab.id)];
      if (!state?.lastObservation) throw new Error('Observe this tab before capturing a checkpoint.');
      return captureCheckpoint(tab, state, state.lastObservation.id);
    }
    if (message?.type === 'SAG_RUN_ACTION') return runAction(message);
    throw new Error('Unknown SAG extension message.');
  })().then((value) => reply({ ok: true, value }), (error) => reply({ ok: false, error: String(error?.message ?? error) }));
  return true;
});
