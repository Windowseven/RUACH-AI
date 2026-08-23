/* RUACH workspace app — state split per docs/09 §74. */

import { api, ApiError } from "./api.js";
import { boot } from "./boot.js";

const els = {
  boot: document.getElementById("boot-screen"),
  workspace: document.getElementById("workspace"),
  messages: document.getElementById("messages"),
  empty: document.getElementById("empty-state"),
  composer: document.getElementById("composer"),
  input: document.getElementById("composer-input"),
  sendBtn: document.getElementById("send-btn"),
  conversationList: document.getElementById("conversation-list"),
  newChat: document.getElementById("new-chat"),
  sidebar: document.getElementById("sidebar"),
  drawerToggle: document.getElementById("drawer-toggle"),
  drawerBackdrop: document.getElementById("drawer-backdrop"),
  offline: document.getElementById("offline-banner"),
  reconnect: document.getElementById("reconnect-btn"),
  badge: document.getElementById("connection-badge"),
};

const state = {
  connection: "connecting", // connecting | connected | disconnected
  conversations: [],
  activeId: null,
  sending: false,
};

/* --------------------------------------------------------- connection */

function setConnection(mode) {
  state.connection = mode;
  const dot = els.badge.querySelector(".dot");
  if (mode === "connected") {
    dot.classList.add("dot-ok");
    els.offline.hidden = true;
  } else {
    dot.classList.remove("dot-ok");
    if (mode === "disconnected" && !els.workspace.hidden) els.offline.hidden = false;
  }
}

els.reconnect.addEventListener("click", () => location.reload());

/* ------------------------------------------------------------ messages */

function scrollToEnd() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

function addMessage(role, content, extraClass = "") {
  els.empty.style.display = "none";
  const wrap = document.createElement("article");
  wrap.className = `message ${role} ${extraClass}`.trim();
  const head = document.createElement("div");
  head.className = "message-head";
  const glyph = role === "assistant" ? '<span class="state-glyph">◉</span>' : "";
  head.innerHTML = `${glyph}<span class="who"></span>`;
  const body = document.createElement("div");
  body.className = "body";
  body.textContent = content;
  wrap.append(head, body);
  els.messages.appendChild(wrap);
  scrollToEnd();
  return body;
}

function addThinking() {
  const head = addMessage("assistant", "", "state-thinking").parentElement;
  const body = head.querySelector(".body");
  body.textContent = "";
  return { block: head, body };
}

/* -------------------------------------------------------- conversation */

async function refreshConversations() {
  try {
    state.conversations = await api.conversations();
    renderConversationList();
  } catch (err) {
    handleFailure(err);
  }
}

function renderConversationList() {
  els.conversationList.textContent = "";
  for (const convo of state.conversations) {
    const item = document.createElement("button");
    item.type = "button";
    item.className =
      "conversation-item" + (convo.id === state.activeId ? " active" : "");
    item.textContent = convo.title || "(untitled)";
    item.addEventListener("click", () => selectConversation(convo.id));
    els.conversationList.appendChild(item);
  }
}

async function selectConversation(id) {
  state.activeId = id;
  renderConversationList();
  try {
    const detail = await api.conversationDetail(id);
    els.messages.querySelectorAll(".message").forEach((m) => m.remove());
    els.empty.style.display = detail.messages.length ? "none" : "";
    for (const msg of detail.messages) {
      addMessage(msg.role, msg.content);
    }
    closeDrawer();
  } catch (err) {
    handleFailure(err);
  }
}

function resetToNewChat() {
  state.activeId = null;
  els.messages.querySelectorAll(".message").forEach((m) => m.remove());
  els.empty.style.display = "";
  renderConversationList();
  closeDrawer();
  els.input.focus();
}

async function sendMessage(text) {
  if (!text.trim() || state.sending) return;
  state.sending = true;
  els.sendBtn.disabled = true;

  addMessage("user", text);
  const thinking = addThinking();

  try {
    const result = await api.send(state.activeId, text.trim());
    thinking.block.remove();
    addMessage("assistant", result.content);
    if (!state.activeId) {
      state.activeId = result.conversation_id;
    }
    await refreshConversations();
  } catch (err) {
    thinking.block.remove();
    const explanation =
      err.code === "OFFLINE"
        ? "The local server is unreachable. Your message was not delivered."
        : `Inference error (${err.code}): ${err.message}`;
    addMessage("error", explanation);
    if (err.code === "OFFLINE") setConnection("disconnected");
  } finally {
    state.sending = false;
    updateSendState();
    els.input.focus();
  }
}

function handleFailure(err) {
  if (err instanceof ApiError && err.code === "OFFLINE") setConnection("disconnected");
}

/* ------------------------------------------------------------- composer */

function updateSendState() {
  els.sendBtn.disabled = state.sending || !els.input.value.trim();
}

els.input.addEventListener("input", () => {
  updateSendState();
  autosize();
});

function autosize() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 180) + "px";
}

els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    const text = els.input.value;
    els.input.value = "";
    autosize();
    updateSendState();
    sendMessage(text);
  }
});

els.composer.addEventListener("submit", (event) => event.preventDefault());
els.sendBtn.addEventListener("click", () => {
  const text = els.input.value;
  els.input.value = "";
  autosize();
  updateSendState();
  sendMessage(text);
});
els.newChat.addEventListener("click", resetToNewChat);

/* ---------------------------------------------------------------- drawer */

function openDrawer() {
  els.sidebar.classList.add("open");
  els.drawerBackdrop.hidden = false;
  els.drawerToggle.setAttribute("aria-expanded", "true");
}
function closeDrawer() {
  els.sidebar.classList.remove("open");
  els.drawerBackdrop.hidden = true;
  els.drawerToggle.setAttribute("aria-expanded", "false");
}
els.drawerToggle.addEventListener("click", () =>
  els.sidebar.classList.contains("open") ? closeDrawer() : openDrawer(),
);
els.drawerBackdrop.addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeDrawer();
});

/* ------------------------------------------------------------------ boot */

setConnection("connecting");

boot(async () => {
  setConnection("connected");
  els.boot.style.opacity = "0";
  setTimeout(() => {
    els.boot.hidden = true;
    els.workspace.hidden = false;
    requestAnimationFrame(() => els.workspace.classList.add("visible"));
    els.input.focus();
  }, 250);
  await refreshConversations();
});
