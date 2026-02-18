const HISTORY_KEY = "recHistory";
const MODE_KEY = "uiMode";

const state = {
  apiBase: "",
  apiToken: "",
  history: [],
  globalErrorEl: null,
  mode: "demo",
};

const DEMO_CHANNELS = [
  { channel_id: "UC_ML_01", title: "ML Core" },
  { channel_id: "UC_ML_02", title: "Data Infra" },
];

const DEMO_VIDEOS = [
  {
    video_id: "VID_ML_001",
    channel_id: "UC_ML_01",
    title: "Intro to Recommender Systems",
    description: "Overview of collaborative and content based methods.",
    tags: ["recommender", "ml", "intro"],
    duration_seconds: 600,
  },
  {
    video_id: "VID_ML_002",
    channel_id: "UC_ML_01",
    title: "TF-IDF for Content Ranking",
    description: "Using tfidf vectors for ranking videos.",
    tags: ["tfidf", "nlp", "ranking"],
    duration_seconds: 720,
  },
  {
    video_id: "VID_ML_003",
    channel_id: "UC_ML_01",
    title: "Cosine Similarity Explained",
    description: "Vector similarity for recommendation and retrieval.",
    tags: ["cosine", "vectors", "ml"],
    duration_seconds: 540,
  },
  {
    video_id: "VID_ML_004",
    channel_id: "UC_ML_02",
    title: "FastAPI Production Patterns",
    description: "Production backend patterns and deployment strategy.",
    tags: ["fastapi", "backend", "deploy"],
    duration_seconds: 800,
  },
  {
    video_id: "VID_ML_005",
    channel_id: "UC_ML_02",
    title: "Postgres Indexing Deep Dive",
    description: "Database indexing strategies for low-latency systems.",
    tags: ["postgres", "database", "indexing"],
    duration_seconds: 900,
  },
  {
    video_id: "VID_ML_006",
    channel_id: "UC_ML_02",
    title: "Redis Caching for APIs",
    description: "Cache patterns and invalidation techniques.",
    tags: ["redis", "cache", "api"],
    duration_seconds: 670,
  },
];

const DEMO_INTERACTIONS = [
  { video_id: "VID_ML_001", event_type: "watch", watch_seconds: 420 },
  { video_id: "VID_ML_002", event_type: "watch", watch_seconds: 510 },
  { video_id: "VID_ML_003", event_type: "like", watch_seconds: null },
  { video_id: "VID_ML_006", event_type: "click", watch_seconds: null },
];

function byId(id) {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing UI element: #${id}`);
  }
  return element;
}

function resolveBaseUrl() {
  const stored = localStorage.getItem("apiBase");
  if (stored && stored.trim()) {
    return stored.trim().replace(/\/$/, "");
  }
  return window.location.origin.replace(/\/$/, "");
}

function resolveApiToken() {
  const stored = localStorage.getItem("apiToken");
  return stored ? stored.trim() : "";
}

function resolveMode() {
  const stored = localStorage.getItem(MODE_KEY);
  return stored === "takeout" ? "takeout" : "demo";
}

function saveMode(mode) {
  localStorage.setItem(MODE_KEY, mode);
}

function safeErrorMessage(err) {
  if (!err) return "Unknown error";
  if (typeof err === "string") return err;
  if (err instanceof Error) return err.message;
  try {
    return JSON.stringify(err);
  } catch (_jsonErr) {
    return "Unknown error";
  }
}

function setGlobalError(message) {
  const el = state.globalErrorEl;
  if (!el) return;
  el.textContent = message;
  el.classList.remove("hidden");
}

function clearGlobalError() {
  const el = state.globalErrorEl;
  if (!el) return;
  el.textContent = "";
  el.classList.add("hidden");
}

function markOutput(el, isError) {
  if (!el) return;
  el.classList.toggle("error-output", Boolean(isError));
}

