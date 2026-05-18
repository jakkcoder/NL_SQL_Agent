const STORAGE_KEY = "chatbot-tester-settings";

const DEFAULTS = {
  apiUrl: "http://localhost:8000/chat",
  messageKey: "message",
  responseKey: "reply",
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
  apiUrl: document.getElementById("api-url"),
  messageKey: document.getElementById("message-key"),
  responseKey: document.getElementById("response-key"),
  apiToken: document.getElementById("api-token"),
  saveSettings: document.getElementById("save-settings"),
  clearChat: document.getElementById("clear-chat"),
};

/** @type {{ role: "user" | "assistant", content: string }[]} */
let conversation = [];
let isSending = false;

function loadSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : { ...DEFAULTS };
  } catch {
    return { ...DEFAULTS };
  }
}

function saveSettingsToStorage() {
  const settings = {
    apiUrl: els.apiUrl.value.trim() || DEFAULTS.apiUrl,
    messageKey: els.messageKey.value.trim() || DEFAULTS.messageKey,
    responseKey: els.responseKey.value.trim() || DEFAULTS.responseKey,
    token: els.apiToken.value,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  return settings;
}

function applySettingsToForm(settings) {
  els.apiUrl.value = settings.apiUrl;
  els.messageKey.value = settings.messageKey;
  els.responseKey.value = settings.responseKey;
  els.apiToken.value = settings.token;
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
    '<p class="empty-state">Send a message to test your chatbot.<br />Configure the API URL in Settings.</p>';
}

function appendMessage(role, content, { isError = false } = {}) {
  const empty = els.chatLog.querySelector(".empty-state");
  if (empty) empty.remove();

  const wrap = document.createElement("article");
  wrap.className = `message message--${isError ? "error" : role === "user" ? "user" : "bot"}`;

  const label = document.createElement("span");
  label.className = "message__role";
  label.textContent = isError ? "Error" : role === "user" ? "You" : "Bot";

  const body = document.createElement("p");
  body.style.margin = "0";
  body.textContent = content;

  wrap.append(label, body);
  els.chatLog.appendChild(wrap);
  scrollToBottom();
}

function getNestedValue(obj, path) {
  return path.split(".").reduce((acc, key) => (acc == null ? undefined : acc[key]), obj);
}

function extractReply(data, responseKey) {
  const direct = getNestedValue(data, responseKey);
  if (typeof direct === "string") return direct;

  const fallbacks = ["reply", "response", "answer", "text", "content", "message"];
  for (const key of fallbacks) {
    const val = data[key];
    if (typeof val === "string") return val;
  }

  if (typeof data === "string") return data;
  return JSON.stringify(data, null, 2);
}

async function sendToBot(userText, settings) {
  const body = {
    [settings.messageKey]: userText,
    messages: conversation,
  };

  const headers = {
    "Content-Type": "application/json",
  };
  if (settings.token) {
    headers.Authorization = `Bearer ${settings.token}`;
  }

  const response = await fetch(settings.apiUrl, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
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

  return extractReply(data, settings.responseKey);
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
    conversation.push({ role: "assistant", content: reply });
    appendMessage("assistant", reply);
    setStatus("");
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Request failed";
    appendMessage("assistant", msg, { isError: true });
    setStatus(
      "Could not reach the API. Is your backend running? Enable CORS for this origin.",
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

els.clearChat.addEventListener("click", () => {
  conversation = [];
  els.chatLog.innerHTML = "";
  renderEmptyState();
  setStatus("Chat cleared.");
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
els.userInput.focus();
