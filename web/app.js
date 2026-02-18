const state = {
  apiBase: "",
};

function resolveBaseUrl() {
  const stored = localStorage.getItem("apiBase");
  if (stored && stored.trim()) {
    return stored.trim().replace(/\/$/, "");
  }
  return window.location.origin.replace(/\/$/, "");
}

function setOutput(el, payload) {
  if (!el) return;
  if (typeof payload === "string") {
    el.textContent = payload;
    return;
  }
  el.textContent = JSON.stringify(payload, null, 2);
}

async function request(method, path, body) {
  const url = `${state.apiBase}${path}`;
  const init = { method, headers: {} };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(url, init);
  const text = await res.text();
  let data = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_err) {
    // non-json response fallback
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

function bindControls() {
  const apiBaseInput = document.querySelector("#apiBase");
  const saveBaseBtn = document.querySelector("#saveBaseBtn");
  const healthBtn = document.querySelector("#healthBtn");
  const redisBtn = document.querySelector("#redisBtn");
  const channelForm = document.querySelector("#channelForm");
  const videoForm = document.querySelector("#videoForm");
  const interactionForm = document.querySelector("#interactionForm");
  const recommendationForm = document.querySelector("#recommendationForm");

  const systemOutput = document.querySelector("#systemOutput");
  const channelOutput = document.querySelector("#channelOutput");
  const videoOutput = document.querySelector("#videoOutput");
  const interactionOutput = document.querySelector("#interactionOutput");
  const recommendationList = document.querySelector("#recommendationList");

  state.apiBase = resolveBaseUrl();
  apiBaseInput.value = state.apiBase;

  saveBaseBtn.addEventListener("click", () => {
    state.apiBase = apiBaseInput.value.trim().replace(/\/$/, "");
    localStorage.setItem("apiBase", state.apiBase);
    setOutput(systemOutput, { message: "Saved API base URL", apiBase: state.apiBase });
  });

  healthBtn.addEventListener("click", async () => {
    try {
      setOutput(systemOutput, await request("GET", "/health"));
    } catch (err) {
      setOutput(systemOutput, `Health check failed: ${err.message}`);
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

  recommendationForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(recommendationForm);
    const userId = String(formData.get("user_id") || "");
    const k = parseMaybeInt(formData.get("k")) || 20;
    try {
      const data = await request("GET", `/recommendations?user_id=${encodeURIComponent(userId)}&k=${k}`);
      renderRecommendations(recommendationList, data);
    } catch (err) {
      recommendationList.innerHTML = `<p>Recommendation fetch failed: ${err.message}</p>`;
    }
  });
}

bindControls();
