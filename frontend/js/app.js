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
    els.messages.querySelectorAll(".message, .approval-card, .tool-activity").forEach((n) => n.remove());
    els.empty.style.display = detail.messages.length ? "none" : "";
    for (const msg of detail.messages) {
      if (msg.role === "tool") {
        try {
          const event = JSON.parse(msg.content);
          addToolActivity(event.capability || "unknown", event.state || "?");
        } catch {
          addToolActivity("unknown", "LOGGED");
        }
      } else {
        addMessage(msg.role, msg.content);
      }
    }
    closeDrawer();
  } catch (err) {
    handleFailure(err);
  }
}

function resetToNewChat() {
  state.activeId = null;
  els.messages
    .querySelectorAll(".message, .approval-card, .tool-activity")
    .forEach((n) => n.remove());
  els.empty.style.display = "";
  renderConversationList();
  closeDrawer();
  els.input.focus();
}

function addToolActivity(capability, stateLabel) {
  els.empty.style.display = "none";
  const line = document.createElement("div");
  line.className = `tool-activity tool-${stateLabel.toLowerCase()}`;
  line.textContent = `TOOL ${capability} — ${stateLabel}`;
  els.messages.appendChild(line);
  scrollToEnd();
}

function addApprovalCard(pending) {
  els.empty.style.display = "none";
  const card = document.createElement("section");
  card.className = "approval-card";

  const head = document.createElement("header");
  const title = document.createElement("div");
  title.className = "approval-title";
  title.textContent = "APPROVAL REQUIRED";
  const cap = document.createElement("div");
  cap.className = "approval-capability";
  cap.textContent = pending.capability;
  const args = document.createElement("code");
  args.className = "approval-args";
  args.textContent = JSON.stringify(pending.arguments);
  head.append(title, cap, args);

  const actions = document.createElement("div");
  actions.className = "approval-actions";
  const denyBtn = document.createElement("button");
  denyBtn.type = "button";
  denyBtn.className = "btn-deny";
  denyBtn.textContent = "DENY";
  const approveBtn = document.createElement("button");
  approveBtn.type = "button";
  approveBtn.className = "btn-approve";
  approveBtn.textContent = "APPROVE";
  actions.append(denyBtn, approveBtn);

  card.append(head, actions);
  els.messages.appendChild(card);
  scrollToEnd();

  let settled = false;
  async function decide(kind) {
    if (settled) return;
    settled = true;
    approveBtn.disabled = true;
    denyBtn.disabled = true;
    card.classList.add("settling");
    try {
      const result =
        kind === "approve"
          ? await api.approveTool(pending.approval_id)
          : await api.rejectTool(pending.approval_id);
      card.remove();
      if (result.tool) {
        addToolActivity(result.tool.capability, result.tool.state);
      }
      addMessage("assistant", result.content);
      await refreshConversations();
    } catch (err) {
      card.classList.remove("settling");
      settled = false;
      approveBtn.disabled = false;
      denyBtn.disabled = false;
      addMessage(
        "error",
        err.code === "OFFLINE"
          ? "The local server is unreachable. The action was not executed."
          : `Approval failed (${err.code}): ${err.message}`,
      );
      if (err.code === "OFFLINE") setConnection("disconnected");
    }
  }

  approveBtn.addEventListener("click", () => decide("approve"));
  denyBtn.addEventListener("click", () => decide("deny"));
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
    if (result.tool) {
      addToolActivity(result.tool.capability, result.tool.state);
    }
    addMessage("assistant", result.content);
    if (result.pending_approval) {
      addApprovalCard(result.pending_approval);
    }
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
