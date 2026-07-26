const TICKS = 120000;
const state = {
  projectId: localStorage.getItem("sag-video-project") || "demo",
  projects: [], project: null, selection: [], receipts: [], busy: false,
  playheadTicks: 0, previewItemId: null, pairTimer: null,
  renderJobId: null, renderReceiptId: null, resultUrl: null,
  sequencePlaying: false, playbackOriginTicks: 0, playbackStartedAt: 0,
  playbackFrame: null,
  shortsJobId: null,
};
const $ = (id) => document.getElementById(id);

function inviteToken() {
  let token = sessionStorage.getItem("sag-video-invite") || "";
  if (!token && location.search.includes("invite=")) {
    token = new URLSearchParams(location.search).get("invite") || "";
    sessionStorage.setItem("sag-video-invite", token);
    history.replaceState({}, "", "/");
  }
  return token;
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  if (inviteToken()) headers["X-Invite-Token"] = inviteToken();
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401 && !inviteToken()) {
    const token = prompt("Enter your SAG Video invite token");
    if (token) {
      sessionStorage.setItem("sag-video-invite", token);
      return api(path, options);
    }
  }
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.detail || `Request failed: ${response.status}`);
    error.code = payload.code;
    throw error;
  }
  return payload;
}

function requestId(prefix) { return `${prefix}-${crypto.randomUUID()}`; }
function allItems() { return state.project?.tracks.flatMap((track) => track.items) || []; }
function videoItems() { return allItems().filter((item) => item.kind === "video" && assetById(item.asset_id)).sort((a, b) => a.start_ticks - b.start_ticks); }
function activeVideoItem(ticks = state.playheadTicks) { return videoItems().find((item) => ticks >= item.start_ticks && ticks < item.start_ticks + item.duration_ticks) || null; }
function selectedItem() { return allItems().find((item) => state.selection.includes(item.id)); }
function assetById(assetId) { return state.project?.assets.find((asset) => asset.id === assetId); }
function seconds(ticks) { return ticks / TICKS; }
function timeLabel(ticks) { return `${seconds(ticks).toFixed(1).padStart(4, "0")}s`; }
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}
function toast(message, error = false) {
  const node = $("toast");
  node.textContent = message;
  node.className = `toast${error ? " error" : ""}`;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 4200);
}

async function loadProjects() {
  const payload = await api("/api/projects");
  state.projects = payload.projects;
  if (!state.projects.some((project) => project.id === state.projectId)) {
    state.projectId = state.projects.find((project) => project.id === "demo")?.id || state.projects[0]?.id;
  }
  const picker = $("project-picker");
  picker.innerHTML = "";
  state.projects.forEach((project) => {
    const option = document.createElement("option");
    option.value = project.id;
    option.textContent = project.name;
    option.selected = project.id === state.projectId;
    picker.appendChild(option);
  });
}

async function load({ projects = false } = {}) {
  if (projects || !state.projects.length) await loadProjects();
  const payload = await api(`/api/projects/${state.projectId}`);
  state.project = payload.project;
  state.selection = payload.selection;
  state.receipts = await api(`/api/projects/${state.projectId}/receipts`);
  state.playheadTicks = Math.min(state.playheadTicks, state.project.duration_ticks);
  localStorage.setItem("sag-video-project", state.projectId);
  draw();
  checkPairStatus();
}

function draw() {
  const project = state.project;
  $("project-name").textContent = project.name;
  $("revision").textContent = `revision ${project.revision}`;
  $("project-picker").value = project.id;
  $("reset").hidden = project.id !== "demo";
  $("render").hidden = false;
  $("render").disabled = Boolean(state.renderJobId);
  $("resolution").textContent = `${project.canvas.width} × ${project.canvas.height} · ${project.canvas.fps_numerator / project.canvas.fps_denominator} fps`;
  $("duration").textContent = timeLabel(project.duration_ticks);
  $("playhead").max = project.duration_ticks;
  $("playhead").value = state.playheadTicks;
  $("playhead-time").textContent = timeLabel(state.playheadTicks);
  drawMedia();
  drawMonitor();
  drawTimeline();
  drawInspector();
  drawReceipts();
}

function drawMedia() {
  const libraryAssets = state.project.assets.filter((asset) => asset.source_kind !== "derived");
  $("media-grid").innerHTML = libraryAssets.map((asset, index) => {
    const metadata = asset.duration_ticks ? `${seconds(asset.duration_ticks).toFixed(1)}s${asset.width ? ` / ${asset.width}×${asset.height}` : ""}` : asset.kind;
    const thumbnail = asset.thumbnail_asset_id ? `background-image:url('/api/projects/${state.project.id}/assets/${asset.id}/thumbnail')` : `background:${index ? "#292a27" : "#252a2e"}`;
    const insert = asset.intake_status === "observed_valid" && ["video", "audio"].includes(asset.kind)
      ? `<button data-insert-asset="${asset.id}">Add to timeline</button>` : "";
    return `<article class="media-item"><div class="media-thumb" style="${thumbnail}"></div><strong>${escapeHtml(asset.name)}</strong><small>${metadata}</small><em>${asset.intake_status || "pending"}</em>${insert}</article>`;
  }).join("") || `<div class="empty">Import a video or audio file to begin.</div>`;
  document.querySelectorAll("[data-insert-asset]").forEach((button) => {
    button.onclick = () => runCommands([{
      name: "timeline.insert_asset",
      args: { asset_id: button.dataset.insertAsset },
    }], "Asset inserted on the canonical timeline.");
  });
}

function previewableItem() {
  return activeVideoItem();
}

