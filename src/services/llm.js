import { spawn, execSync } from "child_process";
import { existsSync, readdirSync } from "fs";
import { join, dirname } from "path";
import { homedir, cpus, arch, platform } from "os";

const RUACH_DIR = join(homedir(), ".ruach");

function detectArch() {
  try {
    const uname = execSync("uname -m", { encoding: "utf8" }).trim().toLowerCase();
    if (uname === "armv7l" || uname === "armv6l") return "arm";
    if (uname === "aarch64" || uname === "arm64") return "arm64";
    if (uname === "x86_64" || uname === "amd64") return "x64";
  } catch {}
  return arch();
}

function getArchLabel() {
  const a = detectArch();
  const p = platform();
  if (p === "android" || p === "linux") {
    if (a === "arm") return "arm-linux";
    if (a === "arm64") return "aarch64-linux";
    if (a === "x64") return "x86_64-linux";
  }
  if (p === "darwin") {
    if (a === "arm64") return "aarch64-macos";
    if (a === "x64") return "x86_64-macos";
  }
  if (p === "win32") return "x86_64-windows";
  return `${a}-${p}`;
}

export class LLMService {
  constructor() {
    this.process = null;
    this.port = parseInt(process.env.LLAMA_PORT || "8080", 10);
    this.modelPath = null;
    this.serverPath = null;
    this.startTime = null;
  }

  isRunning() {
    return this.process !== null && !this.process.killed;
  }

  getPid() {
    return this.process?.pid || null;
  }

  getUptime() {
    if (!this.startTime) return 0;
    return Date.now() - this.startTime;
  }

  findServer() {
    const archLabel = getArchLabel();
    const bin = process.platform === "win32" ? "llama-server.exe" : "llama-server";
    const candidates = [
      join(RUACH_DIR, "runtime", archLabel, bin),
      join(RUACH_DIR, "runtime", bin),
    ];
    return candidates.find((p) => existsSync(p)) || null;
  }

  findModel() {
    const modelsDir = join(RUACH_DIR, "models");
    if (!existsSync(modelsDir)) return null;
    try {
      const entries = readdirSync(modelsDir);
      const gguf = entries.find((e) => e.endsWith(".gguf"));
      return gguf ? join(modelsDir, gguf) : null;
    } catch {
      return null;
    }
  }

  async start() {
    if (this.isRunning()) return;

    this.serverPath = this.findServer();
    this.modelPath = this.findModel();

    if (!this.serverPath) {
      throw new Error(
        "llama-server not found. Run `ruach setup` to install the runtime."
      );
    }
    if (!this.modelPath) {
      throw new Error(
        "No model found. Run `ruach setup` to download a model."
      );
    }

    return new Promise((resolve, reject) => {
      this.process = spawn(
        this.serverPath,
        [
          "--model", this.modelPath,
          "--host", "127.0.0.1",
          "--port", String(this.port),
          "--ctx-size", "2048",
          "--threads", String(Math.max(1, cpus().length - 1)),
        ],
        {
          stdio: ["ignore", "pipe", "pipe"],
          env: {
            ...process.env,
            OMP_NUM_THREADS: "1",
            LD_LIBRARY_PATH: join(dirname(this.serverPath)) + (process.env.LD_LIBRARY_PATH ? ":" + process.env.LD_LIBRARY_PATH : ""),
          },
        }
      );

      let started = false;
      let startTimeout;
      let stderrOutput = "";

      this.process.stdout.on("data", (data) => {
        const line = data.toString();
        if (!started && line.includes("listening")) {
          started = true;
          clearTimeout(startTimeout);
          this.startTime = Date.now();
          resolve();
        }
      });

      this.process.stderr.on("data", (data) => {
        const line = data.toString();
        stderrOutput += line;
        if (!started && line.includes("listening")) {
          started = true;
          clearTimeout(startTimeout);
          this.startTime = Date.now();
          resolve();
        }
      });

      this.process.on("error", (err) => {
        this.process = null;
        this.startTime = null;
        reject(new Error(`Failed to start llama-server: ${err.message}`));
      });

      this.process.on("exit", (code) => {
        this.process = null;
        this.startTime = null;
        if (!started) {
          reject(new Error(`llama-server exited with code ${code}: ${stderrOutput.slice(0, 500)}`));
        }
      });

      // Timeout after 30s
      startTimeout = setTimeout(() => {
        if (!started) {
          this.process?.kill();
          this.process = null;
          this.startTime = null;
          reject(new Error("llama-server failed to start within 30s"));
        }
      }, 30000);
    });
  }

  stop() {
    if (this.process) {
      this.process.kill("SIGTERM");
      this.process = null;
      this.startTime = null;
    }
  }

  async complete(prompt, opts = {}) {
    const resp = await fetch(`http://127.0.0.1:${this.port}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "local",
        messages: [{ role: "user", content: prompt }],
        stream: false,
      }),
    });

    if (!resp.ok) {
      throw new Error(`llama-server returned ${resp.status}`);
    }

    const data = await resp.json();
    return {
      conversation_id: opts.conversationId || Date.now(),
      content: data.choices?.[0]?.message?.content || "",
    };
  }

  async completeStream(prompt, onToken) {
    const resp = await fetch(`http://127.0.0.1:${this.port}/v1/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "local",
        messages: [{ role: "user", content: prompt }],
        stream: true,
      }),
    });

    if (!resp.ok) {
      throw new Error(`llama-server returned ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6).trim();
          if (data === "[DONE]") return;
          try {
            const parsed = JSON.parse(data);
            const token = parsed.choices?.[0]?.delta?.content;
            if (token) onToken(token);
          } catch {}
        }
      }
    }
  }

  handleStream(ws) {
    ws.on("message", async (msg) => {
      try {
        const { message } = JSON.parse(msg);
        if (!this.isRunning()) await this.start();
        await this.completeStream(message, (token) => {
          ws.send(JSON.stringify({ type: "token", token }));
        });
        ws.send(JSON.stringify({ type: "done" }));
      } catch (err) {
        ws.send(JSON.stringify({ type: "error", message: err.message }));
      }
    });
  }
}