function setOutput(el, payload) {
  if (!el) return;
  markOutput(el, false);
  if (typeof payload === "string") {
    el.textContent = payload;
    return;
  }
  el.textContent = JSON.stringify(payload, null, 2);
}

function setErrorOutput(el, message) {
  if (!el) return;
  markOutput(el, true);
  el.textContent = message;
  setGlobalError(message);
}

function setConnectionStatus(el, ok, message) {
  if (!el) return;
  el.classList.remove("ok", "bad");
  if (ok === true) {
    el.classList.add("ok");
  } else if (ok === false) {
    el.classList.add("bad");
  }
  el.textContent = `Status: ${message}`;
}

function buildHeaders(contentType) {
  const headers = {};
  if (contentType) {
    headers["Content-Type"] = contentType;
  }
  if (state.apiToken) {
    headers.Authorization = `Bearer ${state.apiToken}`;
  }
  return headers;
}

async function fetchWithTimeout(url, init, timeoutMs = 45000) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function request(method, path, body) {
  const url = `${state.apiBase}${path}`;
  const init = { method, headers: buildHeaders(body !== undefined ? "application/json" : null) };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetchWithTimeout(url, init);
  } catch (err) {
    if (err?.name === "AbortError") {
      throw new Error(`Request timed out: ${method} ${path}`);
    }
    throw new Error(`Network error calling ${url}`);
  }

  const text = await res.text();
  let data = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_err) {
    // non-json fallback
  }
  if (!res.ok) {
    throw new Error(typeof data === "string" ? data : JSON.stringify(data));
  }
  return data;
}

async function requestRaw(method, path, body, contentType) {
  const url = `${state.apiBase}${path}`;
  let res;
  try {
    res = await fetchWithTimeout(url, {
      method,
      headers: buildHeaders(contentType),
      body,
    });
  } catch (err) {
    if (err?.name === "AbortError") {
      throw new Error(`Upload timed out: ${method} ${path}`);
    }
    throw new Error(`Network error calling ${url}`);
  }

  const text = await res.text();
  let data = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_err) {
    // non-json fallback
  }
  if (!res.ok) {
    throw new Error(typeof data === "string" ? data : JSON.stringify(data));
  }
  return data;
}