function drawMonitor() {
  const monitor = $("monitor");
  $("caption-preview").hidden = true;
  monitor.classList.toggle("vertical", state.project.canvas.height > state.project.canvas.width);
  monitor.style.aspectRatio = `${state.project.canvas.width} / ${state.project.canvas.height}`;
  const video = $("preview-video");
  const resultVideo = $("result-video");
  const placeholder = $("monitor-placeholder");
  placeholder.hidden = true;
  if (state.resultUrl) {
    if (resultVideo.dataset.url !== state.resultUrl) {
      resultVideo.src = state.resultUrl;
      resultVideo.dataset.url = state.resultUrl;
    }
    resultVideo.hidden = false;
    video.hidden = true;
    $("monitor-empty").hidden = true;
    $("preview-title").hidden = true;
    $("transform-box").hidden = true;
    monitor.classList.add("showing-result");
    return;
  }
  resultVideo.hidden = true;
  monitor.classList.remove("showing-result");
  const item = previewableItem();
  const title = allItems().find((entry) => entry.kind === "title");
  const node = $("preview-title");
  if (title) {
    const sx = monitor.clientWidth / state.project.canvas.width;
    const sy = monitor.clientHeight / state.project.canvas.height;
    node.hidden = false;
    node.style.left = `${title.x * sx}px`;
    node.style.top = `${title.y * sy}px`;
    node.style.width = `${title.width * sx}px`;
    node.style.height = `${title.height * sy}px`;
    node.style.background = title.color;
    node.querySelector("span").textContent = title.text;
    node.classList.toggle("selected", state.selection.includes(title.id));
    node.onclick = () => select(title.id);
  } else {
    node.hidden = true;
  }
  if (!item) {
    video.pause();
    video.hidden = true;
    video.removeAttribute("src");
    video.dataset.itemId = "";
    $("monitor-empty").hidden = false;
    $("monitor-empty").textContent = videoItems().length ? "Timeline gap" : "Insert an observed video asset";
    $("transform-box").hidden = true;
    state.previewItemId = null;
    updateTitleVisibility();
    updateCaptionVisibility();
    return;
  }
  const asset = assetById(item.asset_id);
  if (!asset.managed_uri) {
    video.pause();
    video.hidden = true;
    video.removeAttribute("src");
    video.dataset.itemId = "";
    placeholder.querySelector("strong").textContent = asset.name;
    placeholder.hidden = false;
    $("monitor-empty").hidden = true;
    $("transform-box").hidden = true;
    state.previewItemId = item.id;
    updateTitleVisibility();
    updateCaptionVisibility();
    return;
  }
  const src = asset.proxy_asset_id
    ? `/api/projects/${state.project.id}/assets/${asset.id}/proxy`
    : `/api/projects/${state.project.id}/assets/${asset.id}/content`;
  if (video.dataset.itemId !== item.id) {
    video.src = src;
    video.dataset.itemId = item.id;
    state.previewItemId = item.id;
    state.playheadTicks = Math.max(item.start_ticks, Math.min(state.playheadTicks, item.start_ticks + item.duration_ticks));
    $("playhead").value = state.playheadTicks;
    $("playhead-time").textContent = timeLabel(state.playheadTicks);
    video.addEventListener("loadedmetadata", () => {
      syncVideoToPlayhead();
      if (state.sequencePlaying) video.play().catch(() => {});
    }, { once: true });
  }
  video.hidden = false;
  $("monitor-empty").hidden = true;
  video.style.objectFit = item.fit_mode === "fill" ? "cover" : item.fit_mode === "stretch" ? "fill" : "contain";
  if (item.crop_keyframes?.length) {
    const relative = Math.max(0, state.playheadTicks - item.start_ticks);
    const nextIndex = item.crop_keyframes.findIndex((entry) => entry.time_ticks >= relative);
    const right = item.crop_keyframes[nextIndex < 0 ? item.crop_keyframes.length - 1 : nextIndex];
    const left = item.crop_keyframes[Math.max(0, (nextIndex < 0 ? item.crop_keyframes.length : nextIndex) - 1)];
    const mix = right.time_ticks === left.time_ticks ? 0 : Math.max(0, Math.min(1, (relative - left.time_ticks) / (right.time_ticks - left.time_ticks)));
    const centerX = left.center_x + (right.center_x - left.center_x) * mix;
    const centerY = left.center_y + (right.center_y - left.center_y) * mix;
    video.style.objectPosition = `${centerX * 100}% ${centerY * 100}%`;
  } else video.style.objectPosition = "50% 50%";
  video.style.opacity = item.opacity;
  video.style.transform = `translate(${item.x}px, ${item.y}px) scale(${item.scale}) rotate(${item.rotation}deg)`;
  video.muted = item.muted;
  video.volume = Math.min(1, Math.pow(10, item.gain_db / 20));
  updateTransformBox(item);
  updateTitleVisibility();
  updateCaptionVisibility();
}

function updateTransformBox(item, preview = null) {
  const box = $("transform-box");
  if (!item || item.kind !== "video" || !state.selection.includes(item.id)) {
    box.hidden = true;
    return;
  }
  const values = preview || item;
  const monitor = $("monitor");
  const sx = monitor.clientWidth / state.project.canvas.width;
  const sy = monitor.clientHeight / state.project.canvas.height;
  const width = state.project.canvas.width * values.scale;
  const height = state.project.canvas.height * values.scale;
  box.hidden = false;
  box.style.left = `${(values.x + (state.project.canvas.width - width) / 2) * sx}px`;
  box.style.top = `${(values.y + (state.project.canvas.height - height) / 2) * sy}px`;
  box.style.width = `${width * sx}px`;
  box.style.height = `${height * sy}px`;
  box.style.transform = `rotate(${values.rotation}deg)`;
}

