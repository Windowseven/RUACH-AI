import express from "express";
import { createServer } from "http";
import { WebSocketServer } from "ws";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { existsSync, readFileSync } from "fs";
import { router as chatRouter } from "./routes/chat.js";
import { router as healthRouter } from "./routes/health.js";
import { LLMService } from "./services/llm.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
const server = createServer(app);

const PORT = parseInt(process.env.RUACH_PORT || "8120", 10);
const HOST = process.env.RUACH_HOST || "127.0.0.1";

// ── Middleware ──────────────────────────────────────────────
app.use(express.json({ limit: "1mb" }));

// ── LLM service (manages llama.cpp subprocess) ────────────
const llm = new LLMService();
app.set("llm", llm);

// ── API routes ─────────────────────────────────────────────
app.use("/api/v1", healthRouter);
app.use("/api/v1", chatRouter);

// ── Serve frontend (built React app) ──────────────────────
const distDir = join(__dirname, "..", "frontend", "dist");
if (existsSync(distDir)) {
  app.use(express.static(distDir));
  app.get("/{*splat}", (req, res) => {
    if (!req.path.startsWith("/api")) {
      res.sendFile(join(distDir, "index.html"));
    }
  });
}

// ── WebSocket (for streaming + terminal) ───────────────────
const wss = new WebSocketServer({ server, path: "/ws" });
wss.on("connection", (ws, req) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const type = url.searchParams.get("type");

  if (type === "chat") {
    llm.handleStream(ws);
  } else if (type === "terminal") {
    handleTerminal(ws);
  } else {
    ws.close(4000, "Unknown ws type");
  }
});

// ── Terminal via node-pty ──────────────────────────────────
async function handleTerminal(ws) {
  try {
    const pty = await import("node-pty");
    const shell = process.env.SHELL || (process.platform === "win32" ? "powershell.exe" : "bash");
    const proc = pty.spawn(shell, [], {
      name: "xterm-256color",
      cols: 80,
      rows: 24,
      cwd: process.env.HOME || "/data/data/com.termux/files/home",
    });

    proc.onData((data) => {
      if (ws.readyState === 1) ws.send(JSON.stringify({ type: "output", data }));
    });
    proc.onExit(({ exitCode }) => {
      if (ws.readyState === 1) ws.send(JSON.stringify({ type: "exit", code: exitCode }));
      ws.close();
    });

    ws.on("message", (msg) => {
      try {
        const parsed = JSON.parse(msg);
        if (parsed.type === "input") proc.write(parsed.data);
        if (parsed.type === "resize") proc.resize(parsed.cols, parsed.rows);
      } catch {}
    });
    ws.on("close", () => proc.kill());
  } catch (err) {
    ws.send(JSON.stringify({ type: "error", message: "Terminal not available: " + err.message }));
    ws.close();
  }
}

// ── Start ──────────────────────────────────────────────────
server.listen(PORT, HOST, () => {
  console.log(`\n  ╔══════════════════════════════════════╗`);
  console.log(`  ║  RUACH AI — Local-First Workspace   ║`);
  console.log(`  ╠══════════════════════════════════════╣`);
  console.log(`  ║  UI:    http://${HOST}:${PORT}          ║`);
  console.log(`  ║  API:   http://${HOST}:${PORT}/api/v1   ║`);
  console.log(`  ║  WS:    ws://${HOST}:${PORT}/ws         ║`);
  console.log(`  ╚══════════════════════════════════════╝\n`);
});

// ── Graceful shutdown ──────────────────────────────────────
process.on("SIGINT", () => {
  llm.stop();
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 3000);
});
process.on("SIGTERM", () => {
  llm.stop();
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 3000);
});
