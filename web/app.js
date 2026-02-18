const HISTORY_KEY = "recHistory";

const state = {
  apiBase: "",
  apiToken: "",
  history: [],
};

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

function setOutput(el, payload) {
  if (!el) return;
  if (typeof payload === "string") {
    el.textContent = payload;
    return;
  }
  el.textContent = JSON.stringify(payload, null, 2);
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

async function request(method, path, body) {
  const url = `${state.apiBase}${path}`;
  const init = { method, headers: buildHeaders(body !== undefined ? "application/json" : null) };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }
  const res = await fetch(url, init);
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
  const init = { method, headers: buildHeaders(contentType), body };
  const res = await fetch(url, init);
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

async function readFileText(file) {
  return await file.text();
}

async function readFileArrayBuffer(file) {
  return await file.arrayBuffer();
}

function bindControls() {
  const apiBaseInput = document.querySelector("#apiBase");
  const apiTokenInput = document.querySelector("#apiToken");
  const saveBaseBtn = document.querySelector("#saveBaseBtn");
  const healthBtn = document.querySelector("#healthBtn");
  const redisBtn = document.querySelector("#redisBtn");
  const channelForm = document.querySelector("#channelForm");
  const videoForm = document.querySelector("#videoForm");
  const interactionForm = document.querySelector("#interactionForm");
  const takeoutForm = document.querySelector("#takeoutForm");
  const recommendationForm = document.querySelector("#recommendationForm");
  const clearHistoryBtn = document.querySelector("#clearHistoryBtn");
  const connectionStatus = document.querySelector("#connectionStatus");

  const systemOutput = document.querySelector("#systemOutput");
  const channelOutput = document.querySelector("#channelOutput");
  const videoOutput = document.querySelector("#videoOutput");
  const interactionOutput = document.querySelector("#interactionOutput");
  const takeoutOutput = document.querySelector("#takeoutOutput");
  const recommendationList = document.querySelector("#recommendationList");
  const historyTableBody = document.querySelector("#historyTableBody");

  state.apiBase = resolveBaseUrl();
  state.apiToken = resolveApiToken();
  state.history = loadHistory();
  apiBaseInput.value = state.apiBase;
  apiTokenInput.value = state.apiToken;
  renderHistory(historyTableBody);

  saveBaseBtn.addEventListener("click", () => {
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
    try {
      const data = await request("GET", "/health");
      setOutput(systemOutput, data);
      setConnectionStatus(connectionStatus, data?.status === "ok", data?.status || "unknown");
    } catch (err) {
      setOutput(systemOutput, `Health check failed: ${err.message}`);
      setConnectionStatus(connectionStatus, false, "health check failed");
    }
  });

  redisBtn.addEventListener("click", async () => {
    try {
      setOutput(systemOutput, await request("GET", "/redis-ping"));
    } catch (err) {
      setOutput(systemOutput, `Redis check failed: ${err.message}`);
    }
  });

  channelForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(channelForm);
    const payload = {
      channel_id: formData.get("channel_id"),
      title: formData.get("title"),
    };
    try {
      setOutput(channelOutput, await request("POST", "/channels/upsert", payload));
    } catch (err) {
      setOutput(channelOutput, `Upsert failed: ${err.message}`);
    }
  });

  videoForm.addEventListener("submit", async (event) => {
    event.preventDefault();
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
      setOutput(videoOutput, `Upsert failed: ${err.message}`);
    }
  });

  interactionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
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
      setOutput(interactionOutput, `Interaction failed: ${err.message}`);
    }
  });

  takeoutForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(takeoutForm);
    const userId = String(formData.get("user_id") || "").trim();
    const sourceFileInput = String(formData.get("source_file") || "").trim();
    const fileType = String(formData.get("file_type") || "zip").toLowerCase();
    const file = formData.get("file");
    if (!(file instanceof File)) {
      setOutput(takeoutOutput, "No file selected.");
      return;
    }

    const sourceFile = encodeURIComponent(toSafeFileName(sourceFileInput, file.name));
    const userParam = encodeURIComponent(userId);

    try {
      let response;
      if (fileType === "json") {
        const body = await readFileText(file);
        response = await requestRaw(
          "POST",
          `/ingest/google-takeout/file?user_id=${userParam}&source_file=${sourceFile}`,
          body,
          "application/json",
        );
      } else {
        const body = await readFileArrayBuffer(file);
        response = await requestRaw(
          "POST",
          `/ingest/google-takeout/zip?user_id=${userParam}&source_file=${sourceFile}`,
          body,
          "application/zip",
        );
      }
      setOutput(takeoutOutput, response);
    } catch (err) {
      const message = String(err.message || "");
      if (message.includes("disabled by configuration")) {
        setOutput(
          takeoutOutput,
          "Takeout import is disabled on backend. Start API with ENABLE_TAKEOUT_IMPORT=true to use this feature.",
        );
      } else {
        setOutput(takeoutOutput, `Takeout import failed: ${message}`);
      }
    }
  });

  recommendationForm.addEventListener("submit", async (event) => {
    event.preventDefault();
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
      recommendationList.innerHTML = `<p>Recommendation fetch failed: ${err.message}</p>`;
    }
  });

  clearHistoryBtn.addEventListener("click", () => {
    state.history = [];
    saveHistory();
    renderHistory(historyTableBody);
  });

  healthBtn.click();
}

bindControls();