function drawTimeline() {
  const duration = state.project.duration_ticks;
  const zoom = +$("zoom").value;
  const timelineWidth = Math.max(720, Math.round(720 * zoom / 5));
  $("tracks").style.minWidth = `${timelineWidth}px`;
  const ruler = document.querySelector(".ruler");
  ruler.style.width = `${timelineWidth - 130}px`;
  ruler.style.minWidth = `${timelineWidth - 130}px`;
  ruler.innerHTML = Array.from({ length: 7 }, (_, index) => `<span>${timeLabel(Math.round(duration * index / 6))}</span>`).join("");
  $("tracks").innerHTML = state.project.tracks.map((track) => `<div class="track"><div class="track-label"><strong>${escapeHtml(track.name)}</strong><span>${track.kind}</span></div><div class="track-lane" data-track="${track.id}"><span class="lane-playhead"></span>${track.items.map((item) => {
    const left = item.start_ticks / duration * 100;
    const width = item.duration_ticks / duration * 100;
    const handles = ["video", "audio"].includes(item.kind) ? `<button class="trim-handle trim-left" data-trim="left" aria-label="Trim clip start"></button><button class="trim-handle trim-right" data-trim="right" aria-label="Trim clip end"></button>` : "";
    return `<div tabindex="0" data-item="${item.id}" class="timeline-item ${item.kind} ${state.selection.includes(item.id) ? "selected" : ""}" style="left:${left}%;width:${Math.max(width, .4)}%;background:${item.kind === "title" ? "" : item.color}">${handles}<strong>${escapeHtml(item.name)}</strong><small>${seconds(item.duration_ticks).toFixed(1)}s / ${item.id}</small></div>`;
  }).join("")}</div></div>`).join("");
  document.querySelectorAll("[data-item]").forEach((node) => installTimelineItem(node));
  document.querySelectorAll(".track-lane").forEach((lane) => {
    lane.onclick = (event) => {
      if (event.target !== lane) return;
      const box = lane.getBoundingClientRect();
      setPlayhead(Math.round((event.clientX - box.left) / box.width * duration), true);
    };
  });
  updateTimelinePlayhead();
}

function updateTimelinePlayhead() {
  if (!state.project) return;
  const percent = state.playheadTicks / state.project.duration_ticks * 100;
  document.querySelectorAll(".lane-playhead").forEach((node) => { node.style.left = `${percent}%`; });
}

function snapTicks(value, itemId, thresholdTicks) {
  const edges = [0, state.project.duration_ticks];
  allItems().forEach((item) => {
    if (item.id !== itemId) edges.push(item.start_ticks, item.start_ticks + item.duration_ticks);
  });
  const nearest = edges.reduce((best, edge) => Math.abs(edge - value) < Math.abs(best - value) ? edge : best, value);
  return Math.abs(nearest - value) <= thresholdTicks ? nearest : value;
}

function installTimelineItem(node) {
  let startX = 0;
  let originalLeft = 0;
  let originalWidth = 0;
  let dragged = false;
  let trimMode = null;
  node.onpointerdown = (event) => {
    if (state.busy) return;
    startX = event.clientX;
    originalLeft = node.offsetLeft;
    originalWidth = node.offsetWidth;
    dragged = false;
    trimMode = event.target.dataset.trim || null;
    node.setPointerCapture(event.pointerId);
    event.stopPropagation();
  };
  node.onpointermove = (event) => {
    if (!node.hasPointerCapture(event.pointerId)) return;
    const delta = event.clientX - startX;
    if (Math.abs(delta) < 5) return;
    dragged = true;
    const laneWidth = node.parentElement.clientWidth;
    if (trimMode === "left") {
      const adjusted = Math.max(-originalLeft, Math.min(originalWidth - 24, delta));
      node.style.left = `${(originalLeft + adjusted) / laneWidth * 100}%`;
      node.style.width = `${(originalWidth - adjusted) / laneWidth * 100}%`;
    } else if (trimMode === "right") {
      node.style.width = `${Math.max(24, originalWidth + delta) / laneWidth * 100}%`;
    } else {
      node.style.left = `${Math.max(0, Math.min(laneWidth - originalWidth, originalLeft + delta)) / laneWidth * 100}%`;
    }
  };
  node.onpointerup = async (event) => {
    if (!node.hasPointerCapture(event.pointerId)) return;
    node.releasePointerCapture(event.pointerId);
    if (!dragged) {
      select(node.dataset.item);
      return;
    }
    const lane = node.parentElement;
    const item = allItems().find((entry) => entry.id === node.dataset.item);
    const threshold = Math.round(state.project.duration_ticks * 8 / lane.clientWidth);
    if (trimMode) {
      const minimum = Math.max(1, Math.round(TICKS / 30));
      let startTicks = item.start_ticks;
      let sourceIn = item.source_in_ticks || 0;
      let durationTicks = item.duration_ticks;
      if (trimMode === "left") {
        const rawStart = Math.round(node.offsetLeft / lane.clientWidth * state.project.duration_ticks);
        const snappedStart = snapTicks(rawStart, item.id, threshold);
        const delta = Math.max(-Math.min(item.start_ticks, sourceIn), Math.min(item.duration_ticks - minimum, snappedStart - item.start_ticks));
        startTicks += delta;
        sourceIn += delta;
        durationTicks -= delta;
      } else {
        const rawEnd = Math.round((node.offsetLeft + node.offsetWidth) / lane.clientWidth * state.project.duration_ticks);
        const end = snapTicks(rawEnd, item.id, threshold);
        durationTicks = Math.max(minimum, end - item.start_ticks);
        const asset = assetById(item.asset_id);
        if (asset?.duration_ticks) durationTicks = Math.min(durationTicks, asset.duration_ticks - sourceIn);
      }
      await runCommands([{ name: "timeline.trim_clip", args: {
        item_id: item.id, start_ticks: startTicks, duration_ticks: durationTicks,
        source_in_ticks: sourceIn, source_out_ticks: sourceIn + durationTicks,
      } }], "Clip edge trimmed.");
    } else {
      const rawStart = Math.round(node.offsetLeft / lane.clientWidth * state.project.duration_ticks);
      const startTicks = snapTicks(rawStart, item.id, threshold);
      await runCommands([{ name: "timeline.move_item", args: { item_id: item.id, start_ticks: startTicks } }], "Timeline position updated.");
    }
  };
}

