const STORAGE_KEY = "chatbot-tester-settings";

const DEFAULTS = {
  apiBaseUrl: "http://127.0.0.1:8000",
  appName: "investor_search_agent",
  userId: "local_user",
  sessionId: "",
  token: "",
};

const els = {
  chatLog: document.getElementById("chat-log"),
  chatForm: document.getElementById("chat-form"),
  userInput: document.getElementById("user-input"),
  sendBtn: document.getElementById("send-btn"),
  status: document.getElementById("status"),
  settingsPanel: document.getElementById("settings-panel"),
  settingsToggle: document.getElementById("settings-toggle"),
  apiBaseUrl: document.getElementById("api-base-url"),
  appName: document.getElementById("app-name"),
  userId: document.getElementById("user-id"),
  sessionId: document.getElementById("session-id"),
  apiToken: document.getElementById("api-token"),
  saveSettings: document.getElementById("save-settings"),
  testConnection: document.getElementById("test-connection"),
  clearChat: document.getElementById("clear-chat"),
};

/** @type {{ role: "user" | "assistant", content: string, rows?: Record<string, unknown>[], count?: number, page?: { limit: number, offset: number } | null }[]} */
let conversation = [];
let isSending = false;

function createSessionId() {
  return `session_${Date.now()}`;
}

function loadSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const settings = raw ? { ...DEFAULTS, ...JSON.parse(raw) } : { ...DEFAULTS };
    settings.sessionId = createSessionId();
    return settings;
  } catch {
    return { ...DEFAULTS, sessionId: createSessionId() };
  }
}

