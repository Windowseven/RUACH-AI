import { Router } from "express";

export const router = Router();

// ── In-memory conversation store ───────────────────────────
const conversations = new Map();
let nextId = 1;

function getOrCreateConversation(id) {
  if (id && conversations.has(id)) return conversations.get(id);
  const conv = { id: nextId++, title: null, messages: [] };
  conversations.set(conv.id, conv);
  return conv;
}

// GET /api/v1/conversations — list all
router.get("/conversations", (req, res) => {
  const list = [...conversations.values()].map((c) => ({
    id: c.id,
    title: c.title,
  }));
  res.json({ data: list });
});

// GET /api/v1/conversations/:id — detail with messages
router.get("/conversations/:id", (req, res) => {
  const conv = conversations.get(parseInt(req.params.id, 10));
  if (!conv) return res.status(404).json({ error: { code: "NOT_FOUND", message: "Conversation not found" } });
  res.json({ data: { messages: conv.messages } });
});

// POST /api/v1/chat — send message, get AI response
router.post("/chat", async (req, res) => {
  const llm = req.app.get("llm");
  const { message, conversation_id } = req.body;

  if (!message || typeof message !== "string") {
    return res.status(400).json({
      error: { code: "BAD_REQUEST", message: "message is required" },
    });
  }

  if (!llm.isRunning()) {
    // Try to start the LLM
    try {
      await llm.start();
    } catch (err) {
      return res.status(503).json({
        error: {
          code: "INFERENCE_UNAVAILABLE",
          message: "LLM server not running. Run `ruach setup` first.",
        },
      });
    }
  }

  try {
    const result = await llm.complete(message, {
      conversationId: conversation_id,
    });

    // Store messages in conversation
    const conv = getOrCreateConversation(conversation_id || result.conversation_id);
    conv.messages.push({ role: "user", content: message });
    conv.messages.push({ role: "assistant", content: result.content });
    if (!conv.title) conv.title = message.slice(0, 60);

    res.json({
      data: {
        conversation_id: conv.id,
        content: result.content,
      },
    });
  } catch (err) {
    res.status(500).json({
      error: { code: "LLM_ERROR", message: err.message },
    });
  }
});

// POST /api/v1/chat/stream — streaming via SSE
router.post("/chat/stream", async (req, res) => {
  const llm = req.app.get("llm");
  const { message, conversation_id } = req.body;

  if (!message) {
    return res.status(400).json({
      error: { code: "BAD_REQUEST", message: "message is required" },
    });
  }

  if (!llm.isRunning()) {
    try {
      await llm.start();
    } catch (err) {
      return res.status(503).json({
        error: {
          code: "INFERENCE_UNAVAILABLE",
          message: "LLM server not running.",
        },
      });
    }
  }

  // SSE headers
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
  });

  try {
    await llm.completeStream(message, (token) => {
      res.write(`data: ${JSON.stringify({ token })}\n\n`);
    });
    res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
    res.end();
  } catch (err) {
    res.write(`data: ${JSON.stringify({ error: err.message })}\n\n`);
    res.end();
  }
});

// POST /api/v1/chat/approvals/:id/approve — approve tool use
router.post("/chat/approvals/:id/approve", (req, res) => {
  const { id } = req.params;
  res.json({
    data: { content: "Approved.", tool: null },
  });
});

// POST /api/v1/chat/approvals/:id/reject — reject tool use
router.post("/chat/approvals/:id/reject", (req, res) => {
  const { id } = req.params;
  res.json({
    data: { content: "Rejected.", tool: null },
  });
});