function drawInspector() {
  const item = selectedItem();
  $("selection-name").textContent = item?.name || "Nothing selected";
  $("selection-id").textContent = item?.id || "No stable ID";
  $("inspector-empty").hidden = Boolean(item);
  $("title-form").hidden = item?.kind !== "title";
  $("clip-form").hidden = !["video", "audio"].includes(item?.kind);
  $("caption-form").hidden = item?.kind !== "caption";
  if (item?.kind === "title") {
    $("field-text").value = item.text || "";
    $("field-x").value = item.x;
    $("field-y").value = item.y;
    $("field-width").value = item.width;
    $("field-height").value = item.height;
  } else if (["video", "audio"].includes(item?.kind)) {
    $("field-start").value = item.start_ticks;
    $("field-duration").value = item.duration_ticks;
    $("field-source-in").value = item.source_in_ticks || 0;
    $("field-fit").value = item.fit_mode || "fit";
    $("fit-label").hidden = item.kind !== "video";
    $("visual-fields").hidden = item.kind !== "video";
    $("field-clip-x").value = item.x || 0;
    $("field-clip-y").value = item.y || 0;
    $("field-scale").value = item.scale || 1;
    $("field-rotation").value = item.rotation || 0;
    $("field-opacity").value = item.opacity ?? 1;
    $("field-gain").value = item.gain_db || 0;
    $("field-muted").checked = Boolean(item.muted);
    $("crop-fields").hidden = item.kind !== "video" || !item.crop_keyframes?.length;
    if (item.crop_keyframes?.length) {
      $("field-crop-x").value = item.crop_keyframes[0].center_x;
      $("field-crop-y").value = item.crop_keyframes[0].center_y;
    }
  } else if (item?.kind === "caption") {
    const style = item.caption_style || {};
    $("field-caption-text").value = item.caption_words.map((word) => word.text).join(" ");
    $("field-caption-preset").value = style.preset || "bold_pop";
    $("field-caption-position").value = style.position || "bottom";
    $("field-caption-size").value = style.font_size || 64;
    $("field-caption-font").value = style.font_family || "Noto Sans";
    $("field-caption-words").value = style.words_per_cue || 5;
    $("field-caption-color").value = (style.text_color || "#FFFFFF").slice(0, 7);
    $("field-caption-highlight").value = (style.highlight_color || "#F8E71C").slice(0, 7);
    $("field-caption-background").value = (style.background_color || "#000000").slice(0, 7);
  }
}

function drawReceipts() {
  $("receipt-count").textContent = state.receipts.length;
  $("receipts").innerHTML = state.receipts.map((receipt) => {
    const tone = receipt.status === "observed_success" ? "success" : ["observed_failure", "execution_failed", "denied", "cancelled", "timeout"].includes(receipt.status) ? "failure" : "pending";
    const label = receipt.command.replaceAll(".", " / ");
    const intake = receipt.command === "asset.import" && receipt.payload.artifact_sha256 ? ` / sha ${receipt.payload.artifact_sha256.slice(0, 10)}` : "";
    return `<div class="receipt ${tone}" title="${receipt.id}"><span class="receipt-dot"></span><span><strong>${label}</strong><small>${receipt.status.replaceAll("_", " ")} / r${receipt.project_revision}${intake}</small></span><time>${escapeHtml(receipt.actor)}</time></div>`;
  }).join("") || `<div class="empty">Receipts appear after a declared action.</div>`;
}

async function select(itemId) {
  try {
    stopSequencePlayback();
    await api(`/api/projects/${state.projectId}/selection`, {
      method: "POST",
      body: JSON.stringify({ item_ids: [itemId], expected_revision: state.project.revision, request_id: requestId("selection"), actor: "browser" }),
    });
    state.selection = [itemId];
    const item = selectedItem();
    if (item) state.playheadTicks = item.start_ticks;
    draw();
  } catch (error) { toast(error.message, true); }
}

async function dispatchCommand(name, args) {
  const receipt = await api(`/api/projects/${state.projectId}/commands`, {
    method: "POST",
    body: JSON.stringify({ command: name, arguments: args, expected_revision: state.project.revision, request_id: requestId("browser"), actor: "browser" }),
  });
  state.resultUrl = null;
  await load();
  return receipt;
}

async function runCommands(steps, successMessage) {
  if (state.busy || !steps.length) return;
  stopSequencePlayback();
  state.busy = true;
  try {
    for (const step of steps) await dispatchCommand(step.name, step.args);
    toast(successMessage);
  } catch (error) {
    if (error.code === "stale_revision") toast("The project changed elsewhere. Refreshed without replaying your edit.", true);
    else toast(error.message, true);
    await load();
  } finally { state.busy = false; }
}

function setPlayhead(ticks, syncVideo = false) {
  state.playheadTicks = Math.max(0, Math.min(Number(ticks), state.project.duration_ticks));
  $("playhead").value = state.playheadTicks;
  $("playhead-time").textContent = timeLabel(state.playheadTicks);
  updateTimelinePlayhead();
  if (syncVideo) syncVideoToPlayhead();
  updateTitleVisibility();
  updateCaptionVisibility();
  updateCropPreview();
}

function syncVideoToPlayhead(autoPlay = false) {
  const item = previewableItem();
  const video = $("preview-video");
  if (!item) {
    if (state.previewItemId) drawMonitor();
    return;
  }
  const asset = assetById(item.asset_id);
  if (!asset?.managed_uri) {
    if (state.previewItemId !== item.id) drawMonitor();
    return;
  }
  if (video.dataset.itemId !== item.id) {
    drawMonitor();
    return;
  }
  if (!video.duration) return;
  const relative = Math.max(0, Math.min(item.duration_ticks, state.playheadTicks - item.start_ticks));
  const sourceTicks = (item.source_in_ticks || 0) + relative;
  const sourceSeconds = seconds(sourceTicks);
  if (Math.abs(video.currentTime - sourceSeconds) > .18) video.currentTime = sourceSeconds;
  if (autoPlay && video.paused) video.play().catch(() => {});
}

function updateTitleVisibility() {
  const title = allItems().find((entry) => entry.kind === "title");
  if (!title) return;
  const active = state.playheadTicks >= title.start_ticks && state.playheadTicks < title.start_ticks + title.duration_ticks;
  $("preview-title").style.visibility = active ? "visible" : "hidden";
}