function saveSettingsToStorage() {
  const settings = {
    apiBaseUrl: els.apiBaseUrl.value.trim() || DEFAULTS.apiBaseUrl,
    appName: els.appName.value.trim() || DEFAULTS.appName,
    userId: els.userId.value.trim() || DEFAULTS.userId,
    sessionId: els.sessionId.value.trim() || createSessionId(),
    token: els.apiToken.value,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  return settings;
}

function applySettingsToForm(settings) {
  els.apiBaseUrl.value = settings.apiBaseUrl;
  els.appName.value = settings.appName;
  els.userId.value = settings.userId;
  els.sessionId.value = settings.sessionId;
  els.apiToken.value = settings.token;
}

function apiUrl(settings, path) {
  return `${settings.apiBaseUrl.replace(/\/$/, "")}${path}`;
}

function authHeaders(settings) {
  const headers = { "Content-Type": "application/json" };
  if (settings.token) {
    headers.Authorization = `Bearer ${settings.token}`;
  }
  return headers;
}

function setStatus(text, isError = false) {
  els.status.textContent = text;
  els.status.classList.toggle("status--error", isError);
}

function scrollToBottom() {
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function renderEmptyState() {
  if (conversation.length > 0) return;
  els.chatLog.innerHTML =
    '<p class="empty-state">Send a message to test your ADK backend.<br />Use Settings to verify the API connection.</p>';
}

function appendMessage(role, content, { isError = false, rows = [], count = 0, page = null } = {}) {
  const empty = els.chatLog.querySelector(".empty-state");
  if (empty) empty.remove();

  const wrap = document.createElement("article");
  wrap.className = `message message--${isError ? "error" : role === "user" ? "user" : "bot"}`;

  const label = document.createElement("span");
  label.className = "message__role";
  label.textContent = isError ? "Error" : role === "user" ? "You" : "Bot";

  const body = document.createElement("p");
  body.style.margin = "0";
  body.style.whiteSpace = "pre-wrap";
  body.textContent = content;

  wrap.append(label);
  if (content) {
    wrap.append(body);
  }
  if (!isError && Array.isArray(rows) && rows.length > 0) {
    wrap.append(createRowsTable(rows, count, page));
  }
  els.chatLog.appendChild(wrap);
  scrollToBottom();
}

function createRowsTable(rows, count, page) {
  const container = document.createElement("div");
  container.className = "table-card";

  const summary = document.createElement("div");
  summary.className = "table-summary";
  const total = Number.isFinite(count) && count > 0 ? count : rows.length;
  const start = page?.offset != null ? page.offset + 1 : 1;
  const end = page?.offset != null ? page.offset + rows.length : rows.length;
  summary.textContent = `Found ${total} investor(s). Showing ${start}-${end}.`;
  container.appendChild(summary);

  const scroll = document.createElement("div");
  scroll.className = "table-scroll";

  const table = document.createElement("table");
  table.className = "results-table";

  const columns = [
    ["first_name", "Name"],
    ["pan_number", "PAN"],
    ["dob", "DOB"],
    ["email", "Email"],
    ["mobile_number", "Mobile"],
    ["folio_number", "Folio"],
    ["otm", "OTM"],
  ];

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const [, label] of columns) {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const [key] of columns) {
      const td = document.createElement("td");
      const value = row[key] ?? (key === "first_name" ? row.name : undefined);
      td.textContent = formatCell(value);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  scroll.appendChild(table);
  container.appendChild(scroll);

  if (page?.limit && rows.length === page.limit) {
    const hint = document.createElement("div");
    hint.className = "table-hint";
    hint.textContent = "Ask for the next page to see more results.";
    container.appendChild(hint);
  }

  return container;
}

function formatCell(value) {
  if (value === null || value === undefined || value === "") return "N/A";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function extractReplyFromEvents(events) {
  if (!Array.isArray(events) || events.length === 0) {
    return { content: "No response events returned." };
  }

  const toolReplies = [];
  const textReplies = [];

  for (const event of events) {
    const parts = event?.content?.parts || [];
    for (const part of parts) {
      const toolReply = part?.functionResponse?.response?.reply;
      if (typeof toolReply === "string" && toolReply.trim()) {
        const response = part.functionResponse.response;
        const rows = response.rows || [];
        toolReplies.push({
          content: rows.length > 0 ? "" : toolReply.trim(),
          rows,
          count: response.count || 0,
          page: response.page || null,
        });
      }
      if (typeof part?.text === "string" && part.text.trim()) {
        textReplies.push(part.text.trim());
      }
    }
  }

  if (toolReplies.length > 0) {
    return toolReplies[toolReplies.length - 1];
  }
  if (textReplies.length > 0) {
    return { content: textReplies[textReplies.length - 1] };
  }

  return { content: JSON.stringify(events[events.length - 1], null, 2) };
}

async function testBackendConnection(settings) {
  const healthResponse = await fetch(apiUrl(settings, "/health"), {
    headers: authHeaders(settings),
  });
  if (!healthResponse.ok) {
    throw new Error(`Health check failed with HTTP ${healthResponse.status}`);
  }

  const appsResponse = await fetch(apiUrl(settings, "/list-apps"), {
    headers: authHeaders(settings),
  });
  if (!appsResponse.ok) {
    throw new Error(`List apps failed with HTTP ${appsResponse.status}`);
  }

  const apps = await appsResponse.json();
  if (!apps.includes(settings.appName)) {
    throw new Error(`Agent "${settings.appName}" not found. Available: ${apps.join(", ")}`);
  }

  return apps;
}

async function sendToBot(userText, settings) {
  const response = await fetch(apiUrl(settings, "/run"), {
    method: "POST",
    headers: authHeaders(settings),
    body: JSON.stringify({
      appName: settings.appName,
      userId: settings.userId,
      sessionId: settings.sessionId,
      newMessage: {
        role: "user",
        parts: [{ text: userText }],
      },
    }),
  });

  const contentType = response.headers.get("content-type") || "";
  let data;
  if (contentType.includes("application/json")) {
    data = await response.json();
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    const detail =
      typeof data === "object" && data != null
        ? data.detail || data.error || JSON.stringify(data)
        : String(data);
    throw new Error(`HTTP ${response.status}: ${detail}`);
  }

  return extractReplyFromEvents(data);
}

async function handleSubmit(event) {
  event.preventDefault();
  if (isSending) return;

  const text = els.userInput.value.trim();
  if (!text) return;

  const settings = saveSettingsToStorage();

  conversation.push({ role: "user", content: text });
  appendMessage("user", text);
  els.userInput.value = "";
  els.userInput.style.height = "auto";

  isSending = true;
  els.sendBtn.disabled = true;
  els.userInput.disabled = true;
  setStatus("Waiting for bot…");

  try {
    const reply = await sendToBot(text, settings);
    conversation.push({ role: "assistant", ...reply });
    appendMessage("assistant", reply.content, {
      rows: reply.rows,
      count: reply.count,
      page: reply.page,
    });
    setStatus("");
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Request failed";
    appendMessage("assistant", msg, { isError: true });
    setStatus(
      "Could not reach the backend. Confirm uvicorn is running and CORS allows this origin.",
      true
    );
    conversation.pop();
  } finally {
    isSending = false;
    els.sendBtn.disabled = false;
    els.userInput.disabled = false;
    els.userInput.focus();
  }
}

async function handleTestConnection() {
  const settings = saveSettingsToStorage();
  setStatus("Testing backend connection…");
  try {
    const apps = await testBackendConnection(settings);
    setStatus(`Connected. Available agents: ${apps.join(", ")}`);
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Connection test failed";
    setStatus(msg, true);
  }
}

function autoResizeTextarea() {
  const ta = els.userInput;
  ta.style.height = "auto";
  ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
}

els.settingsToggle.addEventListener("click", () => {
  const hidden = els.settingsPanel.hasAttribute("hidden");
  if (hidden) {
    els.settingsPanel.removeAttribute("hidden");
    els.settingsToggle.setAttribute("aria-expanded", "true");
  } else {
    els.settingsPanel.setAttribute("hidden", "");
    els.settingsToggle.setAttribute("aria-expanded", "false");
  }
});

els.saveSettings.addEventListener("click", () => {
  saveSettingsToStorage();
  setStatus("Settings saved.");
  setTimeout(() => setStatus(""), 2000);
});

els.testConnection.addEventListener("click", () => {
  handleTestConnection();
});

els.clearChat.addEventListener("click", () => {
  conversation = [];
  els.chatLog.innerHTML = "";
  els.sessionId.value = createSessionId();
  saveSettingsToStorage();
  renderEmptyState();
  setStatus("Chat cleared. New ADK session created.");
  setTimeout(() => setStatus(""), 2000);
});

els.userInput.addEventListener("input", autoResizeTextarea);
els.userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    els.chatForm.requestSubmit();
  }
});

els.chatForm.addEventListener("submit", handleSubmit);

applySettingsToForm(loadSettings());
renderEmptyState();
handleTestConnection();
els.userInput.focus();
