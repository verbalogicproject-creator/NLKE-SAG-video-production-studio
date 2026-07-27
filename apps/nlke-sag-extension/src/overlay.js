(() => {
  const existing = document.getElementById('nlke-sag-computer-use-host');
  if (existing) { existing.remove(); return; }
  const host = document.createElement('aside');
  host.id = 'nlke-sag-computer-use-host';
  host.style.cssText = 'all:initial;position:fixed;z-index:2147483647;right:18px;top:18px';
  document.documentElement.append(host);
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = `
    <link rel="stylesheet" href="${chrome.runtime.getURL('overlay.css')}">
    <section class="shell" aria-label="SAG Computer Use">
      <header><div><span class="eyebrow">NLKE · SAG</span><strong>Computer Use</strong></div><button id="close" aria-label="Close">×</button></header>
      <div id="status" class="status idle"><i></i><span>Not paired</span></div>
      <div id="pair" class="stack">
        <label>SAG engine<input id="engine" type="url" value="http://127.0.0.1:8080" spellcheck="false"></label>
        <label>One-time pairing code<input id="code" inputmode="numeric" maxlength="6" placeholder="000000"></label>
        <button id="connect" class="primary">Pair workspace</button>
      </div>
      <div id="controls" class="stack hidden">
        <div class="contract"><span>Current tab only</span><span>No coordinates</span><span>Signed actions</span></div>
        <button id="activate" class="primary">Activate this tab</button>
        <div class="grid"><button id="observe">Observe metadata</button><button id="checkpoint">Capture checkpoint</button></div>
        <div id="actions" class="actions hidden">
          <small>SAFE REVERSIBLE · EXPLICIT BEFORE/AFTER</small>
          <button id="scale" class="accent">Confirm clip scale → 0.85</button>
          <button id="restore">Compensate clip scale → 1.00</button>
          <button id="fixture" class="accent">Confirm fixture value change</button>
        </div>
        <button id="pause" class="quiet">Pause and release tab</button>
      </div>
      <pre id="result" aria-live="polite"></pre>
      <footer>Routine frames are metadata-only. Screenshots occur only when you click.</footer>
    </section>`;
  const element = (id) => root.getElementById(id);
  const status = element('status'); const result = element('result');
  let activeProfile = null;
  const message = (value) => new Promise((resolve, reject) => chrome.runtime.sendMessage(value, (response) => {
    if (chrome.runtime.lastError) return reject(chrome.runtime.lastError);
    if (!response?.ok) return reject(new Error(response?.error ?? 'Extension request failed'));
    resolve(response.value);
  }));
  const setStatus = (label, state = 'idle') => {
    status.className = `status ${state}`; status.querySelector('span').textContent = label;
  };
  const run = async (label, operation) => {
    setStatus(label, 'busy'); result.textContent = '';
    try {
      const value = await operation();
      setStatus('Ready', 'ready');
      result.textContent = JSON.stringify(value, null, 2).slice(0, 1800);
      return value;
    } catch (error) {
      setStatus(error.message ?? String(error), 'error');
      throw error;
    }
  };
  element('close').onclick = () => host.remove();
  element('connect').onclick = () => run('Pairing workspace…', async () => {
    const value = await message({ type: 'SAG_CONFIGURE', engineUrl: element('engine').value, code: element('code').value });
    element('pair').classList.add('hidden'); element('controls').classList.remove('hidden');
    return value;
  }).catch(() => undefined);
  element('activate').onclick = () => run('Activating current tab…', async () => {
    const value = await message({ type: 'SAG_ACTIVATE' }); activeProfile = value.profile?.id ?? null;
    element('actions').classList.toggle('hidden', !activeProfile);
    element('scale').classList.toggle('hidden', activeProfile !== 'sag.studio.local');
    element('restore').classList.toggle('hidden', activeProfile !== 'sag.studio.local');
    element('fixture').classList.toggle('hidden', activeProfile !== 'sag.fixture.local');
    return value;
  }).catch(() => undefined);
  element('observe').onclick = () => run('Recording bounded observation…', () => message({ type: 'SAG_OBSERVE_NOW' })).catch(() => undefined);
  element('checkpoint').onclick = () => run('Capturing explicit checkpoint…', () => message({ type: 'SAG_CHECKPOINT' })).catch(() => undefined);
  element('scale').onclick = () => run('Applying and verifying scale…', () => message({ type: 'SAG_RUN_ACTION', actionId: 'timeline.set_clip_transform', arguments: { scale: 0.85 } })).catch(() => undefined);
  element('restore').onclick = () => run('Compensating and verifying…', () => message({ type: 'SAG_RUN_ACTION', actionId: 'timeline.set_clip_transform', arguments: { scale: 1 } })).catch(() => undefined);
  element('fixture').onclick = () => run('Applying fixture action…', () => message({ type: 'SAG_RUN_ACTION', actionId: 'fixture.set_value', arguments: { value: 'SAG verified' } })).catch(() => undefined);
  element('pause').onclick = () => run('Pausing…', () => message({ type: 'SAG_PAUSE' })).then(() => {
    activeProfile = null; element('actions').classList.add('hidden'); setStatus('Paused', 'idle');
  }).catch(() => undefined);
  message({ type: 'SAG_STATUS' }).then((value) => {
    if (!value.configured) return;
    element('pair').classList.add('hidden'); element('controls').classList.remove('hidden');
    setStatus(value.activity ? 'Active on this tab' : 'Paired · tab inactive', value.activity ? 'ready' : 'idle');
  }).catch(() => undefined);
})();