function updateCaptionVisibility() {
  const node = $("caption-preview");
  const caption = allItems().find((entry) => entry.kind === "caption");
  if (!caption || state.playheadTicks < caption.start_ticks || state.playheadTicks >= caption.start_ticks + caption.duration_ticks) {
    node.hidden = true;
    return;
  }
  const relative = state.playheadTicks - caption.start_ticks;
  const words = caption.caption_words || [];
  const activeIndex = words.findIndex((word) => relative >= word.start_ticks && relative < word.end_ticks);
  const style = caption.caption_style || {};
  const perCue = style.words_per_cue || 5;
  const cueStart = Math.max(0, Math.floor(Math.max(0, activeIndex) / perCue) * perCue);
  const cue = words.slice(cueStart, cueStart + perCue);
  node.innerHTML = cue.map((word, index) => `<span class="${cueStart + index === activeIndex ? "active" : ""}">${escapeHtml(word.text)}</span>`).join(" ");
  node.style.fontSize = `${Math.max(14, (style.font_size || 64) * $("monitor").clientHeight / state.project.canvas.height)}px`;
  node.style.color = style.text_color || "#fff";
  node.style.setProperty("--caption-highlight", style.highlight_color || "#f8e71c");
  node.dataset.position = style.position || "bottom";
  node.hidden = !cue.length;
}

function updateCropPreview() {
  const item = activeVideoItem();
  const video = $("preview-video");
  if (!item?.crop_keyframes?.length) return;
  const relative = Math.max(0, state.playheadTicks - item.start_ticks);
  const nextIndex = item.crop_keyframes.findIndex((entry) => entry.time_ticks >= relative);
  const right = item.crop_keyframes[nextIndex < 0 ? item.crop_keyframes.length - 1 : nextIndex];
  const left = item.crop_keyframes[Math.max(0, (nextIndex < 0 ? item.crop_keyframes.length : nextIndex) - 1)];
  const mix = right.time_ticks === left.time_ticks ? 0 : Math.max(0, Math.min(1, (relative - left.time_ticks) / (right.time_ticks - left.time_ticks)));
  video.style.objectPosition = `${(left.center_x + (right.center_x-left.center_x)*mix)*100}% ${(left.center_y + (right.center_y-left.center_y)*mix)*100}%`;
}

function stopSequencePlayback() {
  state.sequencePlaying = false;
  if (state.playbackFrame) cancelAnimationFrame(state.playbackFrame);
  state.playbackFrame = null;
  $("preview-video").pause();
  $("play").textContent = "▶";
}

function playbackTick(now) {
  if (!state.sequencePlaying) return;
  const elapsedTicks = Math.round((now - state.playbackStartedAt) / 1000 * TICKS);
  const next = state.playbackOriginTicks + elapsedTicks;
  if (next >= state.project.duration_ticks) {
    setPlayhead(state.project.duration_ticks, true);
    stopSequencePlayback();
    return;
  }
  setPlayhead(next);
  syncVideoToPlayhead(true);
  state.playbackFrame = requestAnimationFrame(playbackTick);
}

function startSequencePlayback() {
  if (!videoItems().length) return toast("Insert an observed video first.", true);
  if (state.playheadTicks >= state.project.duration_ticks) setPlayhead(0, true);
  state.resultUrl = null;
  drawMonitor();
  state.sequencePlaying = true;
  state.playbackOriginTicks = state.playheadTicks;
  state.playbackStartedAt = performance.now();
  $("play").textContent = "❚❚";
  syncVideoToPlayhead(true);
  state.playbackFrame = requestAnimationFrame(playbackTick);
}

$("title-form").onsubmit = (event) => {
  event.preventDefault();
  const item = selectedItem();
  const steps = [];
  const text = $("field-text").value.trim();
  if (text !== item.text) steps.push({ name: "timeline.set_title", args: { item_id: item.id, text } });
  const transform = { x: +$("field-x").value, y: +$("field-y").value, width: +$("field-width").value, height: +$("field-height").value };
  if (["x", "y", "width", "height"].some((field) => transform[field] !== item[field])) {
    steps.push({ name: "timeline.set_title_transform", args: { item_id: item.id, ...transform } });
  }
  runCommands(steps, "Title changes applied to the canonical project.");
};

$("clip-form").onsubmit = (event) => {
  event.preventDefault();
  const item = selectedItem();
  const start = +$("field-start").value;
  const duration = +$("field-duration").value;
  const sourceIn = +$("field-source-in").value;
  const steps = [];
  if (start !== item.start_ticks || duration !== item.duration_ticks || sourceIn !== (item.source_in_ticks || 0)) {
    steps.push({ name: "timeline.trim_clip", args: { item_id: item.id, start_ticks: start, duration_ticks: duration, source_in_ticks: sourceIn, source_out_ticks: sourceIn + duration } });
  }
  if (item.kind === "video") {
    const transform = {
      fit_mode: $("field-fit").value, x: +$("field-clip-x").value, y: +$("field-clip-y").value,
      scale: +$("field-scale").value, rotation: +$("field-rotation").value,
      opacity: +$("field-opacity").value,
    };
    if (Object.entries(transform).some(([field, value]) => value !== item[field])) {
      steps.push({ name: "timeline.set_clip_transform", args: { item_id: item.id, ...transform } });
    }
    if (item.crop_keyframes?.length) {
      const centerX = +$("field-crop-x").value;
      const centerY = +$("field-crop-y").value;
      if (item.crop_keyframes.some((entry) => entry.center_x !== centerX || entry.center_y !== centerY)) {
        steps.push({ name: "timeline.set_crop_keyframes", args: { item_id: item.id, keyframes: item.crop_keyframes.map((entry) => ({ ...entry, center_x: centerX, center_y: centerY, locked: true })) } });
      }
    }
  }
  const gain = +$("field-gain").value;
  const muted = $("field-muted").checked;
  if (gain !== item.gain_db || muted !== item.muted) {
    steps.push({ name: "timeline.set_audio_gain", args: { item_id: item.id, gain_db: gain, muted } });
  }
  runCommands(steps, "Clip settings applied to the canonical project.");
};