function parseTags(raw) {
  return raw
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

function parseMaybeInt(raw) {
  if (!raw || !String(raw).trim()) return null;
  const value = Number.parseInt(String(raw), 10);
  return Number.isNaN(value) ? null : value;
}

function formatTime(isoLike) {
  const d = new Date(isoLike);
  if (Number.isNaN(d.getTime())) return String(isoLike);
  return d.toLocaleString();
}

function renderRecommendations(target, response) {
  target.innerHTML = "";
  const items = response?.items || [];
  if (!items.length) {
    target.innerHTML = "<p>No recommendations available.</p>";
    return;
  }

  for (const item of items) {
    const reasons = (item.reasons || []).map((r) => `<li>${r}</li>`).join("");
    const card = document.createElement("article");
    card.className = "rec-item";
    card.innerHTML = `
      <div class="video-id">${item.video_id}</div>
      <div>Score: ${item.score}</div>
      <ul>${reasons}</ul>
    `;
    target.appendChild(card);
  }
}

function loadHistory() {
  const raw = localStorage.getItem(HISTORY_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (_err) {
    return [];
  }
}

function saveHistory() {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(state.history));
}

function addHistoryEntry(entry) {
  state.history.unshift(entry);
  state.history = state.history.slice(0, 50);
  saveHistory();
}

function renderHistory(target) {
  target.innerHTML = "";
  if (!state.history.length) {
    target.innerHTML = `<tr><td colspan="5">No history yet.</td></tr>`;
    return;
  }

  for (const row of state.history) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${formatTime(row.timestamp)}</td>
      <td>${row.user_id}</td>
      <td>${row.k}</td>
      <td>${row.item_count}</td>
      <td>${row.top_video_id || "-"}</td>
    `;
    target.appendChild(tr);
  }
}

function toSafeFileName(fileName, fallback) {
  const value = (fileName || fallback || "").trim();
  return value || fallback;
}

async function loadDemoData(userId) {
  for (const channel of DEMO_CHANNELS) {
    await request("POST", "/channels/upsert", channel);
  }
  for (const video of DEMO_VIDEOS) {
    await request("POST", "/videos/upsert", video);
  }
  for (const event of DEMO_INTERACTIONS) {
    await request("POST", "/interactions", {
      user_id: userId,
      video_id: event.video_id,
      event_type: event.event_type,
      watch_seconds: event.watch_seconds,
      metadata: { source: "ui_demo_seed" },
    });
  }
  return {
    channels_upserted: DEMO_CHANNELS.length,
    videos_upserted: DEMO_VIDEOS.length,
    interactions_logged: DEMO_INTERACTIONS.length,
    user_id: userId,
  };
}

function bindControls() {
  state.globalErrorEl = byId("globalError");

  const apiBaseInput = byId("apiBase");
  const apiTokenInput = byId("apiToken");
  const saveBaseBtn = byId("saveBaseBtn");
  const healthBtn = byId("healthBtn");
  const redisBtn = byId("redisBtn");
  const restartBtn = byId("restartBtn");
  const channelForm = byId("channelForm");
  const videoForm = byId("videoForm");
  const interactionForm = byId("interactionForm");
  const takeoutForm = byId("takeoutForm");
  const demoForm = byId("demoForm");
  const recommendationForm = byId("recommendationForm");
  const clearHistoryBtn = byId("clearHistoryBtn");
  const connectionStatus = byId("connectionStatus");
  const modeDemoBtn = byId("modeDemoBtn");
  const modeTakeoutBtn = byId("modeTakeoutBtn");
  const takeoutCard = byId("takeoutCard");
  const demoCard = byId("demoCard");

  const systemOutput = byId("systemOutput");
  const channelOutput = byId("channelOutput");
  const videoOutput = byId("videoOutput");
  const interactionOutput = byId("interactionOutput");
  const takeoutOutput = byId("takeoutOutput");
  const demoOutput = byId("demoOutput");
  const recommendationList = byId("recommendationList");
  const historyTableBody = byId("historyTableBody");

  state.apiBase = resolveBaseUrl();
  state.apiToken = resolveApiToken();
  state.history = loadHistory();
  state.mode = resolveMode();
  apiBaseInput.value = state.apiBase;
  apiTokenInput.value = state.apiToken;
  renderHistory(historyTableBody);

  function applyMode(mode) {
    state.mode = mode === "takeout" ? "takeout" : "demo";
    saveMode(state.mode);

    modeDemoBtn.classList.toggle("active", state.mode === "demo");
    modeTakeoutBtn.classList.toggle("active", state.mode === "takeout");
    demoCard.classList.toggle("hidden-card", state.mode === "takeout");
    takeoutCard.classList.toggle("hidden-card", state.mode === "demo");
  }

  modeDemoBtn.addEventListener("click", () => {
    clearGlobalError();
    applyMode("demo");
  });

  modeTakeoutBtn.addEventListener("click", () => {
    clearGlobalError();
    applyMode("takeout");
  });

  saveBaseBtn.addEventListener("click", () => {
    clearGlobalError();
    state.apiBase = apiBaseInput.value.trim().replace(/\/$/, "");
    state.apiToken = apiTokenInput.value.trim();
    localStorage.setItem("apiBase", state.apiBase);
    localStorage.setItem("apiToken", state.apiToken);
    setOutput(systemOutput, {
      message: "Saved API client settings",
      apiBase: state.apiBase,
      auth: state.apiToken ? "Bearer token configured" : "No token",
    });
    setConnectionStatus(connectionStatus, null, "saved, run Check Health");
  });

  healthBtn.addEventListener("click", async () => {
    clearGlobalError();
    try {
      const data = await request("GET", "/health");
      setOutput(systemOutput, data);
      setConnectionStatus(connectionStatus, data?.status === "ok", data?.status || "unknown");
    } catch (err) {
      const message = `Health check failed: ${safeErrorMessage(err)}`;
      setErrorOutput(systemOutput, message);
      setConnectionStatus(connectionStatus, false, "health check failed");
    }
  });

  redisBtn.addEventListener("click", async () => {
    clearGlobalError();
    try {
      setOutput(systemOutput, await request("GET", "/redis-ping"));
    } catch (err) {
      setErrorOutput(systemOutput, `Redis check failed: ${safeErrorMessage(err)}`);
    }
  });

  restartBtn.addEventListener("click", async () => {
    clearGlobalError();
    restartBtn.disabled = true;
    setOutput(systemOutput, "Requesting API restart...");
    try {
      const data = await request("POST", "/admin/restart");
      setOutput(systemOutput, data);
      setConnectionStatus(connectionStatus, null, "restart requested");
    } catch (err) {
      setErrorOutput(systemOutput, `Restart failed: ${safeErrorMessage(err)}`);
    } finally {
      window.setTimeout(() => {
        restartBtn.disabled = false;
      }, 1200);
    }
  });

  channelForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearGlobalError();
    const formData = new FormData(channelForm);
    const payload = {
      channel_id: formData.get("channel_id"),
      title: formData.get("title"),
    };
    try {
      setOutput(channelOutput, await request("POST", "/channels/upsert", payload));
    } catch (err) {
      setErrorOutput(channelOutput, `Upsert failed: ${safeErrorMessage(err)}`);
    }
  });

  videoForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearGlobalError();
    const formData = new FormData(videoForm);
    const payload = {
      video_id: formData.get("video_id"),
      channel_id: formData.get("channel_id"),
      title: formData.get("title"),
      description: formData.get("description") || "",
      tags: parseTags(String(formData.get("tags") || "")),
      duration_seconds: parseMaybeInt(formData.get("duration_seconds")),
    };
    try {
      setOutput(videoOutput, await request("POST", "/videos/upsert", payload));
    } catch (err) {
      setErrorOutput(videoOutput, `Upsert failed: ${safeErrorMessage(err)}`);
    }
  });

  interactionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearGlobalError();
    const formData = new FormData(interactionForm);
    const payload = {
      user_id: formData.get("user_id"),
      video_id: formData.get("video_id"),
      event_type: formData.get("event_type"),
      watch_seconds: parseMaybeInt(formData.get("watch_seconds")),
    };
    try {
      setOutput(interactionOutput, await request("POST", "/interactions", payload));
    } catch (err) {
      setErrorOutput(interactionOutput, `Interaction failed: ${safeErrorMessage(err)}`);
    }
  });

  takeoutForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearGlobalError();
    const submitBtn = takeoutForm.querySelector("button[type='submit']");
    const formData = new FormData(takeoutForm);
    const userId = String(formData.get("user_id") || "").trim();
    const sourceFileInput = String(formData.get("source_file") || "").trim();
    const fileType = String(formData.get("file_type") || "zip").toLowerCase();
    const file = formData.get("file");
    if (!(file instanceof File)) {
      setErrorOutput(takeoutOutput, "No file selected.");
      return;
    }

    const sourceFile = encodeURIComponent(toSafeFileName(sourceFileInput, file.name));
    const userParam = encodeURIComponent(userId);
    setOutput(takeoutOutput, "Uploading and importing file...");
    if (submitBtn) submitBtn.disabled = true;

    try {
      let response;
      if (fileType === "json") {
        const body = await file.text();
        response = await requestRaw(
          "POST",
          `/ingest/google-takeout/file?user_id=${userParam}&source_file=${sourceFile}`,
          body,
          "application/json",
        );
      } else {
        const body = await file.arrayBuffer();
        response = await requestRaw(
          "POST",
          `/ingest/google-takeout/zip?user_id=${userParam}&source_file=${sourceFile}`,
          body,
          "application/zip",
        );
      }
      setOutput(takeoutOutput, response);
    } catch (err) {
      const message = safeErrorMessage(err);
      if (message.includes("disabled by configuration")) {
        setErrorOutput(
          takeoutOutput,
          "Takeout import is disabled on backend. Start API with ENABLE_TAKEOUT_IMPORT=true to use this feature.",
        );
      } else {
        setErrorOutput(takeoutOutput, `Takeout import failed: ${message}`);
      }
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });

  demoForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearGlobalError();
    const submitBtn = demoForm.querySelector("button[type='submit']");
    const formData = new FormData(demoForm);
    const userId = String(formData.get("user_id") || "").trim();
    const recUserInput = recommendationForm.querySelector("input[name='user_id']");
    const recKInput = recommendationForm.querySelector("input[name='k']");
    const k = parseMaybeInt(recKInput ? recKInput.value : "20") || 20;

    setOutput(demoOutput, "Loading demo dataset...");
    if (submitBtn) submitBtn.disabled = true;
    try {
      const summary = await loadDemoData(userId);
      const recData = await request("GET", `/recommendations?user_id=${encodeURIComponent(userId)}&k=${k}`);
      renderRecommendations(recommendationList, recData);
      addHistoryEntry({
        timestamp: new Date().toISOString(),
        user_id: userId,
        k,
        item_count: Array.isArray(recData?.items) ? recData.items.length : 0,
        top_video_id: recData?.items?.[0]?.video_id || null,
      });
      renderHistory(historyTableBody);
      setOutput(demoOutput, {
        status: "ok",
        ...summary,
        recommendations_fetched: Array.isArray(recData?.items) ? recData.items.length : 0,
      });
      if (recUserInput) {
        recUserInput.value = userId;
      }
    } catch (err) {
      setErrorOutput(demoOutput, `Demo load failed: ${safeErrorMessage(err)}`);
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });

  recommendationForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearGlobalError();
    const formData = new FormData(recommendationForm);
    const userId = String(formData.get("user_id") || "");
    const k = parseMaybeInt(formData.get("k")) || 20;
    try {
      const data = await request("GET", `/recommendations?user_id=${encodeURIComponent(userId)}&k=${k}`);
      renderRecommendations(recommendationList, data);
      addHistoryEntry({
        timestamp: new Date().toISOString(),
        user_id: userId,
        k,
        item_count: Array.isArray(data?.items) ? data.items.length : 0,
        top_video_id: data?.items?.[0]?.video_id || null,
      });
      renderHistory(historyTableBody);
    } catch (err) {
      recommendationList.innerHTML = `<p class="hint">Recommendation fetch failed: ${safeErrorMessage(err)}</p>`;
      setGlobalError(`Recommendation fetch failed: ${safeErrorMessage(err)}`);
    }
  });

  clearHistoryBtn.addEventListener("click", () => {
    state.history = [];
    saveHistory();
    renderHistory(historyTableBody);
  });

  healthBtn.click();
  applyMode(state.mode);
}

window.addEventListener("error", (event) => {
  setGlobalError(`UI error: ${safeErrorMessage(event.error || event.message)}`);
});

window.addEventListener("unhandledrejection", (event) => {
  setGlobalError(`Unhandled async error: ${safeErrorMessage(event.reason)}`);
});

try {
  bindControls();
} catch (err) {
  const fallback = document.getElementById("globalError");
  if (fallback) {
    fallback.classList.remove("hidden");
    fallback.textContent = `Failed to initialize UI: ${safeErrorMessage(err)}`;
  }
  window.alert(`Failed to initialize UI. Hard refresh the page (Ctrl+F5).\n\n${safeErrorMessage(err)}`);
  // eslint-disable-next-line no-console
  console.error(err);
}