$("caption-form").onsubmit = (event) => {
  event.preventDefault();
  const item = selectedItem();
  const steps = [];
  const text = $("field-caption-text").value.trim();
  const oldText = item.caption_words.map((word) => word.text).join(" ");
  if (text && text !== oldText) {
    const pieces = text.split(/\s+/);
    const firstTick = item.caption_words[0]?.start_ticks || 0;
    const lastTick = item.caption_words.at(-1)?.end_ticks || item.duration_ticks;
    const words = pieces.map((piece, index) => {
      const original = item.caption_words[index];
      const start_ticks = pieces.length === item.caption_words.length ? original.start_ticks : Math.round(firstTick + (lastTick-firstTick)*index/pieces.length);
      const end_ticks = pieces.length === item.caption_words.length ? original.end_ticks : Math.round(firstTick + (lastTick-firstTick)*(index+1)/pieces.length);
      return { id: original?.id || `edited_${index}`, text: piece, start_ticks, end_ticks, confidence: original?.confidence ?? null };
    });
    steps.push({ name: "timeline.set_caption_words", args: { item_id: item.id, words } });
  }
  steps.push({ name: "timeline.set_caption_style", args: {
    item_id: item.id, preset: $("field-caption-preset").value, position: $("field-caption-position").value,
    font_size: +$("field-caption-size").value, words_per_cue: +$("field-caption-words").value,
    font_family: $("field-caption-font").value.trim() || "Noto Sans",
    text_color: $("field-caption-color").value, highlight_color: $("field-caption-highlight").value,
    background_color: $("field-caption-background").value + "B8",
  } });
  runCommands(steps, "Caption content and style updated.");
};

function previewClipTransform(item, values) {
  const video = $("preview-video");
  video.style.opacity = values.opacity;
  video.style.transform = `translate(${values.x}px, ${values.y}px) scale(${values.scale}) rotate(${values.rotation}deg)`;
  updateTransformBox(item, values);
}

function installDirectTransformControls() {
  const box = $("transform-box");
  const monitor = $("monitor");
  const begin = (event, mode) => {
    const item = selectedItem();
    if (!item || item.kind !== "video" || state.busy) return;
    event.preventDefault();
    event.stopPropagation();
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);
    const startX = event.clientX;
    const startY = event.clientY;
    const initial = { x: item.x, y: item.y, scale: item.scale, rotation: item.rotation, opacity: item.opacity };
    let values = { ...initial };
    let changed = false;
    const center = () => {
      const rect = box.getBoundingClientRect();
      return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
    };
    const startCenter = center();
    const startAngle = Math.atan2(startY - startCenter.y, startX - startCenter.x) * 180 / Math.PI;
    target.onpointermove = (move) => {
      if (!target.hasPointerCapture(move.pointerId)) return;
      const dx = move.clientX - startX;
      const dy = move.clientY - startY;
      if (Math.abs(dx) + Math.abs(dy) < 2) return;
      changed = true;
      if (mode === "move") {
        values.x = Math.round(initial.x + dx * state.project.canvas.width / monitor.clientWidth);
        values.y = Math.round(initial.y + dy * state.project.canvas.height / monitor.clientHeight);
      } else if (mode === "resize") {
        const delta = (dx / monitor.clientWidth + dy / monitor.clientHeight) / 2;
        values.scale = Math.max(.05, Math.min(20, Math.round((initial.scale + delta * 2) * 1000) / 1000));
      } else {
        const current = center();
        const angle = Math.atan2(move.clientY - current.y, move.clientX - current.x) * 180 / Math.PI;
        values.rotation = Math.round((initial.rotation + angle - startAngle) * 10) / 10;
      }
      previewClipTransform(item, values);
    };
    target.onpointerup = (up) => {
      if (target.hasPointerCapture(up.pointerId)) target.releasePointerCapture(up.pointerId);
      target.onpointermove = null;
      target.onpointerup = null;
      if (!changed) return;
      runCommands([{ name: "timeline.set_clip_transform", args: { item_id: item.id, ...values } }], "Clip transform applied.");
    };
  };
  box.onpointerdown = (event) => {
    if (event.target === box) begin(event, "move");
  };
  $("resize-handle").onpointerdown = (event) => begin(event, "resize");
  $("rotate-handle").onpointerdown = (event) => begin(event, "rotate");
}

installDirectTransformControls();

$("play").onclick = () => state.sequencePlaying ? stopSequencePlayback() : startSequencePlayback();
$("jump-start").onclick = () => {
  stopSequencePlayback();
  setPlayhead(0, true);
};
$("playhead").oninput = (event) => { stopSequencePlayback(); setPlayhead(+event.target.value, true); };

$("undo").onclick = () => runCommands([{ name: "project.undo", args: {} }], "A compensating revision was created.");
$("split").onclick = () => {
  const item = selectedItem();
  if (!item || !["video", "audio"].includes(item.kind)) return toast("Select a video or audio clip to split.", true);
  const at = state.playheadTicks > item.start_ticks && state.playheadTicks < item.start_ticks + item.duration_ticks
    ? state.playheadTicks : item.start_ticks + Math.floor(item.duration_ticks / 2);
  runCommands([{ name: "timeline.split_clip", args: { item_id: item.id, at_ticks: at } }], "Clip split into stable timeline identities.");
};
$("delete-item").onclick = () => {
  const item = selectedItem();
  if (!item) return toast("Select a timeline item to delete.", true);
  if (!confirm(`Delete “${item.name}” from the timeline?`)) return;
  runCommands([{ name: "timeline.delete_item", args: { item_id: item.id } }], "Timeline item deleted; undo remains available.");
};
$("zoom-in").onclick = () => { $("zoom").value = Math.min(10, +$("zoom").value + 1); drawTimeline(); };
$("zoom-out").onclick = () => { $("zoom").value = Math.max(1, +$("zoom").value - 1); drawTimeline(); };
$("zoom").oninput = drawTimeline;

function renderStateLabel(stateName) {
  return stateName.replaceAll("_", " ").replace(/^./, (value) => value.toUpperCase());
}

async function watchRender(jobId, receiptId) {
  const terminal = new Set(["observed_success", "observed_failure", "execution_failed", "cancelled", "timeout", "interrupted"]);
  while (state.renderJobId === jobId) {
    const [job, receipt] = await Promise.all([api(`/api/jobs/${jobId}`), api(`/api/receipts/${receiptId}`)]);
    $("render-state").textContent = renderStateLabel(job.state);
    $("render-detail").textContent = job.error_detail || (job.state === "awaiting_observation" ? "Checking the encoded output" : "Rendering the frozen project revision");
    $("render-progress").value = job.progress;
    $("cancel-render").hidden = terminal.has(job.state);
    state.receipts = await api(`/api/projects/${state.projectId}/receipts`);
    drawReceipts();
    if (terminal.has(job.state)) {
      state.renderJobId = null;
      state.renderReceiptId = null;
      $("render").disabled = false;
      $("render").textContent = "Render";
      if (receipt.status === "observed_success" && receipt.payload.artifact_url) {
        state.resultUrl = receipt.payload.artifact_url;
        drawMonitor();
        toast("Verified output is ready in the program monitor.");
      } else {
        const finding = receipt.payload.observation?.findings?.find((entry) => !entry.passed);
        toast(finding?.summary || receipt.payload.stderr || renderStateLabel(receipt.status), true);
      }
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
}

$("render").onclick = async () => {
  if (state.busy) return;
  state.busy = true;
  $("render").disabled = true;
  $("render").textContent = "Queueing…";
  state.resultUrl = null;
  try {
    const receipt = await api(`/api/projects/${state.projectId}/renders`, { method: "POST", body: JSON.stringify({ project_revision: state.project.revision, request_id: requestId("render"), actor: "browser" }) });
    state.renderJobId = receipt.payload.job_id;
    state.renderReceiptId = receipt.id;
    $("render-dock").hidden = false;
    $("render-state").textContent = "Queued";
    $("render-detail").textContent = `Revision ${receipt.project_revision} is frozen for rendering`;
    $("render-progress").value = 0;
    $("cancel-render").hidden = false;
    $("render").textContent = "Rendering";
    watchRender(state.renderJobId, state.renderReceiptId).catch((error) => {
      state.renderJobId = null;
      $("render").disabled = false;
      $("render").textContent = "Render";
      toast(`Render status unavailable: ${error.message}`, true);
    });
  } catch (error) { toast(error.message, true); }
  finally {
    state.busy = false;
    if (!state.renderJobId) {
      $("render").disabled = false;
      $("render").textContent = "Render";
    }
  }
};

$("cancel-render").onclick = async () => {
  if (!state.renderJobId) return;
  try {
    await api(`/api/jobs/${state.renderJobId}/cancel`, { method: "POST", body: "{}" });
    $("render-detail").textContent = "Cancellation requested";
  } catch (error) { toast(error.message, true); }
};

async function loadShortDrafts() {
  const payload = await api(`/api/projects/${state.projectId}/suggestions?state=pending`);
  const container = $("shorts-results");
  container.innerHTML = payload.suggestions.map((draft) => {
    const evidence = draft.evidence;
    const components = evidence.score_components || {};
    const preview = `/api/projects/${state.projectId}/assets/${evidence.source_asset_id}/proxy#t=${seconds(evidence.start_ticks)},${seconds(evidence.end_ticks)}`;
    return `<article class="short-draft"><header><strong>${Math.round((draft.confidence || 0) * 100)} Clip Score</strong><span>${timeLabel(evidence.end_ticks - evidence.start_ticks)}</span></header><video class="short-preview" src="${preview}" preload="metadata" controls playsinline></video><p dir="auto">${escapeHtml(evidence.text)}</p><small>${escapeHtml(draft.reason)}</small><div class="score-pills"><span>Hook ${Math.round(components.hook || 0)}</span><span>Flow ${Math.round(components.flow || 0)}</span><span>Value ${Math.round(components.value || 0)}</span></div>${(evidence.warnings || []).map((warning) => `<em>${escapeHtml(warning)}</em>`).join("")}<footer><button data-reject-short="${draft.id}">Reject</button><button class="primary" data-accept-short="${draft.id}">Create project</button></footer></article>`;
  }).join("") || `<div class="empty">No pending drafts yet.</div>`;
  container.querySelectorAll("[data-accept-short]").forEach((button) => {
    button.onclick = async () => {
      button.disabled = true;
      try {
        const result = await api(`/api/suggestions/${button.dataset.acceptShort}/accept`, { method: "POST", body: JSON.stringify({ request_id: requestId("accept-short"), actor: "browser", expected_state: "pending" }) });
        state.projectId = result.project.id;
        $("shorts-dialog").close();
        await load({ projects: true });
        toast("Editable short project created from the frozen source revision.");
      } catch (error) { button.disabled = false; toast(error.message, true); }
    };
  });
  container.querySelectorAll("[data-reject-short]").forEach((button) => {
    button.onclick = async () => {
      await api(`/api/suggestions/${button.dataset.rejectShort}/reject`, { method: "POST", body: JSON.stringify({ request_id: requestId("reject-short"), actor: "browser", expected_state: "pending" }) });
      await loadShortDrafts();
    };
  });
}

async function watchShorts(jobId) {
  const terminal = new Set(["observed_success", "execution_failed", "cancelled", "interrupted", "timeout"]);
  while (state.shortsJobId === jobId) {
    const job = await api(`/api/jobs/${jobId}`);
    $("shorts-stage").textContent = renderStateLabel(job.stage || job.state);
    $("shorts-detail").textContent = job.status_message || job.error_detail || "Analyzing source";
    $("shorts-progress-bar").value = job.progress;
    if (terminal.has(job.state)) {
      state.shortsJobId = null;
      $("cancel-shorts").hidden = true;
      $("shorts-form").querySelector("button[type=submit]").disabled = false;
      if (job.state === "observed_success") await loadShortDrafts();
      else toast(job.error_detail || renderStateLabel(job.state), true);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

$("create-shorts").onclick = async () => {
  const videos = state.project.assets.filter((asset) => asset.kind === "video" && asset.intake_status === "observed_valid" && asset.source_kind !== "derived");
  $("shorts-asset").innerHTML = videos.map((asset) => `<option value="${asset.id}">${escapeHtml(asset.name)} · ${timeLabel(asset.duration_ticks)}</option>`).join("");
  $("shorts-form").hidden = !videos.length;
  if (!videos.length) $("shorts-results").innerHTML = `<div class="empty">Import an observed video before creating shorts.</div>`;
  else await loadShortDrafts();
  $("shorts-dialog").showModal();
};
$("close-shorts").onclick = () => $("shorts-dialog").close();
$("shorts-form").onsubmit = async (event) => {
  event.preventDefault();
  const submit = event.submitter;
  submit.disabled = true;
  try {
    const job = await api(`/api/projects/${state.projectId}/shorts/jobs`, { method: "POST", body: JSON.stringify({
      source_revision: state.project.revision, asset_id: $("shorts-asset").value,
      prompt: $("shorts-prompt").value.trim() || null, language: $("shorts-language").value,
      candidate_count: +$("shorts-count").value, min_duration_ticks: +$("shorts-min").value * TICKS,
      max_duration_ticks: +$("shorts-max").value * TICKS,
    }) });
    state.shortsJobId = job.id;
    $("shorts-progress").hidden = false;
    $("cancel-shorts").hidden = false;
    watchShorts(job.id).catch((error) => toast(error.message, true));
  } catch (error) { submit.disabled = false; toast(error.message, true); }
};
$("cancel-shorts").onclick = async () => {
  if (state.shortsJobId) await api(`/api/jobs/${state.shortsJobId}/cancel`, { method: "POST", body: "{}" });
};

$("reset").onclick = async () => {
  await api("/api/projects/demo/reset", { method: "POST", body: "{}" });
  state.playheadTicks = 0;
  toast("Fixture restored to its deliberately clipped title.");
  await load();
};

$("project-picker").onchange = async (event) => {
  stopSequencePlayback();
  state.projectId = event.target.value;
  state.playheadTicks = 0;
  state.previewItemId = null;
  state.resultUrl = null;
  await load();
};
$("new-project").onclick = async () => {
  const name = prompt("Project name", "New SAG Video");
  if (!name?.trim()) return;
  const result = await api("/api/projects", { method: "POST", body: JSON.stringify({ name: name.trim(), preset: "landscape_1080p" }) });
  state.projectId = result.project.id;
  await load({ projects: true });
  toast("Project created. Import media to begin.");
};

$("import-media").onclick = () => $("media-file").click();
$("media-file").onchange = async () => {
  const file = $("media-file").files[0];
  if (!file || state.busy) return;
  state.busy = true;
  $("import-media").disabled = true;
  try {
    const form = new FormData();
    form.append("file", file);
    form.append("request_id", requestId("upload"));
    form.append("actor", "browser");
    const result = await api(`/api/projects/${state.projectId}/assets/uploads`, { method: "POST", body: form });
    if (result.receipt.status === "observed_success") toast(`${result.asset.name} imported, probed, and proxied.`);
    else toast(result.receipt.payload.observation?.findings?.[0]?.summary || "Media intake failed observation.", true);
    await load();
  } catch (error) { toast(error.message, true); }
  finally { state.busy = false; $("import-media").disabled = false; $("media-file").value = ""; }
};

async function checkPairStatus() {
  if (!state.projectId) return;
  try {
    const status = await api(`/api/pairing/status/${state.projectId}`);
    const actor = status.actors[0]?.actor_name;
    $("pair").textContent = status.connected ? `${actor} connected` : "Pair";
    $("pair").classList.toggle("connected", status.connected);
    if ($("pair-dialog").open) {
      $("pair-status").textContent = status.connected
        ? `${actor} is connected. The new code remains available until it is used or expires.`
        : "Waiting for a terminal to use this code.";
      $("pair-status").classList.toggle("connected", status.connected);
    }
  } catch { /* Pair status is advisory. */ }
}
$("pair").onclick = async () => {
  try {
    const result = await api("/api/pairing/start", { method: "POST", body: JSON.stringify({ workspace_id: state.projectId }) });
    $("pair-code").textContent = result.code;
    $("pair-code-command").textContent = result.code;
    $("pair-url").textContent = location.origin;
    $("pair-status").textContent = "Waiting for a terminal to use this code.";
    $("pair-status").classList.remove("connected");
    $("pair-dialog").showModal();
    clearInterval(state.pairTimer);
    state.pairTimer = setInterval(checkPairStatus, 1500);
  } catch (error) { toast(error.message, true); }
};
$("close-dialog").onclick = () => { $("pair-dialog").close(); clearInterval(state.pairTimer); };
$("copy-pair-command").onclick = async () => {
  try {
    await navigator.clipboard.writeText($("pair-command").textContent.trim());
    $("copy-pair-command").textContent = "Copied";
    toast("Pairing command copied.");
    setTimeout(() => { $("copy-pair-command").textContent = "Copy command"; }, 1800);
  } catch {
    toast("Clipboard access failed. Press and hold the command to copy it.", true);
  }
};

function activateMobilePane(button, scroll = true) {
  document.querySelectorAll("[data-pane]").forEach((entry) => {
    const active = entry === button;
    entry.classList.toggle("active", active);
    entry.setAttribute("aria-selected", String(active));
    if (active) entry.setAttribute("aria-current", "true");
    else entry.removeAttribute("aria-current");
  });
  document.querySelectorAll(".workspace > .panel").forEach((pane) => {
    pane.classList.toggle("mobile-pane-active", pane.id === button.dataset.pane);
  });
  sessionStorage.setItem("sag-video-mobile-pane", button.dataset.pane);
  if (scroll && matchMedia("(max-width: 800px)").matches) {
    window.scrollTo({
      top: 0,
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  }
  if (button.dataset.pane === "stage" && state.project) requestAnimationFrame(drawMonitor);
}

const paneButtons = [...document.querySelectorAll("[data-pane]")];
paneButtons.forEach((button) => { button.onclick = () => activateMobilePane(button); });
const rememberedPane = sessionStorage.getItem("sag-video-mobile-pane");
activateMobilePane(paneButtons.find((button) => button.dataset.pane === rememberedPane) || paneButtons[0], false);
window.addEventListener("resize", () => state.project && drawMonitor());

load({ projects: true }).catch((error) => toast(error.message, true));
setInterval(async () => {
  if (!state.busy && state.project) {
    try {
      const fresh = await api(`/api/projects/${state.projectId}`);
      if (fresh.project.revision !== state.project.revision) await load();
    } catch { /* Reconnect on the next interval. */ }
  }
}, 2500);
